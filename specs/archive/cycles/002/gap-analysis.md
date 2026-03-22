# Gap Analysis — Outpost Cycle 2

**Date**: 2026-03-21
**Scope**: Incremental — gaps introduced by or not addressed by WI-028 through WI-033. Baseline: `specs/archive/cycles/001/gap-analysis.md`.

---

## Missing Requirements from Interview

None.

The cycle 2 work items (WI-028 through WI-033) addressed only code fixes and documentation. No new interview requirements were introduced in the 2026-03-21 refinement interview beyond deferring OQ-025 and the undocumented `spawn_session` architecture additions, both of which are carried forward from the prior cycle as open questions and documented below.

---

## Unhandled Edge Cases

### EC1: Git diff output has no size limit

- **Component**: `mcp/remote-worker/server.py` — `_capture_git_diff` (lines 332–347)
- **Scenario**: A job runs in a workspace with a large number of generated or binary-adjacent files. `git diff HEAD` produces hundreds of kilobytes or more of output.
- **Current behavior**: The full stdout of `git diff HEAD` is stored in `JobRecord.git_diff` and returned verbatim in `GET /jobs/{job_id}` responses and `poll_remote_job` results. No truncation or byte cap exists.
- **Expected behavior**: `git_diff` output should be capped at a reasonable size (the 50KB default used for job output would be consistent), with the same truncation pattern used elsewhere — truncate, write full output to a file, return a note in the field or a `git_diff_truncated` flag.
- **Severity**: Minor
- **Recommendation**: Defer — the scenario requires a workspace with very large diffs, which is uncommon in the target use case. First identified as EC3 in cycle 7 gap analysis. No regression introduced in cycle 2.

---

### EC2: `_session_registry` grows without bound in long-lived session-spawner processes

- **Component**: `mcp/session-spawner/server.py` — line 572 (`_session_registry.append(entry)`)
- **Scenario**: A long-running Claude Code session makes hundreds or thousands of `spawn_session` calls. Every call appends one entry to `_session_registry` and `_print_status_table` renders the entire list to stderr after each call.
- **Current behavior**: The list grows indefinitely. Memory use and stderr table size grow linearly with spawn count.
- **Expected behavior**: An eviction policy (e.g., keep last N entries) should bound the list.
- **Severity**: Minor
- **Recommendation**: Defer — bounded in practice by Claude Code session lifetime, which is shorter than continuous server lifetime. No eviction mechanism was introduced in cycle 2. First identified as EC4 in cycle 7 gap analysis.

---

## Incomplete Integrations

### II1: No integration test for `list_remote_workers` against a live uvicorn instance

- **Interface**: `list_remote_workers` MCP tool → `GET /health` → remote-worker health endpoint
- **Producer**: `mcp/remote-worker/server.py` — `/health` endpoint (line 155)
- **Consumer**: `mcp/session-spawner/server.py` — `_handle_list_remote_workers` / `_fetch_worker_health` (lines 704–709, 655–701)
- **Gap**: `mcp/test_integration.py` contains five tests covering job CRUD and role propagation. None of them call `_handle_list_remote_workers` or exercise the `GET /health` path end-to-end. The `max_jobs` field added to the health response by WI-031 is tested only via a unit test against the mocked health data; the full chain from MCP tool call through live HTTP to uvicorn is untested.
- **Severity**: Minor
- **Recommendation**: Defer — `_fetch_worker_health` is unit-tested in `mcp/session-spawner/test_server.py` and the health endpoint is tested in `mcp/remote-worker/test_server.py`. The integration gap is real but the risk of undetected regression is low given the individual unit coverage. First identified as II2 in cycle 7 gap analysis.

---

### II2: `cancel_remote_job` success response `worker_name` field undocumented in session-spawner README

- **Interface**: `cancel_remote_job` MCP tool response → caller
- **Producer**: `mcp/session-spawner/server.py` — line 990 returns `{"job_id": job_id, "status": "cancelled", "worker_name": w["name"]}`
- **Consumer**: `mcp/session-spawner/README.md` — documents the response as `{"job_id": "...", "status": "cancelled"}` with no `worker_name` field (lines 170–175)
- **Gap**: The implementation returns a richer response than the README documents. A caller reading the README will not know `worker_name` is available. WI-032 (documentation sweep) did not address this discrepancy.
- **Severity**: Minor
- **Recommendation**: Defer — no behavioral impact; the implementation is richer than documented, not poorer. First identified as II1 in cycle 7 gap analysis.

---

## Missing Infrastructure

### MI1: Architecture Section 2 data flow diagram still shows `subprocess.run` for remote worker

