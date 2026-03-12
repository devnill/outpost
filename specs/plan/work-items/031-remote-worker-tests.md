# Work Item 031: Remote Worker Daemon Tests

## Objective

Create a test suite for the remote worker daemon covering all API endpoints, authentication, concurrency, and job lifecycle.

## Acceptance Criteria

1. `POST /jobs` with valid API key and payload returns 201 with job_id.
2. `POST /jobs` with missing/wrong `X-API-Key` returns 401.
3. `POST /jobs` with prompt > 100KB returns 400, no job queued.
4. `GET /jobs/{job_id}` for unknown job_id returns 404.
5. `GET /jobs/{job_id}` for completed job returns output, exit_code, duration_ms, git_diff (may be null if mocked).
6. `GET /jobs` returns array; newly submitted job appears in list.
7. `DELETE /jobs/{job_id}` for queued job returns 204; subsequent GET shows status "cancelled".
8. `DELETE /jobs/{job_id}` for completed job returns 409.
9. `GET /health` returns expected fields including active_jobs and queued_jobs counts.
10. Concurrency: submitting more jobs than max_concurrency queues excess; health endpoint shows correct active_jobs count.
11. All tests mock `subprocess.run` to avoid real claude invocations.
12. All tests pass with `pytest mcp/remote-worker/test_server.py`.

## File Scope

- create: `mcp/remote-worker/test_server.py`

## Dependencies

030 (remote worker daemon must exist).

## Implementation Notes

- Use `httpx.AsyncClient` with FastAPI's test client (`app` imported from server).
- Reset job store between tests via a fixture (same pattern as session-spawner's `_reset_globals`).
- Mock `subprocess.run` to return a configurable CompletedProcess.
- Mock `git diff` subprocess call separately from the main claude call.
- Test client sets `X-API-Key` header from a test constant.

## Complexity

Medium
