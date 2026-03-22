# Code Quality Review — Cycle 5

## Verdict: Pass

All incremental reviews passed after rework; no cross-cutting correctness defects found across the cycle 5 changes.

## Critical Findings

None.

## Significant Findings

None.

## Minor Findings

### M1: Test suite cannot be run as `pytest mcp/` due to duplicate test_server.py basenames
- **Files**: `mcp/remote-worker/test_server.py`, `mcp/session-spawner/test_server.py`
- **Issue**: Both test files share the same basename with no `__init__.py`, causing a pytest import collision when running `pytest mcp/` from the project root. Each suite must be invoked separately (`pytest mcp/remote-worker/test_server.py` and `pytest mcp/session-spawner/test_server.py`). This predates cycle 5 but becomes more noticeable with the addition of `mcp/test_integration.py`.
- **Impact**: CI configuration and CLAUDE.md docs (`pytest` from root) don't work as written. Must run three separate pytest commands.
- **Suggested fix**: Add empty `__init__.py` files to `mcp/remote-worker/` and `mcp/session-spawner/` to make them packages, or rename test files to `test_remote_worker.py` and `test_session_spawner.py`.

### M2: `_evict_terminal_jobs_locked` relies on caller discipline for lock; asyncio.Lock has no `locked()` method
- **File**: `mcp/remote-worker/server.py` (the renamed eviction function)
- **Issue**: The function is named `_locked` to signal it must be called under `job_store_lock`, but there is no runtime assertion enforcing this. The assert suggested in the incremental review (`assert job_store_lock.locked()`) was not added because `asyncio.Lock` does not expose a reliable `.locked()` check that's safe in all coroutine contexts.
- **Impact**: Low — all three call sites correctly hold the lock. But a future caller could omit the lock silently.
- **Suggested fix**: Add a brief comment at the function definition: "# Must be called while holding job_store_lock."

### M3: Integration test `worker_server` fixture does not reset `_evict_terminal_jobs_locked` behavior
- **File**: `mcp/test_integration.py`
- **Issue**: The `worker_server` fixture clears `job_store` and drains the queue but does not reset `worker_mod._max_jobs`. Tests in `test_remote_worker.py` set this to small values (e.g., 2) and reset it in their fixture. If integration tests run after those unit tests in the same process, `_max_jobs` could be stale.
- **Impact**: Low — in practice each test file runs in a separate process. Risk is only if someone later combines test files.
- **Suggested fix**: Add `worker_mod._max_jobs = 1000` to the `worker_server` fixture teardown.
