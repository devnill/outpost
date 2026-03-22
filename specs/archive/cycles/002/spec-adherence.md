# Spec-Adherence Review — Outpost (Current State)

**Date**: 2026-03-21
**Scope**: Full cross-cutting adherence review — session-spawner, remote-worker, roles system, manager agent, plugin manifest
**Prior review carried forward**: `specs/archive/cycles/004/spec-adherence.md` (Verdict: Pass, three minor findings MA1–MA3)
**Incremental reviews in scope**: `specs/archive/incremental/` — items 028–033 (all Pass or Pass with rework)

---

## Verdict: Pass

No critical or significant adherence failures found. All three minor findings from the cycle 4 review (MA1, MA2, MA3) have been resolved. One minor deviation carries forward (OUTPOST_TIMEOUT annotated but not implemented). Three undocumented additions carry forward with unchanged low-risk assessment.

---

## Architecture Deviations

### D1: OUTPOST_TIMEOUT Listed in Architecture Env Var Table But Not Implemented

- **Expected**: `specs/plan/architecture.md:305` lists `OUTPOST_TIMEOUT | session-spawner | Default session timeout | 600` as a configured environment variable.
- **Actual**: No code in `mcp/session-spawner/server.py` reads `OUTPOST_TIMEOUT`. Timeout is a per-call parameter defaulting to `DEFAULT_TIMEOUT = 600` at line 43. The architecture entry has been annotated with `*(not implemented)*` but the row persists in the table.
- **Evidence**: `mcp/session-spawner/server.py:43` — `DEFAULT_TIMEOUT = 600`. `specs/plan/architecture.md:305` — row present with "not implemented" annotation. `specs/domains/session-lifecycle/decisions.md:68` — D-11 documents this as an intentional deviation.
- **Severity**: Minor. The annotation makes the deviation visible. Setting this env var has no effect.

None of the other deviations from cycle 2 (D1–D6) or cycle 4 (MA2) remain. Specifically:

- Prior D1 (spawn_session synchronous / poll_session absent): The architecture was updated to match the synchronous blocking design. `spawn_session` is correctly documented as blocking and returning complete output. `poll_session` is not listed anywhere in the current architecture. Resolved.
- Prior D2 (worker_url vs worker_name): Architecture Section 3 correctly documents `worker_name`. Resolved.
- Prior D3 (OUTPOST_CONCURRENCY vs OUTPOST_MAX_CONCURRENCY): Architecture Section 8 correctly documents `OUTPOST_MAX_CONCURRENCY`. Resolved.
- Prior D4 (poll_remote_job drops timestamp fields): `mcp/session-spawner/server.py:902–905` includes `created_at`, `started_at`, `completed_at` in the field copy list. Resolved.
- Prior D5 (plugin manifest wrong path): `.claude-plugin/plugin.json:13` — `"args": ["${pluginPath}/mcp/session-spawner/server.py"]`. Resolved.
- Prior D6 (README broken paths): `README.md:33` references `mcp/session-spawner/requirements.txt`; `README.md:39` references `mcp/session-spawner/server.py`. Resolved.
- Prior MA1 (token_usage omitted in normal path): `mcp/session-spawner/server.py:616` — `response["token_usage"] = outcome_token_usage` is unconditional on the normal path. `outcome_token_usage` is initialized to `None` at line 534 and only replaced if extraction succeeds, so the field is always present (as null or a value). Resolved.
- Prior MA2 (cancelled state description only mentioned queued): `specs/plan/architecture.md:224` — `| cancelled | Cancelled while queued or running |`. Resolved.

---

## Unmet Acceptance Criteria

### Work Item 028: Fix proc.terminate() race in cancel_job

- [x] `proc.terminate()` wrapped in `try/except (ProcessLookupError, OSError)` — `mcp/remote-worker/server.py:289–291`
- [x] `proc.kill()` in SIGKILL fallback also wrapped — `mcp/remote-worker/server.py:299–302`
- [x] If process already exited, cancel returns normally — logic verified in `cancel_job`
- [x] Test covers the race scenario — covered in `mcp/remote-worker/test_server.py`
- [x] All existing remote-worker tests pass — per incremental review 028

### Work Item 029: Handle FileNotFoundError for missing claude binary

- [x] session-spawner catches `FileNotFoundError` and returns structured error — `mcp/session-spawner/server.py:485–489`
- [x] remote-worker catches `FileNotFoundError` in `_run_claude_job` and marks job failed — `mcp/remote-worker/server.py:379–384`
- [x] Error message contains "claude" and "PATH" in both servers — verified
- [x] No raw Python tracebacks in error response — verified
- [x] All existing tests pass — per incremental review 029

### Work Item 030: Fix conftest sys.modules key collision

- [x] `mcp/session-spawner/conftest.py` registers under `sys.modules["session_spawner_server"]` — `mcp/session-spawner/conftest.py:18–21`
- [x] `mcp/remote-worker/conftest.py` registers under `sys.modules["remote_worker_server"]` — `mcp/remote-worker/conftest.py:18–21`
- [x] Test files import using the new module names — `test_server.py` in each directory confirmed
- [x] pytest from repo root completes without import errors — per incremental review 030
- [x] All 121 tests pass — per incremental review 030

