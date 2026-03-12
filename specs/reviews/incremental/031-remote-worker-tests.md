## Verdict: Pass

All acceptance criteria met after rework. 32 tests pass.

## Critical Findings

### C1: `@pytest.mark.asyncio` decorators redundant with asyncio_mode = "auto"
- **File**: `mcp/remote-worker/test_server.py` (all test functions)
- **Issue**: All 27 test functions decorated with `@pytest.mark.asyncio` despite pyproject.toml setting `asyncio_mode = "auto"`, which makes the decorator redundant and misleading.
- **Impact**: Decorator noise; if asyncio_mode is ever removed, tests silently degrade.
- **Suggested fix**: Remove all `@pytest.mark.asyncio` decorators from test functions. Fixed in rework.

## Significant Findings

### S1: Concurrency test spin-loop races against job_store status
- **File**: `mcp/remote-worker/test_server.py:477`
- **Issue**: The spin-loop waits on `started_count` (incremented when `asyncio.to_thread` is called) but the health assertion reads `status == "running"` from `job_store`. The two conditions are not synchronized — a job could have incremented `started_count` before the `_worker` coroutine updates `record.status = "running"`.
- **Impact**: Occasional race condition causing the assertion `active_jobs == max_concurrency` to fail.
- **Suggested fix**: Poll the health endpoint directly in the spin-loop. Fixed in rework.

### S2: `asyncio.get_event_loop()` deprecated in Python 3.10+
- **File**: `mcp/remote-worker/test_server.py:477-478`
- **Issue**: `asyncio.get_event_loop().time()` inside an async function where a running loop exists; use `asyncio.get_running_loop()` instead.
- **Impact**: DeprecationWarning in Python 3.10+; will be an error in a future version.
- **Suggested fix**: Replace with `asyncio.get_running_loop()`. Fixed in rework.

### S3: `_execute_job` duplicates execution logic from `_worker`
- **File**: `mcp/remote-worker/test_server.py:49-82`
- **Issue**: `_execute_job` replicates the `asyncio.to_thread`, timing, git_diff capture, and status-update logic from `_worker`, creating a maintenance hazard. Changes to execution logic in `server.py` will not automatically be reflected in tests.
- **Impact**: Tests may pass while the production execution path has bugs.
- **Suggested fix**: Extract the execution body from `_worker` into a testable `_process_job` coroutine in `server.py`; have `_execute_job` call `worker._process_job`. Fixed in rework.

## Minor Findings

### M1: `gather` teardown lacks yield point
- **File**: `mcp/remote-worker/test_server.py:496`
- **Issue**: After `await asyncio.gather(*worker_tasks, return_exceptions=True)`, no `await asyncio.sleep(0)` is issued, so cancelled coroutines do not fully unwind before the test exits.
- **Suggested fix**: Add `await asyncio.sleep(0)` after gather. Fixed in rework.

### M2: No test for cancelling a running job
- **File**: `mcp/remote-worker/test_server.py`
- **Issue**: DELETE /jobs/{job_id} with status `running` should return 409, but only `completed` and `failed` are tested.
- **Suggested fix**: Add `test_cancel_running_job_returns_409`. Fixed in rework.

### M3: No multi-byte UTF-8 boundary test
- **File**: `mcp/remote-worker/test_server.py`
- **Issue**: Prompt size limit is validated against byte length, but tests only use single-byte ASCII. A prompt with multi-byte characters could be under `MAX_PROMPT_BYTES` characters but over the byte limit.
- **Suggested fix**: Add test using 3-byte characters (e.g., `€`) at and just over the byte boundary. Fixed in rework.

## Unmet Acceptance Criteria

None.
