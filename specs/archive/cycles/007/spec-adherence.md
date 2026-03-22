# Spec Adherence Review — Cycle 7

## Architecture Adherence

**session-spawner MCP server**

- Location: `mcp/session-spawner/server.py` — correct per architecture section 1.
- All five tools from architecture section 3 are present: `spawn_session` (line 57), `spawn_remote_session` (line 143), `poll_remote_job` (line 198), `cancel_remote_job` (line 225), `list_remote_workers` (line 252). Confirmed in `list_tools()` handler.
- `call_tool()` dispatch routes all five tools correctly.
- Roles loaded at startup from `mcp/roles/default-roles.json` per architecture section 5 — confirmed.
- Depth tracking via `OUTPOST_SPAWN_DEPTH` / `OUTPOST_MAX_DEPTH` per architecture section 6 — confirmed.
- Concurrency semaphore via `OUTPOST_MAX_CONCURRENCY` — confirmed.
- `OUTPOST_SAFE_ROOT` enforcement present.

**remote-worker HTTP daemon**

- Location: `mcp/remote-worker/server.py` — correct per architecture section 1.
- All five REST endpoints present: `GET /health`, `POST /jobs`, `GET /jobs`, `GET /jobs/{job_id}`, `DELETE /jobs/{job_id}`.
- Job states queued / running / completed / failed / cancelled all present per architecture section 4.
- Authentication via `X-API-Key` header and `IDEATE_WORKER_API_KEY` env var confirmed.

**Role definitions**

- `mcp/roles/default-roles.json` contains all four architecture-specified roles: `worker`, `reviewer`, `manager`, `proxy-human`.
- Roles are static JSON loaded at startup — constraint 10 met.

**Manager agent**

- `agents/manager.md` exists per architecture section 1 agent table.

**Deviation D1: `max_jobs` absent from `list_remote_workers` output**

- Expected (architecture.md section 3): `list_remote_workers` returns worker status objects including a `max_jobs` field.
- Actual: `_fetch_worker_health` in session-spawner returns `name`, `url`, `status`, `active_jobs`, `queued_jobs`, `max_concurrency` but does not include `max_jobs`. The remote-worker `/health` endpoint does return `max_jobs`, so the data is available but not forwarded.
- Evidence: `mcp/session-spawner/server.py:678-695` — `max_jobs` key absent from returned dict. `mcp/remote-worker/server.py:166` — `max_jobs` present in health response.
- Severity: Minor (field in architecture spec; implementation omits it from the aggregated output).

---

## Guiding Principle Adherence

**Principle 1 — Session Isolation**: Adhered. Each child process gets its own env copy; no shared mutable state passed between sessions (`server.py:461`).

**Principle 2 — Explicit State Management**: Minor deviation. `_session_registry` (line 1189) is in-memory. Disk logging via `OUTPOST_LOG_FILE` is opt-in with no default. Pre-existing open question Q-4; documented deviation D-8.

**Principle 3 — Graceful Degradation**: Adhered. Timeout handling captures partial output. Job failures recorded without crashing the worker. Worker health failures return structured error responses.

**Principle 4 — Transparency and Observability**: Adhered. Every job state transition logged. Lifecycle events written to JSONL. Status table printed after each spawn. Job responses include `created_at`, `started_at`, `completed_at`, `duration_ms`.

**Principle 5 — Configurable Dispatch**: Adhered. `spawn_session` uses local subprocess; `spawn_remote_session` uses HTTP POST. Both share the same input interface parameters.

**Principle 6 — Protocol Compliance**: Adhered. Unknown tool names raise `McpError` with code -32601. Tool schemas use proper JSON Schema types. Async tool execution follows MCP conventions.

**Principle 7 — Resource Bounds**: Adhered. Concurrency semaphore enforced. Output truncated at 50KB. Prompt size rejected above 100KB. Timeouts enforced with SIGKILL. All defaults are non-unlimited.

**Principle 8 — Role-Based Sessions**: Adhered. All four roles defined in `default-roles.json`. Role constraints applied to both local and remote sessions. Role `allowed_tools`, `system_prompt`, `max_turns`, and `permission_mode` all applied with caller-wins semantics.

**Principle 9 — Depth Limits**: Adhered. Server-side max depth read from `OUTPOST_MAX_DEPTH`. Caller cannot exceed server limit (`min()` at line 407). Depth incremented in child process environment. Error returned at limit.