- **Category**: Documentation
- **Gap**: `specs/plan/architecture.md` Section 2 ("Remote Job Dispatch"), line 74, shows `subprocess.run(["claude", "--print", prompt])` as the mechanism the remote worker uses to execute jobs. WI-031 and WI-033 changed the remote-worker implementation to use `subprocess.Popen` + `communicate()` to enable running-job cancellation. WI-032 updated only the Section 8 environment variable table and did not touch the data flow diagram.
- **Impact**: The diagram misrepresents the actual execution model. A developer reading the architecture to understand how cancellation works will find `subprocess.run` — a blocking call with no process handle — which directly contradicts the cancellation mechanism that WI-028/WI-033 implemented.
- **Severity**: Minor
- **Recommendation**: Defer — the discrepancy is cosmetic at the architecture diagram level; the module-level docstring in `mcp/remote-worker/server.py` accurately describes the implementation. However, this should be corrected in the next documentation pass alongside the deferred `spawn_session` architecture additions.

---

### MI2: Architecture missing six `spawn_session` parameters and four environment variables

- **Category**: Documentation
- **Gap**: `specs/plan/architecture.md` Section 3 (`spawn_session` tool definition) lists eight input parameters. The implementation and session-spawner README document fourteen: the six additional parameters are `max_depth`, `output_format`, `team_name`, `exec_instructions`, `role` (inline dict variant), and the `model` parameter's full semantics. Section 8 (environment variables) is missing `OUTPOST_LOG_FILE`, `OUTPOST_ROLES_FILE`, `OUTPOST_EXEC_INSTRUCTIONS`, and `OUTPOST_TEAM_NAME`, all of which are implemented, documented in the session-spawner README, and used in production code paths.
- **Impact**: The architecture is an incomplete reference for any consumer of the tool API. Callers relying only on the architecture document are unaware of observability (`OUTPOST_LOG_FILE`), role customization (`OUTPOST_ROLES_FILE`), and execution instruction propagation (`exec_instructions`, `OUTPOST_EXEC_INSTRUCTIONS`).
- **Severity**: Minor
- **Recommendation**: Defer — the user explicitly deferred this in the 2026-03-21 refinement interview: "Defer — come back to this in the next refinement cycle." The session-spawner README is authoritative and complete. Track as a known open item for the next architecture documentation pass.

---

## Implicit Requirements

### IR1: `FileNotFoundError` response from session-spawner is missing standard schema fields

- **Expectation**: A reasonable caller expects every `spawn_session` error response to include the same set of fields. All other error return paths in `call_tool` — prompt-too-large (lines 345–362), invalid working-dir (lines 367–380), safe-root violation (lines 387–404), depth-exceeded (lines 412–428) — return a six-field object: `output`, `exit_code`, `session_id`, `duration_ms`, `error`, and a role-error path also returns these six fields.
- **Current state**: The `FileNotFoundError` path introduced by WI-029 (`mcp/session-spawner/server.py` lines 485–489) returns only two fields: `error` and `exit_code`. `output`, `session_id`, and `duration_ms` are absent.
- **Gap**: `output`, `session_id`, and `duration_ms` are missing from the `FileNotFoundError` response. Any orchestrator that destructures the response expecting all six standard fields will receive `None` or `KeyError` on this path. The inconsistency was first identified as G2 in the cycle 001 gap analysis and not addressed by WI-029.
- **Severity**: Minor
- **Recommendation**: Defer — the `FileNotFoundError` path indicates an installation problem, not a normal operation failure. Callers encountering it are unlikely to be processing `session_id` or `duration_ms`. However, schema consistency has value and the fix is a one-line addition. Recommend addressing in the next code-hygiene pass.

---

## Open Questions (carried forward)

**OQ-025 (deferred by user in 2026-03-21 refinement interview)**: In-memory session registry vs. filesystem-state design decision. The interview (Session 1, key design decision #1) states "Filesystem state: All session tracking uses files, not in-memory state." The current implementation uses an in-memory Python list (`_session_registry` in `mcp/session-spawner/server.py` line 1195) with opt-in JSONL disk writing behind `OUTPOST_LOG_FILE`. The manager agent's `session-registry.json` input contract cannot be satisfied by the current implementation. Requires a binding user decision: either add a default `OUTPOST_LOG_FILE` path to make state durable by default, or formally update the interview record and constraints to accept the in-memory design.

**Undocumented `spawn_session` architecture additions (deferred by user in 2026-03-21 refinement interview)**: `max_depth`, `output_format`, `team_name`, `exec_instructions`, `OUTPOST_LOG_FILE`, `OUTPOST_ROLES_FILE`, `OUTPOST_EXEC_INSTRUCTIONS`, and `OUTPOST_TEAM_NAME` are absent from `specs/plan/architecture.md` Sections 3 and 8. All are implemented and documented in `mcp/session-spawner/README.md`. User explicitly deferred architecture documentation to the next refinement cycle.