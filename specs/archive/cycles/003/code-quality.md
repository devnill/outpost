## Verdict: Fail

Two new significant findings. Prior cycle S1 (git diff subprocess leak) and P7-1 (unbounded job_queue) verified fixed.

## Critical Findings

None.

## Significant Findings

### S1: TOCTOU race between `job_queue.full()` check and `job_queue.put()` allows queue overflow
- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:201-210`
- **Issue**: The 429 gate (`job_queue.full()`) and the enqueue (`await job_queue.put(job_id)`) are not atomic. Two concurrent `POST /jobs` requests can both pass the `full()` check simultaneously. Because `asyncio.Queue.put()` blocks when full, the second coroutine suspends indefinitely at the put, holding a live connection open rather than returning 429.
- **Impact**: Under concurrent load at capacity, the 429 back-pressure mechanism fails silently. Requests block instead of being rejected, consuming connection resources and violating the API contract.
- **Suggested fix**: Replace `await job_queue.put(job_id)` with `job_queue.put_nowait(job_id)` wrapped in `try/except asyncio.QueueFull`, raising HTTPException 429 in the except block. This makes the check-and-enqueue atomic within the single-threaded asyncio event loop.

### S2: `_handle_cancel_remote_job` returns on first connection error, masking real result
- **File**: `/Users/dan/code/outpost/mcp/session-spawner/server.py:1031-1039`
- **Issue**: The second pass in `_handle_cancel_remote_job` returns immediately on any `_status in ("conflict", "error")`. Connection errors (`_status: "error"`) are included. With multiple workers, a network failure on any worker that never owned the job returns a "Connection error for worker X" instead of "job not found" — preempting the not-found check.
- **Impact**: A transient network failure on any non-owning worker produces an incorrect error message, masking the true result.
- **Suggested fix**: Separate connection errors from 409 conflict. Only return immediately on 409 conflict (which is definitive from a specific worker). Collect connection errors and surface them only if no other resolution is found.

## Minor Findings

### M1: TimeoutExpired path omits stderr from error message (carry-forward)
- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:408`

### M3: `_handle_spawn_remote_session` does not validate `working_dir` before HTTP calls (carry-forward)
- **File**: `/Users/dan/code/outpost/mcp/session-spawner/server.py:736-810`

### M4: `_semaphore` created at module scope before event loop (carry-forward)
- **File**: `/Users/dan/code/outpost/mcp/session-spawner/server.py:1195`
- **Issue**: `asyncio.Semaphore(DEFAULT_CONCURRENCY)` assigned at module level. On Python 3.10+ safe, but a caller that imports the module without running `main()` re-introduces the original compatibility risk.

### M5: conftest module alias dependency undocumented (carry-forward)
- **File**: `/Users/dan/code/outpost/mcp/remote-worker/test_server.py:19`, `/Users/dan/code/outpost/mcp/session-spawner/test_server.py:20`

## Unmet Acceptance Criteria

None.
