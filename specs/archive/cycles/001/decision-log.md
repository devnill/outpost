# Decision Log — Cycle 8 (brrr Cycle 1)

**Cycle Date**: 2026-03-22
**Trigger**: Cycle 7 capstone review (2026-03-21) — 0 critical, 0 significant findings; long-deferred minor code fixes and documentation gaps
**Work Items Completed**: 5 (028–032)
**Final Review Verdicts**: code-quality Fail (1 significant, 4 minor); spec-adherence Pass; gap-analysis No critical gaps

---

## Decisions Made

### D1: Fix proc.terminate() race in cancel_job with OSError guard
- **When**: Planning — Refinement Interview (2026-03-21); Execution — WI-028
- **Decision**: Wrap `proc.terminate()` and `proc.kill()` in `cancel_job` with `try/except (ProcessLookupError, OSError)` to guard against a race where the process exits between the status check and the signal call.
- **Rationale**: Without the guard, a process that exits naturally between the status check and `proc.terminate()` raises an unhandled exception, returning HTTP 500. Identified as OQ-011 (cycle 3) and escalated to MD3 in cycle 7.
- **Source**: WI-028; specs/domains/remote-dispatch/questions.md Q-9; cycle 7 review MD3

### D2: Handle FileNotFoundError for missing claude binary in both servers
- **When**: Planning — Refinement Interview (2026-03-21); Execution — WI-029
- **Decision**: Catch `FileNotFoundError` from subprocess invocation in both servers. Session-spawner returns a structured MCP error response with exit_code=1. Remote-worker marks the job failed with an actionable message and exit_code=1.
- **Rationale**: Users see an internal exception stack trace instead of an actionable error when the `claude` binary is not on PATH. Identified as EC2 in cycle 3 and recommended for action in four consecutive cycles. User confirmed the approach in the 2026-03-21 refinement interview.
- **Source**: WI-029; specs/domains/session-lifecycle/questions.md Q-6; cycle 7 review OQ-024

### D3: Rename sys.modules keys in conftest to prevent test suite shadowing
- **When**: Execution — WI-030
- **Decision**: Rename `sys.modules` injection keys from the colliding `"server"` to suite-specific names (`"session_spawner_server"`, `"remote_worker_server"`) so that combined pytest runs from the repository root work correctly.
- **Rationale**: OQ-021 (cycle 5) identified that running pytest from the repository root caused the conftest from one suite to shadow the other's module under the same key. Fix enables combined `pytest` runs.
- **Source**: WI-030; cycle 7 review OQ-021

### D4: Add --cwd flag to _run_claude_job in remote-worker
- **When**: Planning — Refinement Interview (2026-03-21); Execution — WI-031
- **Decision**: Add `"--cwd", record.working_dir` to the `claude` CLI command in `_run_claude_job`, matching the session-spawner pattern. Also move `--allowedTools` before the prompt positional argument.
- **Rationale**: OQ-023 (cycle 7) identified that remote-worker set `cwd=` on the subprocess but did not pass `--cwd` to the Claude CLI. The Claude CLI uses `--cwd` for project root, CLAUDE.md loading, and trust boundary enforcement. A false docstring claimed the two patterns were equivalent.
- **Source**: WI-031; specs/domains/remote-dispatch/questions.md Q-18; cycle 7 code-quality M4

### D5: Forward max_jobs field in list_remote_workers output
- **When**: Planning — Refinement Interview (2026-03-21); Execution — WI-031
- **Decision**: Include `max_jobs` from the remote-worker `/health` response in the `list_remote_workers` output forwarded by session-spawner.
- **Rationale**: `max_jobs` is in architecture.md Section 3 and present in the worker health response. It was not being forwarded. This was OQ-022/D1 from cycle 7.
- **Source**: WI-031; specs/domains/remote-dispatch/questions.md Q-17; cycle 7 spec-adherence D1

### D6: Documentation sweep — cancel_remote_job, CLAUDE.md path, IDEATE_WORKER_MAX_JOBS
- **When**: Execution — WI-032
- **Decision**: Add `cancel_remote_job` to README tool list (5th, after `list_remote_workers`); correct stale `requirements.txt` path in CLAUDE.md; add `IDEATE_WORKER_MAX_JOBS` row to architecture.md Section 8.
- **Rationale**: Three documentation gaps deferred from prior cycles. The `cancel_remote_job` tool was added in cycle 5 but the root README was not updated. CLAUDE.md had a stale path. Architecture.md omitted an already-implemented env var.
- **Source**: WI-032; cycle 7 review OQ-020, OQ-026, OQ-027, OQ-028

