# Review Summary — Outpost Cycle 2

## Overview

The session-spawner implementation satisfies its own acceptance criteria and all 58 tests pass. However, the project as a whole has six critical findings, four significant findings, and cannot be installed as documented. The most consequential issues are: broken installation paths in the plugin manifest and README (unanimous finding across all three reviewers), timed-out subprocesses may not be killed (reviewer contradiction requiring verification), the `poll_session` tool is absent and `spawn_session` diverges from its own architecture contract without documentation, and role constraints are not applied to remote sessions.

## Critical Findings

- **[gap-analyst]** Plugin manifest `.claude-plugin/plugin.json` references `${pluginPath}/mcp/server.py` which does not exist — actual server is at `mcp/session-spawner/server.py`. Plugin installation fails for all users. — relates to: cross-cutting
- **[gap-analyst]** Root `README.md` `pip install -r requirements.txt` command fails — no `requirements.txt` at project root. First-run installation broken. — relates to: cross-cutting
- **[gap-analyst]** Root `README.md` `claude mcp add outpost -- python /path/to/outpost/mcp/server.py` command fails — `mcp/server.py` does not exist. Manual registration broken. — relates to: cross-cutting
- **[gap-analyst / spec-reviewer]** `poll_session` tool is absent; `spawn_session` is synchronous and returns full results immediately, contradicting the architecture's async spawn+poll design. No documentation acknowledges the deviation. `mcp/session-spawner/server.py:447–455`, `mcp/session-spawner/server.py:54–238` — relates to: GP-5 (Configurable Dispatch), work item 011
- **[spec-reviewer / gap-analyst]** Timed-out subprocesses may not be killed — constraint C12 (SIGKILL on timeout) may be violated in both session-spawner and remote-worker. Note: the code-quality reviewer states `subprocess.run()` kills internally; spec-reviewer and gap-analyst cite Python docs that it does NOT. This contradiction must be resolved before cycle 3 scope is set. `mcp/session-spawner/server.py:456–468`; `mcp/remote-worker/server.py:312–319` — relates to: C12 (Timeout → SIGKILL)
- **[code-reviewer]** `poll_remote_job` auth-error check takes priority over found-result in multi-worker fanout. A single misconfigured worker blocks all polls that omit `worker_name`. `mcp/session-spawner/server.py:854–867` — relates to: GP-3 (Graceful Degradation)

## Significant Findings

- **[spec-reviewer / gap-analyst]** Role constraints not applied to remote sessions. `spawn_remote_session` with `role="reviewer"` passes role as a label; remote worker does not resolve the definition or apply `allowed_tools`, `system_prompt`, `permission_mode`. `mcp/remote-worker/server.py:290–309` — relates to: GP-8 (Role-Based Sessions)
- **[spec-reviewer / gap-analyst]** `_session_registry` is in-memory only; JSONL logging requires `OUTPOST_LOG_FILE` (no default). Hard constraint C4 (filesystem-based state) and GP-2, GP-11 violated. `mcp/session-spawner/server.py:1008, 1015–1017` — relates to: C4, GP-2, GP-11
- **[gap-analyst]** Architecture document describes async `spawn_session` and `poll_session` that do not exist; env var names and parameter names differ between architecture and implementation. No documentation acknowledges any of these deviations. — relates to: cross-cutting (depends on OQ-004 resolution)
- **[gap-analyst]** Running remote jobs cannot be cancelled. `DELETE /jobs/{id}` returns HTTP 409 for `running` jobs; `cancelled` state defined but unreachable from `running`. No signal sent to subprocess. — relates to: GP-3 (Graceful Degradation)

## Minor Findings

- **[gap-analyst]** `poll_remote_job` drops `created_at`, `started_at`, `completed_at` fields that the README documents in the response. `mcp/session-spawner/server.py:844–846` — relates to: GP-10 (Result Integrity)
- **[gap-analyst]** `spawn_remote_session` does not validate prompt size locally before HTTP call (round-trip wasted; behavior functionally correct). — relates to: GP-7 (Resource Bounds)
- **[code-reviewer / gap-analyst]** `job_store` (remote-worker) and `_session_registry` (session-spawner) grow without bound. No eviction policy. — relates to: GP-7 (Resource Bounds)
- **[spec-reviewer]** `list_remote_workers` status values use `"ok"` and `"auth_error"` in code; architecture specifies `"healthy"` and `"unhealthy"`. — relates to: GP-4 (Observability)
- **[spec-reviewer]** Architecture §8 uses `OUTPOST_CONCURRENCY`; code reads `OUTPOST_MAX_CONCURRENCY`. Setting the architecture's documented variable silently has no effect. — relates to: cross-cutting
- **[spec-reviewer]** Architecture §3 `spawn_remote_session` uses `worker_url`; code uses `worker_name`. Callers following the architecture spec are silently ignored. — relates to: cross-cutting
- **[code-reviewer]** Worker-skip path in remote-worker produces no log output when a queued job is cancelled while waiting. `mcp/remote-worker/server.py:358–360` — relates to: GP-4 (Observability)

