# Review Summary — Cycle 4

## Overview

Cycle 4 is a re-verification review with no new work items executed since cycle 3's PASS verdict. The review found one critical regression introduced by WI-015: `system_prompt` is not propagated to remote sessions when a role is specified, silently degrading behavioral enforcement for the `reviewer`, `manager`, and `proxy-human` roles. Six significant gaps persist or were introduced by cycle 3 changes, five of which are carried from cycle 3 without change. Documentation divergence between implementation and READMEs/architecture has accumulated across three cycles.

---

## Critical Findings

- [code-reviewer, gap-analyst] **Role system_prompt silently dropped for remote sessions** — `_handle_spawn_remote_session` propagates `allowed_tools`, `permission_mode`, and `max_turns` from a resolved role but never prepends `system_prompt` to `payload["prompt"]`. Local `spawn_session` does this correctly at lines 289–292. Three built-in roles (`reviewer`, `manager`, `proxy-human`) express their behavioral contracts primarily through the system prompt. A remote session assigned `role="reviewer"` receives tool restrictions but no behavioral framing. The omission is silent at call time. Introduced as a regression by WI-015. — relates to: GP-8 (Role-Based Sessions), session-lifecycle P-4, work item WI-015

---

## Significant Findings

- [gap-analyst] **DELETE /jobs README documents only queued-job cancellation** — `mcp/remote-worker/README.md` states running jobs return 409 and cannot be cancelled. WI-017 changed this; `cancel_job` handles running jobs with SIGTERM/SIGKILL. README and job lifecycle diagram not updated. — relates to: WI-017
- [gap-analyst] **No MCP tool to cancel a remote job** — session-spawner provides `spawn_remote_session` and `poll_remote_job` but no `cancel_remote_job` tool. The cancellation capability added by WI-017 is unreachable through the MCP interface. Callers must access the remote worker's HTTP API directly. — relates to: WI-017, cross-cutting
- [gap-analyst] **Job store memory leak** (persistent, cycle 2) — `job_store` in `mcp/remote-worker/server.py` accumulates completed/failed/cancelled jobs indefinitely with no eviction, TTL, or size cap. Memory grows linearly with total jobs processed. — relates to: GP-7 (Resource Bounds), cross-cutting
- [gap-analyst] **Role documentation contradiction worsened by WI-015** (persistent, cycle 3) — Both READMEs describe role as "observability label only" with no effect on remote sessions. WI-015 changed this; tool constraints and permission mode now propagate. READMEs not updated. Now incorrect in both directions: tool constraints do propagate (docs wrong), system_prompt does not propagate (docs accidentally correct per critical finding above). — relates to: WI-015, cross-cutting
- [gap-analyst] **No integration tests between session-spawner and remote-worker** (persistent, cycle 3) — All session-spawner tests mock aiohttp; all remote-worker tests use in-process ASGI transport. HTTP contract (payload field names, status codes, response shapes) is untested end-to-end. — relates to: cross-cutting
- [gap-analyst] **No startup configuration validation** (persistent, cycle 3) — Remote-worker does not validate that `IDEATE_WORKER_API_KEY` is set at startup; misconfiguration discovered only when first request arrives. Session-spawner silently treats missing `api_key` in worker entries as empty string. — relates to: GP-4 (Transparency), cross-cutting

---

## Minor Findings

- [spec-reviewer] `token_usage` omitted (not null) in normal-path spawn_session response when extraction fails — violates observability P-3; timeout path correctly emits null (`server.py:582–583`)
- [spec-reviewer] Architecture job-states table still reads "Cancelled while queued" after WI-017 extended cancellation to running jobs (`architecture.md:223`)
- [spec-reviewer] `OUTPOST_TIMEOUT` listed in architecture env var table but not implemented; entry was not corrected by WI-016 (`architecture.md:304`)
- [code-reviewer] `proc.terminate()` in `cancel_job` unguarded against `ProcessLookupError`/`OSError` when process exits before terminate() is called (`remote-worker/server.py:275`)
- [code-reviewer] Variable naming mismatch in `_run_claude_job` timeout handling: `stdout_bytes` is actually a string with `text=True` (`remote-worker/server.py:340–342`)
- [code-reviewer] `spawn_remote_session` tool schema declares role as `string` only but handler also accepts inline dict, bypassing role validation (`session-spawner/server.py:169–171` vs. `server.py:692`)
- [code-reviewer] Tiny race window between `Popen()` call and `record.process = proc` assignment — cancel arriving in this window captures `None` and cannot signal the process (`remote-worker/server.py:327–334`)
- [gap-analyst] Claude CLI not on PATH produces an unhelpful `FileNotFoundError` with no actionable message
- [gap-analyst] `git_diff` output has no size limit; session output is capped at 50KB but git diffs are not
- [gap-analyst] No graceful shutdown for orphaned local `claude` subprocesses when session-spawner terminates
- [gap-analyst] No retry logic for transient remote worker HTTP failures

