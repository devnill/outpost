# Gap Analysis — Cycle 7

This is a capstone review of the full project state after cycles 1–6. No work items were executed in cycle 7; this review examines the complete implementation against the interview transcript, architecture, and all prior decisions.

---

## Missing Requirements from Interview

### MR1: `cancel_remote_job` absent from root README tool list

- **Interview reference**: Interview Session 1 — core components section describes session-spawner as the MCP server providing the primary user-facing tool surface.
- **Current state**: `/Users/dan/code/outpost/README.md` Usage section lists four tools: `spawn_session`, `spawn_remote_session`, `poll_remote_job`, `list_remote_workers`. The `cancel_remote_job` tool (added in WI-019) is not listed.
- **Gap**: A user reading the root README to evaluate outpost's capabilities will not discover that remote job cancellation is available via MCP. The session-spawner README and architecture.md both include it correctly; only the root entry point omits it.
- **Severity**: Minor
- **Recommendation**: Address now — one-line addition to `/Users/dan/code/outpost/README.md`. The root README is the first document a new user reads; omitting a tool from the top-level list creates a permanent discoverability gap.

### MR2: Filesystem-based session state not implemented as required by interview design decision

- **Interview reference**: Interview Session 1 — key design decision #1: "Filesystem state: All session tracking uses files, not in-memory state."
- **Current state**: `_session_registry` in `/Users/dan/code/outpost/mcp/session-spawner/server.py` is an in-memory Python list. JSONL disk logging is opt-in via `OUTPOST_LOG_FILE` with no default path. Session history is lost on server restart. Documented as provisional deviation in session-lifecycle `decisions.md` (D-8) and an open question in `questions.md` (Q-4) since cycle 2.
- **Gap**: Six cycles have passed without resolving whether the in-memory implementation is a formal deviation from the interview's stated design decision or a requirement that remains unimplemented. The open question (Q-4) has never been surfaced to the user for decision.
- **Severity**: Significant
- **Recommendation**: Defer — this is a design decision requiring user input. The finding should be surfaced in the next refinement interview: either add a default `OUTPOST_LOG_FILE` path to make state durable by default, or formally accept the in-memory design and update the interview record and constraints.

### MR3: Root README configuration section omits most environment variables

- **Interview reference**: Interview Session 1 — "Filesystem state" and "Safe root enforcement" imply operators need to configure the server via environment variables.
- **Current state**: `/Users/dan/code/outpost/README.md` Configuration section documents only `OUTPOST_REMOTE_WORKERS`. Seven of the eight session-spawner environment variables and all six remote-worker variables are absent from the root README.
- **Gap**: Users relying on the root README as the configuration reference will not discover the security (`OUTPOST_SAFE_ROOT`), observability (`OUTPOST_LOG_FILE`), or depth-limiting (`OUTPOST_MAX_DEPTH`) variables.
- **Severity**: Minor
- **Recommendation**: Address now — at minimum, add a note pointing to the component READMEs for complete configuration, or reproduce the key security and observability variables. Documentation-only, low risk.

---

## Unhandled Edge Cases

### EC1: `proc.terminate()` called without guard against already-exited process

- **Component**: `/Users/dan/code/outpost/mcp/remote-worker/server.py` (`cancel_job` endpoint)
- **Scenario**: Between `job_store_lock` release and `proc.terminate()`, the subprocess exits naturally. On POSIX, `Popen.terminate()` raises `ProcessLookupError` against an already-dead PID. This propagates as an unhandled HTTP 500. Tracked as OQ-011 since cycle 6.
- **Severity**: Minor
- **Recommendation**: Address now — two-line try/except fix. Deferred for three cycles without scheduling.

### EC2: `claude` binary not on PATH raises unhandled `FileNotFoundError`

- **Component**: `mcp/session-spawner/server.py` (subprocess.run), `mcp/remote-worker/server.py` (`_run_claude_job`)
- **Scenario**: Most common new-user failure — `claude` CLI not installed or not on PATH in the MCP server's process environment.
- **Current behavior**: Session-spawner: `FileNotFoundError` surfaces as an MCP protocol error with Python traceback. Remote-worker: job marked `failed` with raw exception text. Neither is actionable. Tracked as Q-6 in session-lifecycle/questions.md since cycle 3.
- **Expected behavior**: Both components catch `FileNotFoundError` at the subprocess call site and return: "claude CLI not found on PATH."
- **Severity**: Significant
- **Recommendation**: Address now — most common onboarding failure mode. Tracked three cycles without resolution.