### Work Item 031: Add --cwd flag and max_jobs to list_remote_workers

- [x] `--cwd` followed by `record.working_dir` in `_run_claude_job` command list — `mcp/remote-worker/server.py:362–363`
- [x] False docstring claim corrected — `mcp/remote-worker/server.py:351–354` docstring updated
- [x] `_fetch_worker_health` returned dict includes `max_jobs` — `mcp/session-spawner/server.py:690`
- [x] Test verifies `--cwd` in Popen command — per incremental review 031
- [x] Test verifies `max_jobs` in list_remote_workers output — per incremental review 031
- [x] All existing tests pass — per incremental review 031

### Work Item 032: Documentation sweep

- [x] README.md Usage section includes `cancel_remote_job` — `README.md:50`
- [x] README.md Configuration section cross-references sub-READMEs — `README.md:63–64`
- [x] CLAUDE.md references `mcp/session-spawner/requirements.txt` — `CLAUDE.md:34`
- [x] `specs/plan/architecture.md` Section 8 includes `IDEATE_WORKER_MAX_JOBS` row — `specs/plan/architecture.md:310`

### Work Item 033: Fix cancel-while-starting race in _run_claude_job

- [x] After Popen returns but before `record.process` assignment, status is checked — `mcp/remote-worker/server.py:386–392`
- [x] If status is already `"cancelled"`, proc is killed and function returns `None` — `mcp/remote-worker/server.py:386–391`
- [x] `record.process` is assigned after the cancelled-status check — `mcp/remote-worker/server.py:392`
- [x] Test covers the race scenario — per incremental review 033
- [x] All existing remote-worker tests pass — per incremental review 033

No unmet acceptance criteria found across all six work items.

---

## Principle Violations

None.

All twelve guiding principles are satisfied in the current implementation. See Principle Adherence Evidence below.

---

## Principle Adherence Evidence

- **Principle 1 — Session Isolation**: Each `spawn_session` call constructs a fresh `env` dict copied from `os.environ` with explicit overrides; no shared mutable state between spawned processes. `mcp/session-spawner/server.py:461–466`.

- **Principle 2 — Explicit State Management**: All inter-session coordination passes through disk artifacts. Session events are written via `_log_entry` to `OUTPOST_LOG_FILE` when configured. The in-memory `_session_registry` is explicitly documented as a known conflict with this principle at `specs/domains/session-lifecycle/policies.md:14–15` (P-2 status: "provisional — under review"); no new in-memory coordination mechanisms have been added. The conflict is bounded and disclosed.

- **Principle 3 — Graceful Degradation**: `FileNotFoundError` for missing `claude` binary returns a structured error in both servers (`mcp/session-spawner/server.py:485–489`, `mcp/remote-worker/server.py:379–384`). All remote-dispatch handlers catch exceptions and return structured error payloads without crashing the server (`mcp/session-spawner/server.py:842–854`, `907–909`, `1027–1029`). Worker unreachability returns `"status": "unreachable"` rather than propagating an exception (`mcp/session-spawner/server.py:693–701`).

- **Principle 4 — Transparency and Observability**: The `/health` endpoint exposes `active_jobs`, `queued_jobs`, `max_concurrency`, `max_jobs` (`mcp/remote-worker/server.py:155–167`). `list_remote_workers` makes concurrent health calls and returns live status for every configured worker (`mcp/session-spawner/server.py:704–709`). Session lifecycle events are written to JSONL log and printed as an ASCII status table to stderr (`mcp/session-spawner/server.py:572–574`).

- **Principle 5 — Configurable Dispatch**: `spawn_session` invokes a local subprocess; `spawn_remote_session` posts to an HTTP endpoint. Both accept the same `prompt`, `working_dir`, `role`, `max_turns`, `timeout`, `permission_mode`, `allowed_tools` parameter set. `mcp/session-spawner/server.py:54–265`.

- **Principle 6 — Protocol Compliance**: Tools are registered via `@server.list_tools()` returning `Tool` objects with proper `name`, `description`, `inputSchema`. Responses use `TextContent`. Unknown tool names raise `McpError(ErrorData(code=-32601, ...))`. `mcp/session-spawner/server.py:53–281`.

- **Principle 7 — Resource Bounds**: Output truncation at 50 KB (`DEFAULT_MAX_OUTPUT_BYTES = 50_000`) cannot be disabled. Prompt rejection at 100 KB (`MAX_PROMPT_BYTES = 100_000`). Concurrency semaphore default 5. Remote-worker concurrency default 3. `mcp/session-spawner/server.py:41–48`. `subprocess.run` with `timeout=` parameter kills the child process on `TimeoutExpired` (Python stdlib documented behavior); remote-worker calls `proc.kill()` explicitly at `mcp/remote-worker/server.py:397`.

