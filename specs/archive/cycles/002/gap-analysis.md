## Gap Analysis — Cycle 2

### Carried Forward from Prior Cycle

**CF1: No integration test covers actual subprocess execution** — Minor. All subprocess calls mocked. Deliberate CI constraint. Defer.

**CF2: No test for depth limit enforcement in remote sessions** — Minor. Remote path has no depth mechanism by design. Accepted scope gap. Defer.

**CF3: No test for `_handle_cancel_remote_job` when all workers unreachable (connection error, not 404)** — Minor. All-connection-error path falls through to misleading "not found" error. Defer.

**CF4: No test for `spawn_remote_session` allowed_tools override (caller wins over role default)** — Minor. Logic present in code; only test missing. Defer.

**CF5: `spawn_remote_session` does not validate `working_dir` before HTTP calls** — Minor. Opaque 400 from remote rather than structured local error. Defer.

**CF6: `_handle_cancel_remote_job` 204-first-wins behavior** — CLOSED. Concurrent gather + fallback ordering verified by `test_cancel_remote_job_fan_out_is_concurrent` and `test_cancel_remote_job_exception_on_first_worker_success_on_second`.

**CF7: No test for MCP tool schema validation (missing required fields)** — Minor. Depends on MCP SDK behavior; may be handled before `call_tool` dispatch. Defer.

### New Gaps (introduced in cycle 2)

**NG1: `(None, 1, msg)` FileNotFoundError sentinel is ambiguous** — Minor. A legitimate claude invocation producing zero stdout and exiting non-zero (exit_code=1) would be misrouted into the FileNotFoundError branch in `_process_job`, skipping git_diff capture and using the wrong log message. Fix: use a dedicated sentinel object.
- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:428`

**NG2: `_session_registry` maxlen hard-coded in two places** — Minor. Test fixture (`test_server.py:61`) and server declaration (`server.py:1197`) both hard-code `maxlen=1000`. If a constant were introduced and changed, the fixture would diverge silently. Defer.

**NG3: `_evict_terminal_jobs_locked` warning branch untested** — Minor. The `len(terminal) < needed` warning path at lines 318–324 of `remote-worker/server.py` is never exercised. Observability gap only. Defer.

**NG4: `proc.wait` inside `asyncio.to_thread` in cancel path — mock assertion style diverges** — Minor. `test_cancel_running_job_process_already_exited_returns_204` uses a `MagicMock` with `wait.return_value = 0`, but `proc.wait` is invoked inside `asyncio.to_thread`, which the mock handles correctly. No assertion checks that `proc.wait` was called. Test quality concern. Defer.

### Summary

CF6 is fully closed. All other prior gaps remain as minor deferred items. Cycle 2 introduces four new minor gaps: an ambiguous FileNotFoundError sentinel (NG1, most actionable), a hard-coded maxlen in the test fixture (NG2), an untested eviction warning branch (NG3), and a minor mock assertion gap in the cancel test (NG4). None are critical or significant.
