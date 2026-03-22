## Verdict: Fail

The cycle 8 fixes are correctly implemented but one pre-existing race condition that was not addressed by this cycle leaves the cancel-while-starting path silently ineffective, and a false return type annotation on `_run_claude_job` creates a type-safety gap the cycle introduced.

## Critical Findings

None.

## Significant Findings

### S1: Cancel of a running job silently no-ops when the subprocess has not yet been assigned to the record

- **File**: `mcp/remote-worker/server.py:272-278`
- **Issue**: `cancel_job` reads `proc = record.process` while holding `job_store_lock`. `record.process` is assigned the `Popen` object at line 385, inside `_run_claude_job`, which executes in a thread started by `asyncio.to_thread`. The record's status is set to `"running"` at line 452 before the thread starts. There is a window between the lock release at line 455 and the assignment at line 385 in the thread where a DELETE request can arrive, find `record.status == "running"`, read `proc = record.process == None`, set `record.status = "cancelled"`, and return 204 — without ever signalling the process. The subprocess then continues running uninterrupted until it completes or times out.
- **Impact**: A caller that cancels a job immediately after submission receives a success response but no process is killed. The job continues consuming the worker's concurrency slot, CPU, and memory. The health endpoint will misreport load until the process finishes naturally.
- **Suggested fix**: In `_run_claude_job`, after `Popen` returns at line 372 and before assigning `record.process = proc` at line 385, check `record.status`: if it is already `"cancelled"`, call `proc.kill()` and return `None`. Alternatively, add a `cancel_requested` flag to `JobRecord` that `cancel_job` sets under the lock; `_run_claude_job` checks it after `Popen` returns.

## Minor Findings

### M1: `_run_claude_job` return type annotation is incorrect

- **File**: `mcp/remote-worker/server.py:350`
- **Issue**: The function is declared `-> tuple[str, int, str | None]` but returns bare `None` at line 384 in the `FileNotFoundError` branch. The actual return type is `tuple[str, int, str | None] | None`. The caller handles the `None` case correctly at line 410, so there is no runtime failure, but any type checker will report an error.
- **Suggested fix**: Change the annotation to `-> tuple[str, int, str | None] | None`.

### M2: `FileNotFoundError` response in session-spawner omits standard output fields

- **File**: `mcp/session-spawner/server.py:486-489`
- **Issue**: The `FileNotFoundError` handler returns `{"error": "...", "exit_code": 1}` only. Every other early-exit error response in `call_tool` includes the full standard shape: `output`, `session_id`, `duration_ms`, `timed_out`, `token_usage`. A caller that destructures the response expecting all standard fields will get a `KeyError`.
- **Suggested fix**: Return the full standard error shape: `{"output": "", "exit_code": 1, "session_id": "", "duration_ms": 0, "error": "...", "token_usage": None}`.

### M3: Timeout path in `_run_claude_job` discards captured stderr

- **File**: `mcp/remote-worker/server.py:389-393`
- **Issue**: After `subprocess.TimeoutExpired`, `proc.communicate()` returns `(stdout_bytes, stderr_bytes)`. `stderr_bytes` is captured but discarded. The session-spawner includes `partial_stderr[:1000]` in its equivalent timeout error. The inconsistency makes remote-worker timeout failures harder to diagnose.
- **Suggested fix**: Include decoded stderr in the error string: `f"Job timed out after {record.timeout}s. Partial stderr: {partial_stderr[:1000]}"`.

### M4: `_session_registry` in session-spawner grows without bound

- **File**: `mcp/session-spawner/server.py:572`
- **Issue**: Every `spawn_session` call appends to `_session_registry` and nothing ever removes entries. The remote-worker received LRU eviction in this cycle (WI-031). The session-spawner has no equivalent. In a long-running process handling thousands of sessions this list grows indefinitely.
- **Suggested fix**: Cap the list at a configurable size (e.g., `OUTPOST_MAX_REGISTRY_ENTRIES`, default 1000) by trimming oldest entries after each append.

### M5: Integration test patches auth via module attribute replacement instead of environment variable

- **File**: `mcp/test_integration.py:47`
- **Issue**: `worker_mod._get_api_key = lambda: "test-key"` replaces the module-level function. If the middleware is ever refactored to capture the key at startup, this patch would silently stop working. Using the environment variable is more resilient.
- **Suggested fix**: Replace with `patch.dict(os.environ, {"IDEATE_WORKER_API_KEY": "test-key"})` in the fixture.

## Suggestions

- **Extract the repeated UTC timestamp expression into a helper.** The expression `datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")` appears five times in `mcp/remote-worker/server.py`. A module-level `_utcnow_iso() -> str` function eliminates the repetition.

- **Type the `_http_session` module-level default as `Optional`.** `mcp/session-spawner/server.py:1198` uses `# type: ignore[assignment]` to assign `None` to an `aiohttp.ClientSession`-typed variable. Typing it as `_http_session: aiohttp.ClientSession | None = None` removes the suppression.

- **Add an integration test exercising the full health path through session-spawner.** `mcp/test_integration.py` has no test for `list_remote_workers` against a live server. A single integration test calling `_handle_list_remote_workers({})` against the running uvicorn instance would confirm the `max_jobs` forwarding path end-to-end.