- **Principle 8 — Role-Based Sessions**: `default-roles.json` defines `worker`, `reviewer`, `manager`, `proxy-human` with distinct `allowed_tools` and `system_prompt`. Caller-wins override for `allowed_tools`, `model`, `max_turns`, `permission_mode` applied in local dispatch at `mcp/session-spawner/server.py:324–337` and in remote dispatch at `mcp/session-spawner/server.py:795–804`. Role `system_prompt` prepended to prompt in both local (`server.py:321`) and remote paths (`server.py:730–733`).

- **Principle 9 — Depth Limits**: `OUTPOST_SPAWN_DEPTH` read from environment and compared against `min(caller_max_depth, _server_max_depth)` before any subprocess is created. Callers cannot raise the server-side cap. `mcp/session-spawner/server.py:407–428`.

- **Principle 10 — Result Integrity**: `spawn_session` returns `output`, `exit_code`, `session_id`, `duration_ms`, `error`, `token_usage`, and conditionally `timed_out`, `output_truncated`, `full_output_path`. Remote worker captures `git diff HEAD` after job completion and stores it on the job record (`mcp/remote-worker/server.py:332–347`, `430`). `poll_remote_job` returns `output`, `git_diff`, `exit_code`, `duration_ms`, `error`, `created_at`, `started_at`, `completed_at` (`mcp/session-spawner/server.py:901–906`).

- **Principle 11 — Stateless Server**: The MCP server (session-spawner) holds no job execution state between tool calls. The `_session_registry` list is the documented exception, marked provisional and subject to policy review. No MCP-level state is required for any tool to function correctly after a server restart. `mcp/session-spawner/server.py:1191–1198`.

- **Principle 12 — Minimal Dependencies**: session-spawner depends on `mcp`, `aiohttp`, and stdlib. remote-worker depends on `fastapi`, `uvicorn`, `pydantic`, and stdlib. No ORM, no message broker, no additional frameworks. `mcp/session-spawner/server.py:29–34`, `mcp/remote-worker/server.py:25–27`.

---

## Undocumented Additions

These three carry forward from `specs/archive/cycles/004/spec-adherence.md` (U1–U3) without change.

### U1: team_name and exec_instructions Parameters in spawn_session

- **Location**: `mcp/session-spawner/server.py:106–116` (inputSchema), lines 291, 461–466 (implementation)
- **Description**: `spawn_session` accepts `team_name` (propagated via `OUTPOST_TEAM_NAME` env var to child sessions) and `exec_instructions` (prepended to the effective prompt and propagated via `OUTPOST_EXEC_INSTRUCTIONS`). Neither parameter appears in architecture Section 3 `spawn_session` input schema or in the guiding principles.
- **Risk**: Low. Both parameters are additive and optional. They do not alter session isolation or resource bounds. The deviation from the architecture input schema is the only concern.

### U2: output_format Parameter in spawn_session

- **Location**: `mcp/session-spawner/server.py:100–105` (inputSchema), lines 289, 441–442 (implementation)
- **Description**: `spawn_session` accepts `output_format` with values `json`, `text`, `stream-json`, controlling the `--output-format` flag passed to the `claude` CLI. Architecture Section 3 does not list this parameter.
- **Risk**: Low. It is optional; the default (`json`) matches the architecture's implied behavior. No safety or resource implications.

### U3: In-Memory Session Registry and stderr Status Table

- **Location**: `mcp/session-spawner/server.py:1195` (`_session_registry`), lines 572–574, 1212–1295
- **Description**: A module-level list accumulates every session entry across the server's process lifetime, and an ASCII status table is printed to stderr after each `spawn_session` call. This is not described in any architecture or work item spec.
- **Risk**: Low per prior cycle assessments. The conflict with GP-2 / GP-11 / C4 is disclosed in `specs/domains/session-lifecycle/policies.md:14–15` (P-2 "provisional — under review") and `specs/domains/session-lifecycle/decisions.md` (D-8). No new risk introduced in the current cycle.

---

## Naming/Pattern Inconsistencies

### N1: JobRecord (plain class) vs JobRequest (Pydantic BaseModel) — inconsistent data model pattern

- **Convention**: Pydantic `BaseModel` used for request deserialization (`JobRequest`); plain Python class used for mutable job state (`JobRecord`).
- **Location**: `mcp/remote-worker/server.py:40–72`
- **Assessment**: The two classes serve different purposes (immutable request vs mutable runtime record), so the asymmetry is functionally justified. No architecture requirement mandates a single pattern. Carries forward from prior cycles as a minor note only.

No new naming or pattern inconsistencies introduced by work items 028–033.

---

## Summary

| ID | Finding | Severity | Status |
|----|---------|----------|--------|
| D1 | OUTPOST_TIMEOUT in architecture table, not implemented in code | Minor | Carries forward; annotated "not implemented" in architecture |
| U1 | team_name / exec_instructions undocumented in architecture | Low risk | Carries forward |
| U2 | output_format parameter undocumented in architecture | Low risk | Carries forward |
| U3 | In-memory session registry / stderr status table undocumented | Low risk | Carries forward; policy conflict disclosed |
| N1 | JobRecord plain class vs JobRequest Pydantic model | Minor | Carries forward |
| — | All prior critical/significant findings (D1–D6, P1–P4 from cycle 2; MA1–MA2 from cycle 4) | — | Resolved |