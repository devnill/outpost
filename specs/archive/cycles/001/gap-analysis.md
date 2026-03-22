# Gap Analysis — Outpost Cycle 1 (New brrr Session)

**Date**: 2026-03-22
**Scope**: Full project — all source files reviewed. This cycle's work items (WI-043–WI-046) were all test additions and minor bug fixes. Prior cycles addressed core functionality.

---

## Missing Requirements from Interview

### MR1: OUTPOST_TIMEOUT environment variable documented but never implemented

- **Interview reference**: Session 1 — "Timeout enforcement: Every session has a timeout." Architecture Section 8 lists `OUTPOST_TIMEOUT` with annotation "*(not implemented)*".
- **Gap**: The variable does not exist in code. D-11 settled per-call timeout as the final design. The table row is misleading.
- **Severity**: Minor
- **Recommendation**: Remove the row from architecture.md Section 8. D-11 is the decision record. One-line deletion.

### MR2: Session registry violates filesystem-state constraint by default

- **Interview reference**: Session 1 — "Filesystem state: All session tracking uses files." Guiding principle 2, constraint C4.
- **Current state**: `_session_registry` is `collections.deque(maxlen=1000)` in process memory. JSONL disk logging only active when `OUTPOST_LOG_FILE` is set; no default path.
- **Gap**: The filesystem-state requirement is not met by default. Session history is lost on restart unless operator configures `OUTPOST_LOG_FILE`. Deferred through six consecutive cycles.
- **Severity**: Minor (open question OQ-025 — explicitly deferred by user in 2026-03-21 refinement interview)
- **Recommendation**: Defer — user decision required to either (A) add a default `OUTPOST_LOG_FILE` path, or (B) amend constraint C4 to accept in-memory design. Carry forward as OQ-025.

---

## Unhandled Edge Cases

### EC1: git diff output has no size cap

- **Component**: `mcp/remote-worker/server.py` — `_capture_git_diff`
- **Scenario**: Job runs on a large workspace; `git diff HEAD` produces hundreds of KB. Full output stored and returned verbatim. No truncation.
- **Severity**: Minor
- **Recommendation**: Defer — uncommon in target use case. Apply same 50KB boundary as session output if this becomes a problem.

### EC2: OUTPOST_REMOTE_WORKERS parse failure indistinguishable from unset at tool-call time

- **Component**: `mcp/session-spawner/server.py`
- **Scenario**: Variable set but malformed JSON; server logs warning and sets `_remote_workers = []`. Tool calls return "No remote workers configured." — same message as variable not set.
- **Severity**: Minor
- **Recommendation**: Defer — startup log makes root cause diagnosable.

---

## Incomplete Integrations

### II1: No full MCP handler round-trip integration test

- **Interface**: `_handle_spawn_remote_session` → HTTP POST → worker executes → `_handle_poll_remote_job` → HTTP GET → result
- **Gap**: `test_job_lifecycle_running_to_completed` (WI-042) submits directly to `job_queue`, bypassing the MCP handler path. No test exercises the complete async round-trip through both MCP handlers.
- **Severity**: Minor
- **Recommendation**: Defer — component-level tests are thorough. Full end-to-end test requires a real or mock claude binary.

### II2: No integration test for `list_remote_workers` against a live uvicorn instance

- **Gap**: `mcp/test_integration.py` does not exercise the `GET /health` path end-to-end.
- **Severity**: Minor
- **Recommendation**: Defer — individual units tested.

---

## Missing Infrastructure

### MI1: Architecture Section 8 lists OUTPOST_TIMEOUT as "not implemented" — row should be removed

- **Gap**: "not implemented" annotation in the config table misleads operators who try to set the variable.
- **Severity**: Minor
- **Recommendation**: Address now — remove the row. D-11 settled per-call timeout as the final design.

### MI2: No graceful shutdown for local session subprocesses

- **Gap**: When MCP server is killed, active `spawn_session` subprocesses become orphaned. No SIGTERM handler terminates them before exit.
- **Severity**: Minor
- **Recommendation**: Defer — OS process tree cleanup handles this in most deployments.

---

## Implicit Requirements

### IR1: FileNotFoundError response from spawn_session inconsistent schema

- **Expectation**: All `spawn_session` error paths return `{output, exit_code, session_id, duration_ms, error, token_usage}`.
- **Current state**: `FileNotFoundError` path (lines ~487-490 of session-spawner server.py) returns only `{error, exit_code}` — missing `output`, `session_id`, `duration_ms`.
- **Gap**: Callers destructuring the full schema encounter `None` or `KeyError` on this path.
- **Severity**: Minor
- **Recommendation**: Address now — add `output: ""`, `session_id: ""`, `duration_ms: 0`, `token_usage: None` to the FileNotFoundError return dict. Introduced by WI-029, small oversight.

---

## Open Questions (carried forward)

**OQ-025**: In-memory session registry vs. filesystem-state design decision. The interview and constraint C4 require filesystem-only state. Current implementation uses in-memory `_session_registry` with opt-in JSONL. Requires binding user decision. Six cycles deferred.

**Undocumented architecture additions**: `max_depth`, `output_format`, `team_name`, `exec_instructions`, `OUTPOST_LOG_FILE`, `OUTPOST_ROLES_FILE` absent from architecture sections 3 and 8. Deferred by user in 2026-03-21 refinement interview.

---

## Summary

| ID | Title | Severity | Recommendation |
|----|-------|----------|----------------|
| MR2 | Session registry violates filesystem-state constraint by default (OQ-025) | Minor | Defer (user-deferred design decision) |
| IR1 | FileNotFoundError response missing standard schema fields | Minor | Address now |
| MR1 / MI1 | OUTPOST_TIMEOUT "not implemented" row in architecture | Minor | Remove from architecture |
| EC1 | git diff output unbounded | Minor | Defer |
| EC2 | REMOTE_WORKERS parse failure indistinguishable from unset | Minor | Defer |
| II1 | No full MCP handler round-trip integration test | Minor | Defer |
| II2 | No list_remote_workers integration test | Minor | Defer |
| MI2 | No graceful shutdown for local subprocesses | Minor | Defer |
