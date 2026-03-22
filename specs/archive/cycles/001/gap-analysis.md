## Verdict: No critical gaps

All cycle 7 significant and minor findings were addressed in cycle 8. One persistent significant gap from the interview remains open pending a user decision; one new minor gap was introduced in cycle 8.

## Critical Gaps

None.

## Significant Gaps

### G1: Filesystem-based session state not implemented — user decision still pending

- **Missing**: A binding resolution to the open question (Q-4 in `specs/domains/session-lifecycle/questions.md`) of whether `_session_registry` should write to disk by default. The interview (Session 1, key design decision #1) states: "Filesystem state: All session tracking uses files, not in-memory state." The current implementation uses an in-memory Python list (`_session_registry` in `mcp/session-spawner/server.py:1195`) with opt-in JSONL disk writing behind `OUTPOST_LOG_FILE`.
- **Impact**: On server restart, all session history is lost. The manager agent's `artifact_dir/status/session-registry.json` input contract cannot be satisfied by the current implementation. Seven cycles have passed without this decision being put to the user.
- **Evidence**: `specs/domains/session-lifecycle/questions.md` Q-4 open since cycle 2. `specs/domains/session-lifecycle/decisions.md` D-8 marks it provisional. Architecture.md Guiding Principle 2 ("Explicit State Management") and Constraint 4 ("Filesystem-Based State") both call for durable state. Prior gap analyses in cycles 1 and 7 both deferred without user input.

## Minor Gaps

### G2: `FileNotFoundError` response in session-spawner is missing required schema fields

- **Missing**: `output`, `session_id`, and `duration_ms` fields in the `FileNotFoundError` error response from `spawn_session`. All other error return paths in `call_tool` (prompt-too-large, invalid working-dir, safe-root violation, depth-exceeded) return a consistent six-field object: `output`, `exit_code`, `session_id`, `duration_ms`, `error`. The `FileNotFoundError` path introduced in cycle 8 (`mcp/session-spawner/server.py` lines 485–489) returns only `error` and `exit_code`.
- **Impact**: Any caller that destructures the spawn_session response expecting `output`, `session_id`, or `duration_ms` will receive `None`/`KeyError` on the FileNotFoundError path. Orchestrators that log `duration_ms` will silently skip timing on this error case.
- **Evidence**: `mcp/session-spawner/server.py` lines 485–489 vs. lines 345–362 (prompt-too-large reference path showing the full six-field shape).

### G3: `cancel_remote_job` success response `worker_name` field undocumented in session-spawner README

- **Missing**: The `worker_name` field in the `cancel_remote_job` success response. `mcp/session-spawner/README.md` shows `{"job_id": "...", "status": "cancelled"}` but the implementation at `mcp/session-spawner/server.py` line 990 returns `{"job_id": job_id, "status": "cancelled", "worker_name": w["name"]}`.
- **Impact**: Callers reading the README will not know `worker_name` is available. No behavioral impact; implementation is richer than documented.
- **Evidence**: First identified as II1 in cycle 7 gap analysis, deferred.

### G4: Git diff output in remote-worker has no size limit

- **Missing**: A byte cap on `_capture_git_diff` output. The full `git diff HEAD` stdout is stored in `JobRecord.git_diff` and returned verbatim in `GET /jobs/{job_id}` responses and `poll_remote_job` results. No truncation exists.
- **Impact**: A large workspace change produces a diff that can exhaust remote-worker memory and overflow the MCP response context. Uncommon in the target use case but possible with generated files or large binary assets.
- **Evidence**: `mcp/remote-worker/server.py` lines 332–347. First identified as EC3 in cycle 7, deferred as uncommon.

### G5: `_session_registry` grows without bound in long-lived session-spawner processes

- **Missing**: An eviction policy for `_session_registry`. Every `spawn_session` call appends one entry and nothing removes entries. `_print_status_table` reprints the full list after every call.
- **Impact**: Memory growth and increasingly large stderr table output in long-running server processes. Bounded in practice by Claude Code session lifetime, but not by design.
- **Evidence**: `mcp/session-spawner/server.py` line 572 (`_session_registry.append(entry)`); no eviction path exists. First identified as EC4 in cycle 7, deferred.

### G6: No integration test for `list_remote_workers` against a real uvicorn instance

- **Missing**: An integration test exercising `_handle_list_remote_workers` against the live uvicorn server in the `worker_server` fixture. The five existing tests in `mcp/test_integration.py` cover job CRUD and role propagation but not the health endpoint path.
- **Impact**: The `max_jobs` field forwarding added in cycle 8 (WI-031) is untested end-to-end. `_fetch_worker_health` is unit-tested in isolation; the full chain from `list_remote_workers` MCP tool through `GET /health` to response is not covered.
- **Evidence**: `mcp/test_integration.py` — five tests, none call `_handle_list_remote_workers`. First identified as II2 in cycle 7, deferred.

## Open Questions

**OQ-025 (deferred by user in 2026-03-21 refinement interview)**: In-memory session registry vs. filesystem-state design decision. Requires a binding decision: either add a default `OUTPOST_LOG_FILE` path to make state durable by default, or formally update the interview record and constraints to accept the in-memory design. Until resolved, the manager agent's `session-registry.json` input contract remains unsatisfiable.

**Undocumented `spawn_session` architecture additions (deferred by user in 2026-03-21 refinement interview)**: `max_depth`, `output_format`, `team_name`, `exec_instructions`, `OUTPOST_LOG_FILE`, and `OUTPOST_ROLES_FILE` are absent from `architecture.md` Section 3 (`spawn_session` tool definition). All are implemented and documented in the session-spawner README. User explicitly deferred architecture documentation to the next refinement cycle.
