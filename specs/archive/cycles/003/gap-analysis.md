## Gap Analysis — Cycle 3

### Carried Forward

**CF1: No integration test covers actual subprocess execution** — **Significant** (elevated from Minor). All subprocess calls mocked. The integration test uses `lifespan="off"`, keeping all jobs in `"queued"` state. No test drives a job through `running → completed` with a real subprocess.

**CF2: No test for depth limit enforcement in remote sessions** — Minor. Remote path has no depth mechanism by design. Defer.

**CF3: No test for `_handle_cancel_remote_job` when all workers unreachable** — Minor. All-connection-error path untested. Defer.

**CF5: `spawn_remote_session` does not validate `working_dir` before HTTP calls** — Minor. Defer.

**CF7: No test for MCP tool schema validation (missing required fields)** — Minor. Defer.

**NG1: `(None, 1, msg)` FileNotFoundError sentinel ambiguous** — **Significant** (elevated from Minor). A zero-stdout exit-1 claude result is structurally indistinguishable from the FileNotFoundError sentinel in `_process_job`, causing it to be misrouted into the wrong failure branch.

**NG2: `_session_registry` maxlen hard-coded in two places** — Minor. Defer.

**NG3: `_evict_terminal_jobs_locked` warning branch untested** — Minor. Defer.

### Closed This Cycle

**CF4: No test for `spawn_remote_session` allowed_tools caller-wins override** — Closed. `test_spawn_remote_session_role_name_resolves_constraints` covers this.

**NG4: `proc.wait` mock assertion concern in cancel test** — Closed. Cancel test now uses real subprocess.

### New Gaps (cycle 3)

**NC1: `_capture_git_diff` post-kill `communicate()` has no timeout** — Minor. If SIGKILL doesn't terminate the process (pathological OS/container scenario), the drain `communicate()` blocks indefinitely. Defer.

**NC2: `job_queue.full()` / `put()` race has no test** — Minor. The concurrent race path is untested; the code reviewer's S1 finding addresses the fix, but the test coverage gap remains until fixed.

### Summary

CF4 and NG4 are closed. Two carry-forward gaps are elevated to Significant: CF1 (no integration test with real subprocess) and NG1 (ambiguous FileNotFoundError sentinel). Cycle 3 introduces two new minor gaps (NC1: unbounded post-kill drain, NC2: untested queue race). The most structurally important fix is NG1 — using a dedicated sentinel avoids silent misclassification of legitimate claude failures.
