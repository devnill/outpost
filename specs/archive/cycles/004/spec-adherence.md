# Spec Adherence Review — Cycle 4

**Review Date**: 2026-03-20
**Scope**: Full codebase re-verification after Cycle 3 PASS. No new incremental reviews exist; cycle 3 incremental reviews are at `specs/archive/cycles/003/incremental/`.

---

## Verdict: Pass

No critical or significant adherence failures found. Three minor deviations exist; two carry forward from prior cycles with documented rationale.

---

## Adherence Failures (Critical)

None.

---

## Adherence Failures (Significant)

None.

---

## Adherence Failures (Minor)

### MA1: token_usage Omitted (Not Null) in Normal-Path spawn_session Response

**Policy**: Observability P-3 — "When token usage cannot be extracted from session output, token_usage is explicitly set to null in log entries and status responses. Fields are never silently omitted."

**Violation**: In the normal (non-timeout) response path at `mcp/session-spawner/server.py:582–583`, `token_usage` is only added to the response when it is not None:

```python
if outcome_token_usage is not None:
    response["token_usage"] = outcome_token_usage
```

When extraction fails (e.g., `output_format` is "text" or JSON parse fails), `token_usage` is absent from the response entirely rather than set to `null`. The timeout path at line 567 correctly emits `"token_usage": null`, making the two paths inconsistent with each other and with P-3.

### MA2: Architecture Job-States Table Not Updated After WI-017

**Location**: `specs/plan/architecture.md:223`

**What it says**: `| cancelled | Cancelled while queued |`

**What the implementation does**: WI-017 extended cancellation to running jobs. `mcp/remote-worker/server.py:260–284` handles `status == "running"` in `cancel_job`, terminating the process and setting `status = "cancelled"`. The state is now reachable from both `queued` and `running`. WI-016 (Update Architecture Document) did not update this description, and WI-017's incremental review did not flag this gap.

### MA3: OUTPOST_TIMEOUT Listed in Architecture Env Var Table But Not Implemented

**Location**: `specs/plan/architecture.md:304` lists `OUTPOST_TIMEOUT | session-spawner | Default session timeout | 600`

**Implementation**: No code in `mcp/session-spawner/server.py` reads `OUTPOST_TIMEOUT`. Timeout is a per-call parameter defaulting to `DEFAULT_TIMEOUT = 600`. This deviation is documented at `specs/domains/session-lifecycle/decisions.md` (D-11) and `specs/archive/cycles/002/decision-log.md`, but the architecture table itself was never corrected. The table is the definitive reference and remains incorrect.

---

## Undocumented Additions

These carry forward unchanged from `specs/archive/cycles/003/spec-adherence.md` (U1–U3).

### U1: team_name and exec_instructions Parameters in spawn_session

**Location**: `mcp/session-spawner/server.py:106–116` (inputSchema), lines 261–262, 433–437 (implementation)

`spawn_session` accepts `team_name` (propagated via `OUTPOST_TEAM_NAME` env var) and `exec_instructions` (prepended to prompt; propagated via `OUTPOST_EXEC_INSTRUCTIONS`). Neither appears in architecture Section 3 spawn_session input schema. Risk: low.

### U2: output_format Parameter in spawn_session

**Location**: `mcp/session-spawner/server.py:100–105` (inputSchema), lines 260, 412–413 (implementation)

Allows callers to choose `json`, `text`, or `stream-json`. Architecture Section 3 spawn_session input does not list `output_format`. Risk: low.

### U3: In-Memory Session Registry and stderr Status Table

**Location**: `mcp/session-spawner/server.py:1027` (`_session_registry`), lines 538–540, 1044–1133

An in-memory list accumulates every session entry and an ASCII table prints to stderr after each spawn. Session-lifecycle policy P-2 is explicitly marked "provisional — under review" with the conflict recorded at D-8. Risk: low per prior cycle assessments.

---

## Full Adherence (Confirmed)

### Tool Schemas

All four tool schemas in `mcp/session-spawner/server.py:54–237` match architecture Section 3:
- `spawn_session`: required `prompt`, `working_dir`; all optional fields present with correct types.
- `spawn_remote_session`: required `prompt`, `working_dir`; optional `worker_name`, `role`, `max_turns`, `timeout`, `permission_mode`, `allowed_tools`.
- `poll_remote_job`: required `job_id`, optional `worker_name`.
- `list_remote_workers`: no inputs.

### spawn_session Output Schema

Response includes `output`, `exit_code`, `session_id`, `duration_ms`, `error` on both paths. Timeout path includes `timed_out: true` and `token_usage: null`. Truncation fields (`output_truncated`, `full_output_path`) present conditionally. All architecture-mandated fields present. (See MA1 for minor null-vs-omit on `token_usage` in the normal path.)

### Job State Machine — All 5 States Reachable