## Suggestions

- **[spec-reviewer]** `spawn_session` handler (340 lines inline in `call_tool()`) vs. `_handle_*` decomposed functions for remote tools — inconsistent decomposition. Extract `spawn_session` logic into `_handle_spawn_session()` for consistency.
- **[spec-reviewer]** `JobRecord` (plain class) vs. `JobRequest` (Pydantic BaseModel) in remote-worker — inconsistent pattern. Align both to the same serialization approach.
- **[gap-analyst]** Add `pyproject.toml` and entry point to `session-spawner` for packaging parity with `remote-worker`.
- **[gap-analyst]** Add CI configuration (GitHub Actions) running both test suites on commit.

## Findings Requiring User Input

**1. Should `spawn_session` remain synchronous, or should `poll_session` be implemented?** (OQ-004)
- Context: Architecture defines async spawn+poll. Implementation is synchronous. `poll_session` is absent. No document explains the deviation. The fix path (implement async model vs. document sync as final) determines cycle 3 scope entirely.
- Impact: Callers following the architecture contract will receive `McpError -32601` when calling `poll_session`. True parallel dispatch — spawning N sessions then polling each — cannot be used as designed. The architecture document misleads every future contributor.

**2. Are timed-out subprocesses killed?** (OQ-002)
- Context: The code-quality reviewer states `subprocess.run()` kills the child internally on `TimeoutExpired`. The spec-adherence reviewer and gap-analyst state it does NOT (citing Python documentation that the caller must explicitly kill the child). These are opposite conclusions on the same code path.
- Impact: If not killed, C12 is violated in both components and orphaned `claude` processes accumulate. If killed, no fix is needed. This must be resolved before cycle 3 work items are scoped.

**3. Should role constraints apply to remote sessions, and where should resolution happen?** (OQ-003)
- Context: Remote worker receives `role` as a label string but does not apply `allowed_tools`, `system_prompt`, or `permission_mode`. GP-8 requires role constraints for all sessions.
- Options: (a) session-spawner resolves role at dispatch time and sends resolved fields in the HTTP payload; (b) remote-worker loads role definitions locally and applies them. Each option has different deployment implications.

## Proposed Refinement Plan

The review identified 6 critical and 4 significant findings. A refinement cycle is needed.

**Prerequisite: resolve the two user-input questions before creating work items.**

OQ-004 (async vs sync) determines whether cycle 3 includes `poll_session` implementation or architecture document updates. OQ-002 (timeout kill) determines whether cycle 3 includes a subprocess management rework in both components or only documentation. Without these answers, work item scope cannot be accurately set.

**Confirmed work items regardless of user decisions:**

1. **Fix installation paths** (addresses CI1, CI2, CI3): Update `.claude-plugin/plugin.json` arg, update `README.md` mcp-add command and requirements instruction, create root `requirements.txt` or update docs to per-component paths. Low complexity.

2. **Fix `poll_remote_job` auth-error priority** (addresses code-quality S1): In multi-worker fanout, check for found result before returning auth error. One-line reordering. Low complexity.

3. **Fix `poll_remote_job` missing timestamp fields** (addresses IG4): Extend field-copy list in `_poll_one()` to include `created_at`, `started_at`, `completed_at`. One-line fix. Low complexity.

4. **Fix architecture document** (addresses D2, D3, N1 and OQ-007 after OQ-004 resolved): Update `spawn_remote_session` parameter name, env var name, status values, and `spawn_session` output schema to match implementation. Medium complexity.

**Conditional work items (pending user decisions):**

5. **Implement `poll_session` OR document sync as final** (addresses MR1, D1, IG1, AD3): Depends on OQ-004.

6. **Fix timeout SIGKILL enforcement** (addresses SC1, SC2, P2): Depends on OQ-002. If not currently enforced: switch both components to `subprocess.Popen` for explicit kill on `TimeoutExpired`. Medium complexity.

7. **Apply role constraints to remote sessions** (addresses IG2, P3): Depends on OQ-003 design decision.

8. **Default filesystem state** (addresses MR2, P1/P4): Depends on OQ-001 / OQ-004 resolution. If disk state is required: add default `OUTPOST_LOG_FILE` path or implement explicit session-file writing.

**Suggested next step**: Run `/ideate:refine` with the answers to the three user-input questions as the starting context.
