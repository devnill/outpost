# Work Item 030: Remote Worker Daemon

## Objective

Create a standalone Python HTTP service (`mcp/remote-worker/server.py`) that runs on remote machines, accepts jobs from the local MCP server, executes them using the local `claude` CLI (including local/open-weight models), captures results, and exposes a REST API for job management.

## Acceptance Criteria

1. `POST /jobs` accepts a job payload and queues it; returns `{"job_id": "<uuid>", "status": "queued"}` with HTTP 201.
2. `GET /jobs/{job_id}` returns current status. For completed jobs: includes `git_diff`, `output`, `exit_code`, `duration_ms`. For running jobs: `{"status": "running", "started_at": "<iso8601>"}`.
3. `GET /jobs` returns list of all jobs: `[{job_id, status, role, created_at, duration_ms?}]`.
4. `DELETE /jobs/{job_id}` cancels a queued job with 204. Returns 409 if already running or completed.
5. `GET /health` returns `{"status": "ok", "version": "0.1.0", "active_jobs": N, "queued_jobs": N, "max_concurrency": N}`.
6. All endpoints require `X-API-Key` header matching `IDEATE_WORKER_API_KEY` env var; missing/wrong key returns 401.
7. Max concurrent jobs controlled by `IDEATE_WORKER_MAX_CONCURRENCY` env var (default: 3).
8. After job completion, `git_diff` captured via `subprocess.run(["git", "diff", "HEAD"], cwd=working_dir)`. If working_dir is not a git repo, `git_diff` is null.
9. `IDEATE_WORKER_PORT` sets listen port (default: 7432).
10. Timeout per job from payload `timeout` field (default: 600s). Partial output captured on timeout.
11. Job execution uses `claude --print --output-format json --permission-mode {permission_mode} --max-turns {max_turns}` + prompt as positional arg. Same subprocess pattern as session-spawner.
12. Prompts > 100KB rejected with 400 before queuing.
13. Service starts with `python server.py`; logs startup config to stderr.

## File Scope

- create: `mcp/remote-worker/server.py`
- create: `mcp/remote-worker/requirements.txt` — `fastapi>=0.100.0`, `uvicorn>=0.20.0`
- create: `mcp/remote-worker/requirements-dev.txt` — `pytest>=7.0.0`, `pytest-asyncio>=0.21.0`, `httpx>=0.24.0`
- create: `mcp/remote-worker/pyproject.toml` — Python >= 3.10, entry point `ideate-worker = server:main`

## Dependencies

None.

## Implementation Notes

- Use FastAPI + uvicorn. `/docs` auto-generated.
- Job store: in-memory dict `{job_id: JobRecord}` with asyncio lock. No persistence across restarts.
- JobRecord: job_id (UUID str), status (queued/running/completed/failed/cancelled), role, prompt, working_dir, max_turns, timeout, permission_mode, allowed_tools, created_at, started_at, completed_at, output, exit_code, git_diff, error.
- Execution: asyncio.Queue drained by N worker coroutines. `asyncio.to_thread(subprocess.run, ...)` for non-blocking subprocess.
- `allowed_tools` passed as `--allowedTools comma,separated` to claude CLI.
- Job IDs: `str(uuid.uuid4())`.

## Complexity

High
