"""
outpost-remote-worker: FastAPI HTTP service that runs on remote machines, accepts jobs
from the local MCP server, executes them using the local `claude` CLI, captures results,
and exposes a REST API for job management.

Configuration via environment variables:
- IDEATE_WORKER_API_KEY: Required API key for X-API-Key header authentication.
- IDEATE_WORKER_MAX_CONCURRENCY: Max concurrent jobs (default: 3).
- IDEATE_WORKER_MAX_JOBS: Max jobs retained in the job store (default: 1000).
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

# Container execution configuration
_agent_image = os.environ.get("OUTPOST_AGENT_IMAGE", "")
_container_runtime = os.environ.get("OUTPOST_CONTAINER_RUNTIME", "")
_container_memory = os.environ.get("OUTPOST_CONTAINER_MEMORY", "4g")
_container_cpus = os.environ.get("OUTPOST_CONTAINER_CPUS", "2")
DEFAULT_MAX_CONCURRENCY = 3
DEFAULT_PORT = 7432
DEFAULT_TIMEOUT = 600
MAX_PROMPT_BYTES = 100_000

_FILE_NOT_FOUND = object()  # sentinel for FileNotFoundError from _run_claude_job


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
        self.process: subprocess.Popen | None = None
        self.container_name: str | None = None


# --- State ---

job_store: dict[str, JobRecord] = {}
job_store_lock = asyncio.Lock()


# --- App ---


@asynccontextmanager
async def lifespan(application: FastAPI):
    global _max_concurrency, _max_jobs, job_queue
    _max_concurrency = _get_max_concurrency()
    try:
        _max_jobs = int(os.environ.get("IDEATE_WORKER_MAX_JOBS", "1000"))
    except ValueError:
        _max_jobs = 1000
    job_queue = asyncio.Queue(maxsize=_max_jobs)
    if not _get_api_key():
        logger.warning(
            "IDEATE_WORKER_API_KEY is not set — all requests will be rejected with HTTP 401"
        )
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
_max_jobs: int = 1000

job_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_max_jobs)


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
        "max_jobs": _max_jobs,
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

    # Validate ANTHROPIC_API_KEY is present when container mode is active
    if _agent_image and not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail=(
                "ANTHROPIC_API_KEY is not set in the worker environment. "
                "Container mode requires ANTHROPIC_API_KEY to authenticate "
                "the claude CLI inside the container."
            ),
        )

    job_id = str(uuid.uuid4())
    record = JobRecord(job_id, request)

    async with job_store_lock:
        job_store[job_id] = record
    try:
        job_queue.put_nowait(job_id)
    except asyncio.QueueFull:
        async with job_store_lock:
            del job_store[job_id]
        raise HTTPException(status_code=429, detail="Job queue is full. Try again later.")

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
            if record.started_at is not None:
                entry["started_at"] = record.started_at
            if record.completed_at is not None:
                entry["completed_at"] = record.completed_at
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

        if record.status in ("completed", "failed", "cancelled"):
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

        # queued
        return {
            "job_id": record.job_id,
            "status": record.status,
            "created_at": record.created_at,
        }


@app.delete("/jobs/{job_id}", status_code=204)
async def cancel_job(job_id: str):
    proc = None
    container_name = None
    async with job_store_lock:
        record = job_store.get(job_id)
        if not record:
            raise HTTPException(status_code=404, detail="Job not found")

        if record.status == "queued":
            record.status = "cancelled"
            _evict_terminal_jobs_locked()
            return None

        if record.status == "running":
            proc = record.process
            container_name = record.container_name
            record.status = "cancelled"
            record.completed_at = datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            _evict_terminal_jobs_locked()
            # Signal outside the lock to avoid blocking
        else:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot cancel job with status '{record.status}'",
            )

    # Stop the container if running in container mode
    if container_name:
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["docker", "stop", container_name],
                timeout=15,
                capture_output=True,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    # Signal the process after releasing the lock.
    # In container mode, docker stop already caused docker run to exit — skip terminate/wait.
    if proc is not None and not container_name:
        try:
            proc.terminate()
        except (ProcessLookupError, OSError):  # process already exited; ProcessLookupError is a subclass of OSError
            pass
        # Give it 2s to terminate gracefully, then kill
        try:
            await asyncio.wait_for(
                asyncio.to_thread(proc.wait),
                timeout=2.0
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except (ProcessLookupError, OSError):  # process already exited
                pass

    return None


# --- LRU eviction ---


def _evict_terminal_jobs_locked() -> None:
    """Must be called while holding job_store_lock. Remove oldest terminal jobs when job_store exceeds _max_jobs."""
    if len(job_store) <= _max_jobs:
        return
    terminal = [r for r in job_store.values() if r.status in ("completed", "failed", "cancelled")]
    # Sort by completion timestamp (fallback to creation time for cancelled-while-queued)
    terminal.sort(key=lambda r: r.completed_at or r.created_at or "")
    needed = len(job_store) - _max_jobs
    evict_count = min(needed, len(terminal))
    if len(terminal) < needed:
        logger.warning(
            "Cannot prune job store to capacity: need to evict %d but only %d terminal jobs available "
            "(active/queued jobs alone exceed _max_jobs=%d)",
            needed, len(terminal), _max_jobs,
        )
    for record in terminal[:evict_count]:
        del job_store[record.job_id]


# --- Worker coroutines ---


def _capture_git_diff(working_dir: str) -> str | None:
    """Capture git diff HEAD in the working directory. Returns None if not a git repo."""
    try:
        proc = subprocess.Popen(
            ["git", "diff", "HEAD"],
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate(timeout=30)
        if proc.returncode == 0:
            return stdout
        return None
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()  # drain pipes and reap
        return None
    except (FileNotFoundError, OSError):
        return None


def _build_claude_cmd(record: JobRecord) -> list[str]:
    """Build a direct claude CLI invocation command."""
    cmd = [
        "claude", "--print", "--output-format", "json",
        "--permission-mode", record.permission_mode,
        "--max-turns", str(record.max_turns),
        "--cwd", record.working_dir,
    ]
    if record.allowed_tools:
        cmd.extend(["--allowedTools", ",".join(record.allowed_tools)])
    cmd.append(record.prompt)
    return cmd


def _build_container_cmd(record: JobRecord) -> list[str]:
    """Build a docker run command that invokes claude inside the agent container."""
    cmd = ["docker", "run", "--rm"]
    if _container_runtime:
        cmd.extend(["--runtime", _container_runtime])
    cmd.extend([
        "--name", f"job-{record.job_id}",
        "--user", "1000:1000",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--memory", _container_memory,
        "--memory-swap", _container_memory,
        "--cpus", _container_cpus,
        "--pids-limit", "512",
        "-v", f"{record.working_dir}:/workspace",
        "-e", "ANTHROPIC_API_KEY",
        _agent_image,
        "--print", "--output-format", "json",
        "--permission-mode", "dangerouslySkipPermissions",
        "--max-turns", str(record.max_turns),
        "--cwd", "/workspace",
    ])
    if record.allowed_tools:
        cmd.extend(["--allowedTools", ",".join(record.allowed_tools)])
    cmd.append(record.prompt)
    return cmd


def _run_claude_job(record: JobRecord) -> tuple[str, int, str | None] | tuple[object, str] | None:
    """
    Run claude CLI synchronously. Returns (output, exit_code, error).
    Invokes `claude --print` with JSON output, setting both cwd= on the subprocess
    and --cwd in the CLI arguments. When OUTPOST_AGENT_IMAGE is set, runs inside
    a Docker container instead of invoking claude directly.
    """
    if _agent_image:
        cmd = _build_container_cmd(record)
    else:
        cmd = _build_claude_cmd(record)

    try:
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=record.working_dir,
            )
        except FileNotFoundError:
            if _agent_image:
                msg = (
                    "docker not found on PATH. Ensure Docker is installed and the "
                    "'docker' binary is accessible in the server process environment."
                )
            else:
                msg = (
                    "claude CLI not found on PATH. Ensure Claude Code is installed and the "
                    "'claude' binary is accessible in the server process environment."
                )
            return (_FILE_NOT_FOUND, msg)
        # Guard: if the job was cancelled while Popen was initializing, kill and abort
        if record.status == "cancelled":
            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass
            return None
        record.process = proc  # set before communicate() so cancel can signal it
        if _agent_image:
            record.container_name = f"job-{record.job_id}"

        try:
            stdout, stderr = proc.communicate(timeout=record.timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                stdout_data, stderr_data = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                stdout_data, stderr_data = "", ""
            partial_stdout = stdout_data if isinstance(stdout_data, str) else stdout_data.decode("utf-8", errors="ignore")
            return partial_stdout, -1, f"Job timed out after {record.timeout}s"

        error = stderr if proc.returncode != 0 else None
        return stdout, proc.returncode, error
    finally:
        record.process = None  # clear after completion
        record.container_name = None  # clear container name after completion


async def _process_job(record: JobRecord) -> None:
    """Execute a running job record. Called by _worker after status is set to 'running'.
    Exposed for testing so tests can drive execution without duplicating this logic."""
    start_time = time.monotonic()

    result = await asyncio.to_thread(_run_claude_job, record)
    duration_ms = int((time.monotonic() - start_time) * 1000)

    # _run_claude_job returns:
    #   None                        — cancel-while-starting sentinel; no further updates needed
    #   (_FILE_NOT_FOUND, message)  — FileNotFoundError; 2-tuple with sentinel as first element
    #   (out, code, err)            — normal completion (stdout, exit_code, stderr_or_None)
    if result is None:
        # Cancel path: record was already marked cancelled before Popen; set duration_ms only
        async with job_store_lock:
            record.duration_ms = duration_ms
            _evict_terminal_jobs_locked()
        logger.info("Job %s %s in %dms", record.job_id, record.status, duration_ms)
        return

    # FileNotFoundError path: _run_claude_job returns (_FILE_NOT_FOUND, message) when Popen raises FileNotFoundError
    if isinstance(result, tuple) and result[0] is _FILE_NOT_FOUND:
        _, error = result
        completed_at = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        async with job_store_lock:
            record.exit_code = 1
            record.error = error
            record.duration_ms = duration_ms
            if record.status != "cancelled":
                record.status = "failed"
                record.completed_at = completed_at
            _evict_terminal_jobs_locked()
        binary = "docker" if _agent_image else "claude"
        logger.info("Job %s failed (%s not found) in %dms", record.job_id, binary, duration_ms)
        return

    output, exit_code, error = result
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
        if record.status != "cancelled":  # don't overwrite cancel
            record.completed_at = completed_at
            record.status = "failed" if exit_code != 0 else "completed"
        _evict_terminal_jobs_locked()

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