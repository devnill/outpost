# Work Item 034: Remote Dispatch Tests

## Objective

Add tests to `mcp/session-spawner/test_server.py` covering the three new remote dispatch tools.

## Acceptance Criteria

1. `spawn_remote_session` submits to the configured worker and returns job_id and worker_name.
2. `spawn_remote_session` with no workers configured returns structured error, no HTTP call made.
3. `poll_remote_job` for a queued job returns status "queued".
4. `poll_remote_job` for a completed job returns output and git_diff.
5. `list_remote_workers` returns one entry per configured worker with health data.
6. `list_remote_workers` marks an unreachable worker as status "unreachable", does not raise.
7. Worker selection (no `worker_name`): two workers configured, one with more active jobs — test verifies the less-loaded one is selected.
8. Auth error from remote (401 response) returns descriptive error to tool caller.
9. All existing 33 tests still pass.
10. New tests mock `aiohttp.ClientSession` HTTP calls (no real network calls).
11. All tests pass with `pytest mcp/session-spawner/test_server.py`.

## File Scope

- modify: `mcp/session-spawner/test_server.py`

## Dependencies

033 (remote dispatch tools must be implemented).

## Implementation Notes

- Mock `aiohttp.ClientSession` with `unittest.mock.AsyncMock` to simulate HTTP responses.
- Create a helper to build mock health responses and job status responses.
- `_reset_globals` fixture must also reset the module-level worker config list and aiohttp session.

## Complexity

Medium