In `mcp/remote-worker/server.py`:
- `queued`: line 196 (at creation)
- `running`: line 390 (worker coroutine)
- `completed`: line 371 (exit_code == 0)
- `failed`: line 371 (exit_code != 0), line 401 (exception)
- `cancelled`: line 257 (from queued), line 262 (from running)

Race condition guard at line 369 prevents `_process_job` from overwriting a cancelled status.

### Role System — Caller-Wins Override

`mcp/session-spawner/server.py:295–308` applies caller-wins for `allowed_tools`, `model`, `max_turns`, `permission_mode` in local sessions. Lines 755–764 apply the same pattern for remote sessions. Role constraints propagated to POST /jobs payload.

### Auth Enforcement — All Endpoints Including /health

`mcp/remote-worker/server.py:123–139` registers HTTP middleware that runs on every request before any handler, including `GET /health` at line 145. Remote-dispatch P-3 satisfied.

### Environment Variable Names

All env vars in use match the architecture table exactly:
- Session-spawner: `OUTPOST_MAX_DEPTH` (line 970), `OUTPOST_MAX_CONCURRENCY` (line 962), `OUTPOST_SAFE_ROOT` (line 354), `OUTPOST_REMOTE_WORKERS` (line 980)
- Remote-worker: `IDEATE_WORKER_API_KEY` (line 101), `IDEATE_WORKER_MAX_CONCURRENCY` (line 106), `IDEATE_WORKER_PORT` (line 421), `IDEATE_WORKER_BASE_DIR` (line 112)

### Remote Worker API Endpoints

All five endpoints defined in architecture Section 4 are present: `GET /health` (line 145), `POST /jobs` (line 159), `GET /jobs` (line 199), `GET /jobs/{job_id}` (line 216), `DELETE /jobs/{job_id}` (line 248).

### Role Definitions

`mcp/roles/default-roles.json` defines all four architecture roles (`worker`, `reviewer`, `manager`, `proxy-human`) with correct allowed_tools assignments.

### Guiding Principles

| Principle | Evidence |
|-----------|---------|
| GP-1 Session Isolation | Isolated env dict per spawn, `session-spawner/server.py:432–435` |
| GP-2 Explicit State Management | JSONL logging via `_log_entry`, opt-in via `OUTPOST_LOG_FILE`, `server.py:1033–1041` |
| GP-3 Graceful Degradation | All remote handlers catch exceptions and return structured errors, `server.py:802–813` |
| GP-4 Transparency/Observability | stderr status table, JSONL log, `/health` endpoint exposing job counts |
| GP-5 Configurable Dispatch | `spawn_session` (local) and `spawn_remote_session` (remote) share prompt/working_dir interface |
| GP-6 Protocol Compliance | All tools use MCP `Tool` schema with `name`, `description`, `inputSchema` |
| GP-7 Resource Bounds | `DEFAULT_MAX_OUTPUT_BYTES=50_000`, `MAX_PROMPT_BYTES=100_000`, semaphore, `server.py:41–48` |
| GP-8 Role-Based Sessions | Caller-wins at lines 295–308 (local) and 755–764 (remote) |
| GP-9 Depth Limits | Hard enforcement before spawn at `server.py:381–399`; server-side cap at line 378 |
| GP-10 Result Integrity | Git diff captured post-execution, `remote-worker/server.py:291–306` |
| GP-11 Stateless Server | No MCP-level persistent state between calls |
| GP-12 Minimal Dependencies | stdlib + aiohttp + mcp (spawner); FastAPI + uvicorn + pydantic (worker) |

### Domain Policy Compliance

| Policy | Status |
|--------|--------|
| session-lifecycle P-1 (working dir isolation) | Satisfied |
| session-lifecycle P-2 (filesystem-only state) | Provisional conflict — `_session_registry` in-memory; policy marked "provisional — under review" per D-8 |
| session-lifecycle P-3 (resource limits enforced) | Satisfied — all four limits (concurrency, timeout, output size, prompt size) enforced |
| session-lifecycle P-4 (role constraints at spawn time) | Satisfied for local sessions; see code-quality S1 for remote system_prompt gap |
| session-lifecycle P-5 (depth enforcement is hard) | Satisfied — error before session creation |
| session-lifecycle P-6 (restart does not lose visibility) | Satisfied — no running-job state in spawner |
| remote-dispatch P-1 (worker failures don't crash orchestrator) | Satisfied |
| remote-dispatch P-2 (HTTP/REST only) | Satisfied |
| remote-dispatch P-3 (all endpoints require API key) | Satisfied — middleware covers all routes |
| remote-dispatch P-4 (working_dir validated against base) | Satisfied |
| remote-dispatch P-5 (job queue in-memory only) | Satisfied |
| observability P-1 (every lifecycle event logged) | Satisfied |
| observability P-2 (status queries return complete info) | Satisfied |
| observability P-3 (absent token data is null) | Minor violation in normal path — see MA1 |