---

## Suggestions

- [code-reviewer] Extract shared datetime UTC formatting utility — pattern appears 7 times across both servers
- [code-reviewer] Align version numbers: session-spawner (0.4.0) vs. remote-worker (0.1.0) have diverged significantly
- [code-reviewer] Document `IDEATE_WORKER_HOST` in architecture env var table — read at `remote-worker/server.py:425` but not in any documentation
- [code-reviewer] Document `output_format` parameter's behavioral dependency on `token_usage` extraction (only works with `json` format)

---

## Findings Requiring User Input

- **OQ-001: Should remote dispatch propagate system_prompt?** — WI-015 was scoped to `allowed_tools` and `permission_mode` propagation; `system_prompt` was not explicitly in or out of scope. The architectural question is whether remote roles should have the same behavioral semantics as local roles, or whether remote roles are formally tool-constraints-only. The current state (constraints propagated, system_prompt not) is neither the original design nor a documented design decision. Resolving OQ-001 determines the fix for the critical finding and also determines what OQ-006 (README documentation) should say. Options: (A) propagate system_prompt to payload["prompt"] using the same format as local spawn; (B) formally document remote roles as tool-constraints-only and update documentation accordingly. Impact: affects security posture of the reviewer/manager/proxy-human roles in remote dispatch.
- **OQ-002: Add cancel_remote_job MCP tool?** — The remote-worker exposes `DELETE /jobs/{job_id}` for running and queued jobs. The session-spawner has no corresponding tool. Adding it requires implementing worker resolution and HTTP dispatch logic (similar to `_handle_poll_remote_job`). User decision on whether this is in scope for the next work cycle.
- **OQ-007: Job store eviction policy** — Three cycles open. Memory leak in remote-worker `job_store`. Needs a user decision on eviction semantics (TTL, max-size LRU, delete-after-retrieval, explicit clear endpoint) before implementation can proceed.
- **OQ-008: Integration tests** — Two cycles open. Needs user decision on whether to invest in integration test infrastructure (requires running both servers together).

---

## Proposed Refinement Plan

The review identified 1 critical and 6 significant findings. A refinement cycle is recommended.

**Priority 1 — Critical (must fix before project is usable with roles):**
- OQ-001 resolution + implementation: Propagate `system_prompt` in `_handle_spawn_remote_session` (or formally document remote roles as tool-constraints-only and update documentation)

**Priority 2 — Documentation (low-effort, high-impact for correctness):**
- OQ-003: Update `mcp/remote-worker/README.md` to document running-job cancellation
- OQ-004: Update `architecture.md` cancelled state description
- OQ-005: Remove or annotate `OUTPOST_TIMEOUT` in architecture env var table
- OQ-006: Update both READMEs to reflect post-WI-015 role behavior (depends on OQ-001 resolution)

**Priority 3 — Significant gaps with user decisions pending:**
- OQ-002: Add `cancel_remote_job` MCP tool (user decision required)
- OQ-007: Implement job store eviction policy (user decision on semantics required)
- OQ-008: Add integration tests (user decision on test infrastructure required)
- SG6: Add startup configuration validation (technical, no decision needed)

**Priority 4 — Minor fixes (can be batched):**
- MA1/OQ-010: Emit `"token_usage": null` in normal-path spawn_session response
- M1/MG1: Add `try/except OSError` guard around `proc.terminate()` in `cancel_job`
- M3: Document or restrict inline role dict path in `spawn_remote_session`

`/ideate:refine` is recommended with scope description: "Fix role system_prompt propagation for remote sessions (critical), update README and architecture documentation for WI-015 and WI-017 changes, and address user decisions on cancel_remote_job tool and job store eviction policy."
