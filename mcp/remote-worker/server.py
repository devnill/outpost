"""
outpost-remote-worker: FastAPI HTTP service that runs on remote machines, accepts jobs
from the local MCP server, executes them using the local `claude` CLI, captures results,
and exposes a REST API for job management.

Configuration via environment variables:
- IDEATE_WORKER_API_KEY: Required API key for X-API-Key header authentication.
- IDEATE_WORKER_MAX_CONCURRENCY: Max concurrent jobs (default: 3).
- IDEATE_WORKER_PORT: Listen port (default: 7432).
"""

import asyncio
import datetime
import hmac
import logging
import os
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("outpost-remote-worker")

VERSION = "0.1.0"
DEFAULT_MAX_CONCURRENCY = 3
DEFAULT_PORT = 7432
DEFAULT_TIMEOUT = 600
MAX_PROMPT_BYTES = 100_000


# --- Models ---


class JobRequest(BaseModel):
    prompt: str
    working_dir: str
    role: str = "worker"
    max_turns: int = 30
    timeout: int = DEFAULT_TIMEOUT
    permission_mode: str = "acceptEdits"
    allowed_tools: list[str] | None = None


class JobRecord:
    def __init__(self, job_id: str, request: JobRequest):
        self.job_id = job_id
        self.status = "queued"
        self.role = request.role
        self.prompt = request.prompt
        self.working_dir = request.working_dir
        self.max_turns = request.max_turns
        self.timeout = request.timeout
        self.permission_mode = request.permission_mode
        self.allowed_tools = request.allowed_tools
        self.created_at = datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.output: str | None = None
        self.exit_code: int | None = None
        self.git_diff: str | None = None
        self.error: str | None = None
        self.duration_ms: int | None = None


# --- State ---

job_store: dict[str, JobRecord] = {}
job_store_lock = asyncio.Lock()
job_queue: asyncio.Queue[str] = asyncio.Queue()


# --- App ---


@asynccontextmanager
async def lifespan(application: FastAPI):
    global _max_concurrency
    _max_concurrency = _get_max_concurrency()
    tasks = [asyncio.create_task(_worker(i)) for i in range(_max_concurrency)]
    logger.info("Started %d worker coroutines", _max_concurrency)
    yield
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Worker coroutines cancelled")


app = FastAPI(title="outpost-remote-worker", version=VERSION, lifespan=lifespan)


def _get_api_key() -> str:
    return os.environ.get("IDEATE_WORKER_API_KEY", "")


def _get_max_concurrency() -> int:
    try:
        return int(os.environ.get("IDEATE_WORKER_MAX_CONCURRENCY", str(DEFAULT_MAX_CONCURRENCY)))
    except ValueError:
        return DEFAULT_MAX_CONCURRENCY


def _get_base_dir() -> Path | None:
    base = os.environ.get("IDEATE_WORKER_BASE_DIR", "")
    return Path(base).resolve() if base else None


# Resolved at startup
_max_concurrency: int = DEFAULT_MAX_CONCURRENCY


# --- Auth middleware ---


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    expected_key = _get_api_key()
    if not expected_key:
        return JSONResponse(
            status_code=401,
            content={"detail": "IDEATE_WORKER_API_KEY not configured on server"},
        )

    provided_key = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(provided_key, expected_key):
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API key"},
        )

    return await call_next(request)


# --- Endpoints ---


@app.get("/health")
async def health():
    async with job_store_lock:
        active = sum(1 for j in job_store.values() if j.status == "running")
        queued = sum(1 for j in job_store.values() if j.status == "queued")
    return {
        "status": "ok",
        "version": VERSION,
        "active_jobs": active,
        "queued_jobs": queued,
        "max_concurrency": _max_concurrency,
    }


@app.post("/jobs", status_code=201)
async def create_job(request: JobRequest):
    # Validate prompt size
    prompt_bytes = len(request.prompt.encode("utf-8"))
    if prompt_bytes > MAX_PROMPT_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Prompt too large: {prompt_bytes} bytes exceeds {MAX_PROMPT_BYTES} byte limit",
        )

    # Validate working_dir exists
    working_dir = Path(request.working_dir)
    if not working_dir.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"working_dir does not exist or is not a directory: {request.working_dir}",
        )

    # Validate working_dir is within IDEATE_WORKER_BASE_DIR if configured
    base_dir = _get_base_dir()
    if base_dir is not None:
        try:
            working_dir.resolve().relative_to(base_dir)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"working_dir is outside allowed base directory {base_dir}",
            )

    job_id = str(uuid.uuid4())
    record = JobRecord(job_id, request)

    async with job_store_lock:
        job_store[job_id] = record

    await job_queue.put(job_id)

    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs")