### D7: Explicitly defer OQ-025 (in-memory session registry design decision)
- **When**: Planning — Refinement Interview (2026-03-21)
- **Decision**: OQ-025 deferred to a future refinement cycle. No code change in cycle 8.
- **Rationale**: User confirmed deferral. The question has been open since cycle 2 and requires a binding architectural decision.
- **Source**: Refinement interview 2026-03-21; specs/domains/session-lifecycle/questions.md Q-4

### D8: Explicitly defer architecture.md documentation of undocumented spawn_session additions
- **When**: Planning — Refinement Interview (2026-03-21)
- **Decision**: `max_depth`, `output_format`, `team_name`, `exec_instructions`, `OUTPOST_LOG_FILE`, `OUTPOST_ROLES_FILE` remain undocumented in architecture.md. Deferred to next refinement cycle.
- **Rationale**: All items are documented in the session-spawner README. Architecture.md update is a documentation cleanup. User explicitly deferred.
- **Source**: Refinement interview 2026-03-21; spec-adherence U1–U6 (cycle 7)

---

## Open Questions

### OQ-1: cancel-while-starting race leaves subprocess uninterrupted
- **Question**: When `cancel_job` is called for a job whose `record.process` is still `None` (Popen handle not yet assigned), cancellation sets status to `"cancelled"` and returns 204 without signalling the process. WI-028 fixed the OSError race on signal delivery; it did not fix this earlier window.
- **Impact**: Callers receive a success response but the job continues consuming the worker's concurrency slot, CPU, and memory.
- **Status**: open — new finding (code-quality S1, cycle 8)
- **Suggested fix**: In `_run_claude_job`, after `Popen` returns but before assigning `record.process`, check `record.status`; if already `"cancelled"`, kill the process and return `None`.

### OQ-2: FileNotFoundError response in session-spawner omits standard output fields
- **Question**: The `FileNotFoundError` handler in `spawn_session` returns `{"error": "...", "exit_code": 1}` only. All other early-exit error paths return a six-field shape including `output`, `session_id`, `duration_ms`.
- **Impact**: Orchestrators that destructure the response expecting standard fields will `KeyError` on this path.
- **Status**: open — new gap introduced by WI-029 (code-quality M2, gap-analysis G2)

### OQ-3: _run_claude_job return type annotation incorrect
- **Question**: Function annotated `-> tuple[str, int, str | None]` but returns bare `None` on the FileNotFoundError path. Actual type is `tuple[str, int, str | None] | None`.
- **Impact**: No runtime failure. Type checkers will report an error.
- **Status**: open — new gap (code-quality M1, cycle 8)

### OQ-4: Timeout path in remote-worker discards captured stderr
- **Question**: After `TimeoutExpired`, `stderr_bytes` is captured but discarded. Session-spawner includes `partial_stderr[:1000]` in its equivalent timeout error.
- **Impact**: Remote-worker timeout failures produce less diagnostic information than equivalent local session timeouts.
- **Status**: open — carried from cycle 7 (code-quality M3, cycle 8)

### OQ-5: _session_registry grows without bound in long-lived session-spawner processes
- **Question**: `_session_registry` has no eviction policy. Remote-worker received LRU eviction in cycle 5; session-spawner has no equivalent.
- **Impact**: Memory growth and increasingly large stderr status table output in long-running processes.
- **Status**: open — carried from cycle 7 as EC4 (code-quality M4, gap-analysis G5, cycle 8)

### OQ-6: No integration test for list_remote_workers against a live uvicorn instance
- **Question**: The five integration tests cover job CRUD and role propagation; none test `list_remote_workers`. The `max_jobs` forwarding added in WI-031 is untested end-to-end.
- **Impact**: A regression in `max_jobs` forwarding would not be caught by any test.
- **Status**: open — carried from cycle 7 as II2 (gap-analysis G6, cycle 8)

### OQ-7: cancel_remote_job worker_name field undocumented in session-spawner README
- **Question**: Success response includes `worker_name` but README shows only `{"job_id": "...", "status": "cancelled"}`.
- **Impact**: Callers reading the README will not know `worker_name` is available.
- **Status**: open — carried from cycle 7 as II1 (gap-analysis G3, cycle 8)

### OQ-8: Git diff output in remote-worker has no size limit
- **Question**: `_capture_git_diff` returns full `git diff HEAD` with no byte cap. Stored and returned verbatim.
- **Impact**: Large workspace changes can exhaust remote-worker memory and overflow MCP response context.
- **Status**: open — carried from cycle 7 as EC3 (gap-analysis G4, cycle 8)

