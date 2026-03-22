# Spec Adherence Review — Cycle 001

---

## Architecture Deviations

### D1: OUTPOST_TIMEOUT Listed in Architecture Env Var Table But Not Implemented

- **Expected**: Architecture lists `OUTPOST_TIMEOUT` as configurable.
- **Actual**: No code reads `OUTPOST_TIMEOUT`; timeout is a per-call parameter defaulting to 600s.
- **Evidence**: Architecture row annotated `*(not implemented)*`. Pre-existing acknowledged deviation; accepted state.

### D2: session-spawner Uses subprocess.run; Architecture Diagram Shows subprocess.Popen

- **Expected**: Architecture section 2 data flow shows `subprocess.Popen(...)`.
- **Actual**: `mcp/session-spawner/server.py` uses `subprocess.run(...)`.
- **Evidence**: Intentional — session-spawner does not need in-flight cancellation. Remote-worker correctly uses `subprocess.Popen`. Diagram is illustrative, not binding.

### D3: In-Memory Session Registry Contradicts Filesystem-Only State Constraint

- **Expected**: Principle 11 and Constraint 4 require no in-memory state persisting between tool calls.
- **Actual**: `_session_registry: list[dict] = []` grows across tool calls in session-spawner.
- **Evidence**: Registry is purely observational (status table printing), never drives functional decisions. Pre-existing acknowledged gap since cycle 2.

---

## Unmet Acceptance Criteria

All active work items (028–033) have incremental review verdicts of Pass or Pass (with rework). No unmet acceptance criteria.

---

## Principle Violations

None.

---

## Principle Adherence Evidence

- Principle 1 — Session Isolation: Each spawn receives a copied environment dict with only controlled keys modified. No shared mutable objects across process boundaries.

- Principle 2 — Explicit State Management: Cross-session coordination uses filesystem artifacts when `OUTPOST_LOG_FILE` configured. In-memory `_session_registry` is observational only. Remote-worker job store permitted by Constraint 16.

- Principle 3 — Graceful Degradation: Timeout expired captures partial output as structured error. `FileNotFoundError` caught in both servers and returned as structured error. All remote HTTP failures return structured error dicts.

- Principle 4 — Transparency and Observability: Every job state transition logged to stderr in remote-worker. Job GET responses include `created_at`, `started_at`, `completed_at`, `duration_ms`. Session-spawner prints status table and writes JSONL when `OUTPOST_LOG_FILE` set.

- Principle 5 — Configurable Dispatch: `spawn_session` uses `subprocess.run` locally; `spawn_remote_session` uses HTTP POST to `/jobs`. Both accept identical parameters.

- Principle 6 — Protocol Compliance: Unknown tool names raise `McpError` with JSON-RPC code -32601. All five tools declared with proper JSON Schema structure.

- Principle 7 — Resource Bounds: Concurrency capped by `asyncio.Semaphore` (default 5). Output truncated at 50 KB. Prompts rejected above 100 KB in both servers. Timeout enforced with kill.

- Principle 8 — Role-Based Sessions: All four roles in `mcp/roles/default-roles.json`. Role `allowed_tools`, `system_prompt`, `max_turns`, `permission_mode` applied with caller-wins semantics for local and remote sessions.

- Principle 9 — Depth Limits: Max depth read from `OUTPOST_MAX_DEPTH`. Caller `max_depth` clamped to `min(caller, server)`. Error returned before spawn when depth exceeded.

- Principle 10 — Result Integrity: `git_diff` captured after remote job completion. Exit codes preserved including timeout (exit_code -1). Truncation flagged with `output_truncated: true` and `full_output_path`.

- Principle 11 — Stateless Server: No persistent cross-invocation state affects functional outcomes. Remote-worker in-memory job store permitted by Constraint 16. `_session_registry` is observational only.

- Principle 12 — Minimal Dependencies: session-spawner imports `mcp`, `aiohttp`, stdlib only. remote-worker imports `fastapi`, `uvicorn`, `pydantic`, stdlib only.

---

## Undocumented Additions (carried forward, unchanged risk)

- U1: `max_depth` input parameter on spawn_session — Risk: Low (server-side clamp enforced)
- U2: `output_format` input parameter on spawn_session — Risk: Low (defaults to json)
- U3: `team_name` input parameter on spawn_session — Risk: Low (observational only)
- U4: `exec_instructions` input parameter on spawn_session — Risk: Medium (modifies child prompt)
- U5: `OUTPOST_LOG_FILE` logging — Risk: Low (opt-in, no effect when unset)
- U6: `OUTPOST_ROLES_FILE` user role override — Risk: Low (extends, does not replace built-in roles)

---

## Summary

Implementation is fully adherent to architecture and guiding principles as documented. Three pre-existing deviations (D1–D3) are acknowledged and accepted. Six undocumented additions (U1–U6) carry forward with unchanged risk assessments. No unmet acceptance criteria. All 12 guiding principles are satisfied.
