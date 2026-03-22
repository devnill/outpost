# Work Item 033: Local MCP Server — Remote Dispatch Tools

## Objective

Add three new MCP tools to the session-spawner server: `spawn_remote_session`, `poll_remote_job`, and `list_remote_workers`. These allow the orchestrating Claude session to dispatch work to configured remote worker daemons.

## Acceptance Criteria

1. `spawn_remote_session(prompt, working_dir, worker_name?, role?, max_turns?, timeout?, allowed_tools?, permission_mode?)` submits a job to a remote worker and returns immediately with `{"job_id": "<uuid>", "worker_name": "<name>", "status": "queued"}`. Does not block waiting for completion.
2. `poll_remote_job(job_id, worker_name?)` queries job status; returns `{"job_id", "status", "output"?, "git_diff"?, "exit_code"?, "duration_ms"?, "error"?}`. Status values: queued, running, completed, failed, cancelled.
3. `list_remote_workers()` returns `[{"name", "url", "status", "active_jobs", "queued_jobs", "max_concurrency"}]` where `status` is "ok", "unreachable", or "auth_error" based on a live `GET /health` call to each worker.
4. `IDEATE_REMOTE_WORKERS` env var: JSON array of `[{"name": string, "url": string, "api_key": string}]`. If unset or empty, all three tools return a structured error explaining no workers are configured.
5. When `worker_name` not specified in `spawn_remote_session`, select the worker with fewest active+queued jobs (from a live `GET /health` call to each worker). If all workers unreachable, return error.
6. Remote HTTP calls use `aiohttp` with a 30-second connection timeout.
7. `spawn_remote_session` sends `role` parameter to remote if provided; remote daemon's job payload includes role field.
8. Auth header `X-API-Key` set from the matching worker's `api_key` config for all remote calls.
9. All three tools exposed via `list_tools()` with full parameter documentation.
10. `IDEATE_REMOTE_WORKERS` parsing error (invalid JSON) logs a warning at startup; all three tools return error responses.

## File Scope

- modify: `mcp/session-spawner/server.py`

## Dependencies

030 (to know the remote API shape), 032 (role parameter flows through to remote).

## Implementation Notes

- Add `aiohttp` to `mcp/session-spawner/requirements.txt`.
- Worker config parsed at `main()` startup from `IDEATE_REMOTE_WORKERS`. Stored as module-level list.
- `aiohttp.ClientSession` created once and reused (module-level, initialized in `main()`).
- `spawn_remote_session` maps to `POST {worker_url}/jobs` with job payload.
- `poll_remote_job` maps to `GET {worker_url}/jobs/{job_id}`.
- `list_remote_workers` calls `GET {worker_url}/health` for each configured worker; catches exceptions to set status "unreachable".
- Worker selection (no name specified): call health on all workers concurrently (`asyncio.gather`), pick the one with lowest `active_jobs + queued_jobs`. On tie, pick first in config order.
- Job payload sent to remote: `{prompt, working_dir, role?, max_turns, timeout, permission_mode, allowed_tools?}`.

## Complexity

Medium