### OQ-9: Filesystem-based session state not implemented — user decision pending (OQ-025)
- **Question**: `_session_registry` uses in-memory storage with opt-in JSONL (no default path). Interview and Constraint 4 both call for filesystem-based state. The manager agent's `session-registry.json` input contract cannot be satisfied.
- **Impact**: Session history lost on server restart. Manager agent observability contract unsatisfiable.
- **Status**: open — explicitly deferred by user in 2026-03-21 refinement interview (gap-analysis G1, cycle 8)

### OQ-10: Integration test patches auth via module attribute replacement
- **Question**: `mcp/test_integration.py:47` uses `worker_mod._get_api_key = lambda: "test-key"`. If middleware is refactored to capture the key at startup, this patch silently stops working.
- **Impact**: Latent test fragility — would produce auth failure rather than a clear setup error.
- **Status**: open — new observation (code-quality M5, cycle 8)

---

## Resolved Questions

### Q-17 / OQ-022: max_jobs absent from list_remote_workers output
- **Resolution**: WI-031 added `max_jobs` forwarding in `_fetch_worker_health`. Field is now included.
- **Source**: WI-031

### Q-18 / OQ-023: --cwd flag absent from remote-worker _run_claude_job
- **Resolution**: WI-031 added `"--cwd", record.working_dir` to the command. Docstring corrected. `--allowedTools` moved before prompt.
- **Source**: WI-031

### Q-16 / OQ-020: IDEATE_WORKER_MAX_JOBS absent from architecture.md Section 8
- **Resolution**: WI-032 added the row.
- **Source**: WI-032

### OQ-024: FileNotFoundError from missing claude binary raises unhandled exception
- **Resolution**: WI-029 caught the error in both servers. Actionable messages returned. Note: response shape in session-spawner still incomplete (OQ-2).
- **Source**: WI-029

### OQ-011 / MD3: proc.terminate() race raises HTTP 500
- **Resolution**: WI-028 wrapped both signal calls in `try/except (ProcessLookupError, OSError)`. HTTP 500 on natural-exit race is eliminated. Note: earlier window (process not yet assigned to record) remains open as OQ-1.
- **Source**: WI-028

### OQ-021: conftest sys.modules key collision between test suites
- **Resolution**: WI-030 renamed keys. Combined `pytest` from repository root now produces 124 passed, 0 errors.
- **Source**: WI-030

---

## Cross-References

### CR1: FileNotFoundError handling — incomplete fix
- code-quality M2 and gap-analysis G2 both identify that the session-spawner FileNotFoundError response omits standard output fields. OQ-024 is resolved (error is now caught); OQ-2 tracks the remaining schema incompleteness.

### CR2: cancel-while-starting race — two distinct windows
- WI-028 fixed the later window (process exits after status check, before `proc.terminate()`). code-quality S1 identifies the earlier window (process not yet assigned to record). These are two separate races. OQ-1 tracks the earlier one.

### CR3: Filesystem state vs. in-memory registry — converging pressure
- code-quality M4 (memory growth), spec-adherence Principle 2/11 (provisional violation), and gap-analysis G1 (manager agent contract) all observe the same root problem. Together they form a complete picture: the in-memory registry has concrete functional consequences that accumulate with each cycle of deferral.

### CR4: Documentation gaps closed vs. still open
- WI-032 resolved three documentation gaps (OQ-020, cancel_remote_job in README, CLAUDE.md path). spec-adherence confirms all three cycle-7 deviations are closed. gap-analysis G3 identifies one remaining documentation gap (cancel_remote_job worker_name field). The undocumented spawn_session additions (U1–U6) were explicitly deferred by the user.

---

## Summary

Cycle 8 (brrr Cycle 1) completed 5 work items addressing long-deferred minor code fixes and documentation gaps. All five passed incremental review. Combined test suite: 124 tests passing from the repository root.

**Spec-adherence**: Pass. All three cycle-7 tracked deviations closed. Pre-existing in-memory registry gap unchanged (D-8, provisional).

**Code-quality**: Fail. One significant finding (OQ-1, cancel-while-starting race) and four minor findings remain. The significant finding is a pre-existing structural issue outside this cycle's scope.

**Gap-analysis**: No critical gaps. One significant gap (OQ-9, filesystem state) explicitly deferred. Five minor gaps (OQ-2, OQ-5 through OQ-8), including one new gap introduced by this cycle.

**Open questions carried forward**: 10 (OQ-1 through OQ-10). One (OQ-9) requires user decision. One (OQ-8) requires user decision on scope. Eight are addressable by technical investigation.

**Resolved in this cycle**: 6 questions.