**Principle 10 — Result Integrity**: Adhered. `git_diff` captured after job completion. Exit codes preserved in all response paths. Truncation flagged explicitly with `output_truncated: true` and `full_output_path`. `error` field preserved from stderr.

**Principle 11 — Stateless Server**: Minor deviation. Same as Principle 2. `_session_registry` accumulates in memory between tool calls. The remote-worker's in-memory job store is documented scope (constraint 16). The session-spawner in-memory registry is the unresolved gap.

**Principle 12 — Minimal Dependencies**: Adhered. session-spawner uses `mcp`, `aiohttp`, and stdlib. remote-worker uses `fastapi`, `uvicorn`, `pydantic`, and stdlib. No heavy frameworks beyond these.

---

## Principle Violations

None.

The Principle 2 / Principle 11 in-memory session registry deviation is a pre-existing documented open question (Q-4) carried forward from cycle 2. It does not rise to a violation because the deviation is explicitly documented in decisions.md (D-8) and the constraint conflict (C4) is acknowledged as an unresolved design question requiring user input.

---

## Interface Consistency

**`spawn_session`**: All architecture-specified inputs present. Implementation also includes undocumented additions `max_depth`, `output_format`, `team_name`, `exec_instructions` (see Undocumented Additions below). Output schema matches architecture: `output`, `exit_code`, `session_id`, `duration_ms`, `error`, `timed_out`, `token_usage`, `output_truncated`, `full_output_path`.

**`spawn_remote_session`**: Inputs match architecture exactly. Output (`job_id`, `worker_name`, `status`) matches architecture exactly.

**`poll_remote_job`**: Inputs match. Output is a superset of architecture spec (also passes through `created_at`, `started_at`, `completed_at`) — consistent with the job result structure.

**`cancel_remote_job`**: Inputs match. Output includes `worker_name` not in architecture output description — superset, no breaking change.

**`list_remote_workers`**: Inputs match. Output is missing `max_jobs` field specified in architecture section 3 — this is deviation D1.

**Remote worker REST API**: All five endpoints implemented with correct methods, paths, and status codes. Job state machine (queued → running → completed/failed/cancelled) correctly implemented.

---

## Minor Deviations

**MD1: `max_jobs` absent from `list_remote_workers` output** (same as D1 above)
Fix: add `"max_jobs": data.get("max_jobs")` at `mcp/session-spawner/server.py:684`.

**MD2: In-memory session registry** (pre-existing, OQ Q-4 since cycle 2)
Requires user decision to resolve formally.

**MD3: `proc.terminate()` without `ProcessLookupError` guard** (pre-existing, OQ-011 since cycle 6)
`mcp/remote-worker/server.py` `cancel_job` endpoint — HTTP 500 risk if process exits between lock release and terminate call. Two-line try/except fix.

**MD4: `IDEATE_WORKER_MAX_JOBS` absent from architecture.md Section 8 table** (pre-existing, OQ-020 since cycle 6)
One table row addition to `specs/plan/architecture.md`.

---

## Undocumented Additions

**U1: `max_depth` caller input on `spawn_session`** (`server.py:79-83`)
Allows callers to supply a depth limit. `min()` guard prevents exceeding server limit. Technically inconsistent with constraint 9 ("clients cannot override this limit") even though the server limit cannot be exceeded. Low risk.

**U2: `output_format` input** (line 100)
Not in architecture section 3. Extends functionality without breaking existing behavior.

**U3: `team_name` input** (line 106)
Advisory label, not in architecture.

**U4: `exec_instructions` input** (line 110)
Injects content into every child prompt. Not in architecture. Low to moderate risk — allows arbitrary content injection, but only by authorized callers.

**U5: `OUTPOST_LOG_FILE` JSONL logging** (line 1196)
Not in architecture section 8 configuration table. Opt-in; no behavior change when unset.

**U6: `OUTPOST_ROLES_FILE` / `~/.outpost/roles.json` user role override** (lines 1082-1101)
Not described in architecture section 5 or section 8. Backward-compatible extension of the role system.

---

## Verdict

**Pass.**

No principle violations. One minor interface deviation (D1: `max_jobs` absent from `list_remote_workers` output). Three pre-existing tracked minor open items (MD2/MD3/MD4) — all known from prior cycles, none new. Six undocumented additions (U1–U6) that extend functionality beyond what is in the architecture spec without causing harm, but several should be added to architecture sections 5 and 8 for completeness. The implementation faithfully covers all architecture-specified interfaces and enforces all stated constraints.
