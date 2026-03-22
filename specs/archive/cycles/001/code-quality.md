## Verdict: Fail

There are significant findings affecting correctness and resource safety.

## Critical Findings

None.

## Significant Findings

### S1: `_run_claude_job` mutates shared `JobRecord` fields outside the lock
- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:380-384`
- **Issue**: The `FileNotFoundError` handler writes `record.status`, `record.exit_code`, `record.error`, and `record.completed_at` directly without holding `job_store_lock`. These same fields are read and written by `cancel_job` (lines 267–282) and `get_job` (lines 228–256) under the lock. The `record` object is shared mutable state; writes from a thread (via `asyncio.to_thread`) without the lock are a data race with any concurrent HTTP handler.
- **Impact**: Under concurrent load, a cancel or status-poll request can observe a partially-updated record — for example, `status == "failed"` but `exit_code` still `None` — producing incorrect API responses or assertion failures in callers.
- **Suggested fix**: Move the mutation out of `_run_claude_job` and into the caller `_process_job`, which already holds the lock in its `result is None` branch. Make `_run_claude_job` return `(None, 1, "claude CLI not found...")` as a normal tuple so that `_process_job` can apply it under the lock:
  ```python
  # In _run_claude_job, replace the FileNotFoundError handler:
  except FileNotFoundError:
      return None, 1, "claude CLI not found on PATH. ..."
  # In _process_job, the existing result-is-None branch becomes:
  # output, exit_code, error = result  — and normal lock-protected assignment follows.
  ```
  The `return None` cancel-while-starting guard at line 391 must be kept distinct (it intentionally skips all further record updates).

### S2: `asyncio.to_thread` timeout path calls `proc.communicate()` without a timeout
- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:397-398`
- **Issue**: After `proc.kill()` is called on a `TimeoutExpired` exception, the code calls `proc.communicate()` with no timeout argument. If the killed process holds open file descriptors or does not exit promptly (e.g., zombie grandchildren), this call can block indefinitely inside the worker thread, consuming a thread from the `to_thread` pool forever and eventually exhausting concurrency.
- **Impact**: Under adversarial or buggy subprocess conditions, all worker threads can be permanently blocked, halting job processing.
- **Suggested fix**: Pass a short timeout to the second `communicate()` call and handle the resulting `TimeoutExpired`:
  ```python
  try:
      stdout_bytes, stderr_bytes = proc.communicate(timeout=10)
  except subprocess.TimeoutExpired:
      stdout_bytes, stderr_bytes = b"", b""
  ```

### S3: `_session_registry` grows without bound
- **File**: `/Users/dan/code/outpost/mcp/session-spawner/server.py:572`
- **Issue**: Every call to `spawn_session` appends an entry to the module-level `_session_registry` list. There is no eviction, size cap, or flush mechanism. In a long-running server processing thousands of sessions, this list consumes unbounded memory.
- **Impact**: Steady-state memory growth leading to OOM in long-running deployments. Also violates guiding principle 11 (Stateless Server) and principle 7 (Resource Bounds).
- **Suggested fix**: Cap the registry at a fixed size (e.g., the last 1,000 entries) using a `collections.deque(maxlen=1000)`, or write entries only to the JSONL log file and drop the in-memory list entirely since it is only used for `_print_status_table`. The status table can operate on the last N entries from the deque.

### S4: `_handle_cancel_remote_job` fans out sequentially, not concurrently
- **File**: `/Users/dan/code/outpost/mcp/session-spawner/server.py:977`
- **Issue**: When `worker_name` is not specified, the cancel handler loops over workers one at a time with `for w in workers_to_try`. In contrast, `_handle_poll_remote_job` uses `asyncio.gather` for concurrent fan-out. With N workers and a 30-second timeout each, cancellation can take up to N×30 seconds.
- **Impact**: The MCP tool call blocks for an extended period when the job is on the last worker in the list or when early workers are slow. This is especially acute in failure scenarios where the user is trying to abort a runaway job.
- **Suggested fix**: Mirror the poll handler's approach using `asyncio.gather` with a helper coroutine, then inspect the first 204 result and return it immediately.

## Minor Findings

### M1: Timeout path in `_run_claude_job` silently drops `stderr`
- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:398-400`
- **Issue**: After killing a timed-out process, `stderr_bytes` is captured from the second `communicate()` call but is never included in the returned tuple or stored on the record. The timeout error message at line 400 does not include any stderr content, which is the most diagnostic output for understanding why the process timed out.
- **Suggested fix**: Include stderr in the error field:
  ```python
  partial_stderr_str = stderr_bytes if isinstance(stderr_bytes, str) else stderr_bytes.decode("utf-8", errors="ignore")
  return partial_stdout, -1, f"Job timed out after {record.timeout}s. Partial stderr: {partial_stderr_str[:2000]}"
  ```

### M2: `_session_registry` is process-wide mutable state that violates the Stateless Server principle
- **File**: `/Users/dan/code/outpost/mcp/session-spawner/server.py:1195`
- **Issue**: The guiding principles state "no persistent state between tool calls; filesystem only." The `_session_registry` list is in-process mutable state that persists across tool calls. While not a crash risk, it is an architectural inconsistency.
- **Suggested fix**: As noted in S3, replace with a bounded deque or eliminate in-memory accumulation entirely.

### M3: `spawn_remote_session` role resolution does not validate `working_dir` before making HTTP calls
- **File**: `/Users/dan/code/outpost/mcp/session-spawner/server.py:712-757`
- **Issue**: `_handle_spawn_remote_session` does not validate that `working_dir` exists before making health check HTTP requests to select a worker and submitting the job. The `working_dir` validation is delegated to the remote worker's `/jobs` endpoint (which returns HTTP 400). The caller receives a generic `"Remote worker returned HTTP 400"` error rather than a clear client-side message. Compare with `spawn_session` which validates `working_dir` locally before any subprocess call.
- **Suggested fix**: Add a `Path(arguments["working_dir"]).is_dir()` check at the start of `_handle_spawn_remote_session` and return a structured error matching the format used by `spawn_session` before making any HTTP calls.

### M4: No test for `_run_claude_job` `FileNotFoundError` path in remote-worker
- **File**: `/Users/dan/code/outpost/mcp/remote-worker/test_server.py`
- **Issue**: The `FileNotFoundError` branch (lines 379–384 of `server.py`) that sets `record.status = "failed"` and returns early has no corresponding test case. This is the code path identified in S1.
- **Suggested fix**: Add a test that patches `subprocess.Popen` to raise `FileNotFoundError` and asserts that the resulting job has `status == "failed"` and a non-None `error` field referencing the missing CLI.

### M5: `conftest.py` files register modules under aliases that diverge from the package naming
- **File**: `/Users/dan/code/outpost/mcp/remote-worker/conftest.py:18`, `/Users/dan/code/outpost/mcp/session-spawner/conftest.py:18`
- **Issue**: `remote-worker/server.py` is registered as `remote_worker_server` and `session-spawner/server.py` as `session_spawner_server`. The integration test (`test_integration.py`) imports the same files under different aliases (`remote_worker` and `session_spawner`). This means the same source file is loaded twice as two separate module objects. Mutations made to `worker_mod.job_store` in the integration test do not affect the `remote_worker_server` module object used by unit tests, which is correct isolation — but if a future test accidentally imports the wrong alias, it will see inconsistent state with no error.
- **Suggested fix**: Consolidate aliases: use a single name per module (e.g., `remote_worker`) in both conftest files and integration test, enforced by a single shared conftest at the `mcp/` level.

## Unmet Acceptance Criteria

None.