async def list_jobs():
    async with job_store_lock:
        result = []
        for record in job_store.values():
            entry = {
                "job_id": record.job_id,
                "status": record.status,
                "role": record.role,
                "created_at": record.created_at,
            }
            if record.duration_ms is not None:
                entry["duration_ms"] = record.duration_ms
            result.append(entry)
    return result


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    async with job_store_lock:
        record = job_store.get(job_id)
        if not record:
            raise HTTPException(status_code=404, detail="Job not found")

        if record.status == "running":
            return {"job_id": record.job_id, "status": "running", "started_at": record.started_at}

        if record.status in ("completed", "failed"):
            return {
                "job_id": record.job_id,
                "status": record.status,
                "git_diff": record.git_diff,
                "output": record.output,
                "exit_code": record.exit_code,
                "duration_ms": record.duration_ms,
                "error": record.error,
                "created_at": record.created_at,
                "started_at": record.started_at,
                "completed_at": record.completed_at,
            }

        # queued or cancelled
        return {
            "job_id": record.job_id,
            "status": record.status,
            "created_at": record.created_at,
        }


@app.delete("/jobs/{job_id}", status_code=204)
async def cancel_job(job_id: str):
    async with job_store_lock:
        record = job_store.get(job_id)
        if not record:
            raise HTTPException(status_code=404, detail="Job not found")

        if record.status != "queued":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot cancel job with status '{record.status}'",
            )

        record.status = "cancelled"

    return None


# --- Worker coroutines ---


def _capture_git_diff(working_dir: str) -> str | None:
    """Capture git diff HEAD in the working directory. Returns None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _run_claude_job(record: JobRecord) -> tuple[str, int, str | None]:
    """
    Run claude CLI synchronously. Returns (output, exit_code, error).
    Uses the same subprocess pattern as session-spawner.
    """
    cmd = [
        "claude",
        "--print",
        "--output-format", "json",
        "--permission-mode", record.permission_mode,
        "--max-turns", str(record.max_turns),
        record.prompt,
    ]

    if record.allowed_tools:
        cmd.extend(["--allowedTools", ",".join(record.allowed_tools)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=record.timeout,
            cwd=record.working_dir,
        )
        error = result.stderr if result.returncode != 0 else None
        return result.stdout, result.returncode, error
    except subprocess.TimeoutExpired as e:
        # Capture partial output on timeout
        partial_stdout = ""
        if isinstance(e.stdout, bytes):
            partial_stdout = e.stdout.decode("utf-8", errors="ignore")
        elif e.stdout:
            partial_stdout = e.stdout
        return partial_stdout, -1, f"Job timed out after {record.timeout}s"


async def _process_job(record: JobRecord) -> None:
    """Execute a running job record. Called by _worker after status is set to 'running'.
    Exposed for testing so tests can drive execution without duplicating this logic."""
    start_time = time.monotonic()

    output, exit_code, error = await asyncio.to_thread(_run_claude_job, record)
    duration_ms = int((time.monotonic() - start_time) * 1000)
    git_diff = await asyncio.to_thread(_capture_git_diff, record.working_dir)

    completed_at = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    async with job_store_lock:
        record.output = output
        record.exit_code = exit_code
        record.git_diff = git_diff
        record.error = error
        record.duration_ms = duration_ms
        record.completed_at = completed_at
        record.status = "failed" if exit_code != 0 else "completed"

    logger.info(
        "Job %s %s in %dms (exit_code=%d)",
        record.job_id, record.status, duration_ms, exit_code,
    )


async def _worker(worker_id: int):
    """Worker coroutine that drains the job queue."""
    logger.info("Worker %d started", worker_id)
    while True:
        job_id = await job_queue.get()
        try:
            async with job_store_lock:
                record = job_store.get(job_id)
                if not record or record.status != "queued":
                    # Job was cancelled or removed while queued
                    continue
                record.status = "running"
                record.started_at = datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(timespec="milliseconds").replace("+00:00", "Z")

            await _process_job(record)
        except Exception as exc:
            logger.exception("Worker %d encountered an error processing job %s", worker_id, job_id)
            async with job_store_lock:
                record = job_store.get(job_id)
                if record:
                    record.status = "failed"
                    record.error = str(exc)
                    record.completed_at = datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        finally:
            job_queue.task_done()


def main():
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    port = DEFAULT_PORT
    try:
        port = int(os.environ.get("IDEATE_WORKER_PORT", str(DEFAULT_PORT)))
    except ValueError:
        port = DEFAULT_PORT

    host = os.environ.get("IDEATE_WORKER_HOST", "0.0.0.0")
    max_concurrency = _get_max_concurrency()
    api_key = _get_api_key()

    logger.info(
        "outpost-remote-worker v%s starting on %s:%d, max_concurrency=%d, api_key=%s",
        VERSION, host, port, max_concurrency,
        "configured" if api_key else "NOT SET (all requests will be rejected)",
    )

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()