### EC3: Git diff output has no size limit

- **Component**: `mcp/remote-worker/server.py` (`_capture_git_diff`)
- **Scenario**: Large workspace changes produce a very large diff stored in memory and returned verbatim in job responses. No size cap. Tracked as Q-7.
- **Severity**: Minor
- **Recommendation**: Defer — scenario uncommon in target use case.

### EC4: `_session_registry` grows without bound in long-lived session-spawner processes

- **Component**: `mcp/session-spawner/server.py` (`_session_registry`)
- **Scenario**: Long-running server accumulates one entry per spawn call. Status table reprints full list after every spawn.
- **Severity**: Minor
- **Recommendation**: Defer — server restarts with each Claude Code session in practice, bounding registry size.

---

## Incomplete Integrations

### II1: `cancel_remote_job` success response `worker_name` field not documented in session-spawner README

- **Gap**: README documents `{"job_id": "...", "status": "cancelled"}` but implementation returns `{"job_id": ..., "status": "cancelled", "worker_name": ...}`. No harm; implementation is richer.
- **Severity**: Minor
- **Recommendation**: Defer — document in next documentation pass.

### II2: Integration tests do not cover `list_remote_workers` end-to-end

- **Gap**: Five integration tests cover job submission, polling, cancellation, role propagation, and 404 handling. No integration test exercises `GET /health` against a real uvicorn instance.
- **Severity**: Minor
- **Recommendation**: Defer — health endpoint is simple; unit tests provide adequate coverage.

---

## Missing Infrastructure

### MI1: `IDEATE_WORKER_MAX_JOBS` absent from `architecture.md` Section 8 environment variable table

- **Gap**: Added in WI-020, documented in remote-worker README and architecture.md health schema, but missing from the Section 8 reference table. Tracked as OQ-020 / MG1 since cycle 6.
- **Severity**: Minor
- **Recommendation**: Address now — one table row addition, no scheduling required.

### MI2: Both `conftest.py` files register under the same `sys.modules["server"]` key

- **Gap**: Second registration overwrites first. Any bare `import server` in either test file would import the wrong module. Tracked as OQ-021 / MG2 since cycle 6. No current test failure.
- **Severity**: Minor
- **Recommendation**: Defer — harmless under importlib-based test setup. Schedule for next test infrastructure pass.

### MI3: `CLAUDE.md` references a non-existent `requirements.txt` at repository root

- **Gap**: `CLAUDE.md` instructs `pip install -r requirements.txt` from the repository root. No root `requirements.txt` exists. The correct path is `mcp/session-spawner/requirements.txt`, which the root README correctly references. A developer following `CLAUDE.md` gets a `FileNotFoundError` before running any tests.
- **Severity**: Minor
- **Recommendation**: Address now — update `CLAUDE.md` to reference the correct path. One-line fix.

---

## Implicit Requirements

### IR1: Meaningful error message when `claude` binary is not on PATH

- **Gap**: Same as EC2. No component converts the missing-binary error into a user-readable message.
- **Severity**: Significant (same finding, different lens)

### IR2: Root README does not list `cancel_remote_job` as an available tool

- **Gap**: Same as MR1.
- **Severity**: Minor (same finding, different lens)

### IR3: No recovery guidance for worker restart (silent job loss)

- **Gap**: Remote-worker README notes "Jobs are lost if the server restarts" but provides no recovery guidance: no polling pattern to detect restart, no instruction to re-submit, no reference to `list_remote_workers` as a health check. Tracked as Q-1.
- **Severity**: Minor
- **Recommendation**: Defer — in-memory job store is a documented scope boundary (C16).

---

## Verdict

No critical gaps exist. Two significant gaps have been deferred without user input across multiple cycles: `FileNotFoundError` on missing `claude` binary (EC2/IR1, open since cycle 3) and the in-memory session registry versus the interview's filesystem-state design decision (MR2, open since cycle 2). Both require either a code fix or a formal user decision to close. Three minor gaps are documentation-only and can be resolved with single-line edits: `cancel_remote_job` missing from root README (MR1/IR2), stale `requirements.txt` path in `CLAUDE.md` (MI3), and `IDEATE_WORKER_MAX_JOBS` missing from architecture.md Section 8 (MI1). The `proc.terminate()` race (EC1) remains the one minor code gap with a known low-effort fix deferred for three cycles.
