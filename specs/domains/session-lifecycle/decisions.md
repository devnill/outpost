# Decisions: Session Lifecycle

## D-1: Filesystem-only state (no database, no in-memory store)
- **Decision**: All session tracking uses the filesystem. No databases, no in-memory session stores, no external state services.
- **Rationale**: Simplicity and recoverability — a server restart does not lose session state. Matches the single-user, local-tooling deployment model.
- **Assumes**: The filesystem is durable and accessible by the server process.
- **Source**: steering/constraints.md (C4), steering/interview.md
- **Status**: settled

## D-2: Role definitions are static JSON loaded at startup
- **Decision**: Roles are defined in JSON files loaded when the server starts. There is no API for dynamic role creation or modification at runtime.
- **Rationale**: Security and simplicity — static roles cannot be injected at request time by a malicious caller.
- **Assumes**: Role changes require a server restart, which is acceptable for this deployment model.
- **Source**: steering/constraints.md (C10), plan/architecture.md §5
- **Status**: settled

## D-3: Depth limit enforced server-side; error returned before session creation
- **Decision**: The depth check runs before any subprocess is created. Sessions at max depth receive a structured error, not a warning.
- **Rationale**: Prevents runaway recursion. Client-side enforcement would be bypassable.
- **Source**: plan/architecture.md §6, steering/constraints.md (C9)
- **Status**: settled

## D-4: Timed-out sessions are killed via SIGKILL
- **Decision**: When a session exceeds its timeout, the process is terminated with SIGKILL and partial output is returned.
- **Rationale**: SIGTERM could be ignored by the subprocess. SIGKILL guarantees termination.
- **Source**: steering/constraints.md (C12)
- **Status**: settled

## D-5: model parameter uses caller-wins pattern
- **Decision**: If the caller specifies a model, it overrides any model defined in the role. Role default is used only when the caller omits the parameter.
- **Rationale**: Consistent with the pattern used for other role-overridable parameters (max_turns, permission_mode, allowed_tools). Caller has the most context about what model is needed.
- **Source**: specs/journal.md — WI-039 rework note
- **Status**: settled

## D-6: exec_instructions propagate to child sessions via environment variable
- **Decision**: The `exec_instructions` parameter is injected into the child session's prompt and propagated to grandchild sessions via the `IDEATE_EXEC_INSTRUCTIONS` environment variable.
- **Rationale**: Enables consistent execution context across session depth without requiring callers to re-pass instructions at every level.
- **Source**: specs/journal.md — WI-024
- **Status**: settled

## D-7: spawn_session implemented as synchronous (undocumented architecture deviation)
- **Decision**: `spawn_session` blocks until the subprocess exits and returns the full result in one call. The architecture's async spawn+poll model (with `poll_session` as a separate tool) was not implemented. No documentation acknowledged this deviation prior to cycle 2 review.
- **Rationale**: Rationale not recorded. The architecture specifies non-blocking spawn returning `{session_id, status: "running"}` with `poll_session` for result retrieval, but the implementation went synchronous without explanation.
- **Assumes**: Callers do not need true parallel local dispatch (spawn N, poll each). If they do, the current design is blocking.
- **Source**: archive/cycles/002/decision-log.md (D-010), archive/cycles/002/summary.md (OQ-004)
- **Policy**: None — pending Q-3 resolution
- **Status**: settled — superseded by D-12

## D-8: Session registry implemented as in-memory list with opt-in disk logging
- **Decision**: `_session_registry` is a module-level Python list. JSONL disk logging is only active when `OUTPOST_LOG_FILE` is set; there is no default path. Session history is lost on server restart unless the operator configures logging.
- **Rationale**: Rationale not recorded. Contradicts hard constraint C4 and policies P-2, GP-2, GP-11 which require filesystem-based state.
- **Source**: archive/cycles/002/decision-log.md (D-011), archive/cycles/002/spec-adherence.md (P1/P4)
- **Policy**: Conflicts with P-2 — see Q-4
- **Status**: provisional

## D-9: Timeout path uses byte-boundary truncation matching success path
- **Decision**: The timeout code path now uses encode/slice/decode for output truncation, matching the 50KB byte semantic used in the success path. Previously, character-count slicing was used inconsistently.
- **Rationale**: Incremental review M1 identified that character-count slicing in the timeout path was inconsistent with the byte-based truncation in the success path.
- **Source**: archive/cycles/002/decision-log.md (D-017)
- **Status**: settled

## D-10: Timeout path writes overflow file for large partial output
- **Decision**: The timeout code path now mirrors the success path's overflow-file logic, writing large partial output to a temp file so callers can recover the full content.
- **Rationale**: Without this, callers could not recover full partial output from timed-out sessions that exceeded the inline truncation limit.
- **Source**: archive/cycles/002/decision-log.md (D-018)
- **Status**: settled

## D-11: OUTPOST_TIMEOUT env var absent; timeout is per-call only
- **Decision**: There is no global `OUTPOST_TIMEOUT` environment variable. Timeout is a per-call parameter with a server-side default. The architecture spec listed `OUTPOST_TIMEOUT` but the implementation chose per-call parameters instead.
- **Rationale**: Documented as intentional deviation during WI-011 verification. Per-call timeout gives callers fine-grained control without a global override.
- **Source**: archive/cycles/002/decision-log.md (D-020)
- **Status**: settled

## D-12: Accept synchronous spawn_session as final design
- **Decision**: Accept synchronous `spawn_session` as the final design; do not implement `poll_session`.
- **Rationale**: Architecture originally defined async spawn+poll model, but implementation went synchronous. User confirmed synchronous is acceptable for the use case.
- **Assumes**: Callers can block on session completion; no need for async polling pattern.
- **Source**: archive/cycles/003/decision-log.md (Planning phase, 2026-03-16)
- **Status**: settled

## D-13: Timeout subprocess kill verification
- **Decision**: No fix needed for timeout handling; `subprocess.run()` calls `process.kill()` internally.
- **Rationale**: Verified via CPython source (subprocess.py) that timeout parameter triggers kill.
- **Assumes**: CPython subprocess behavior remains consistent across versions.
- **Source**: archive/cycles/003/decision-log.md (Planning phase, 2026-03-16)
- **Status**: settled

## D-14: Role resolution for remote sessions — Option A
- **Decision**: Session-spawner resolves role definition at dispatch time and sends resolved `allowed_tools` and `permission_mode` in HTTP payload.
- **Rationale**: Option A chosen over Option B — simpler deployment, no need to synchronize role definitions across worker nodes.
- **Assumes**: Role definitions are stable during job execution; workers do not need dynamic role updates.
- **Source**: archive/cycles/003/decision-log.md (Planning phase, 2026-03-16)
- **Status**: settled

## D-15: Installation path corrections
- **Decision**: Fix `plugin.json` args path; fix README `pip install` and `claude mcp add` commands.
- **Rationale**: Paths were stale from project restructuring; mechanical fixes required for correct MCP registration.
- **Source**: archive/cycles/003/decision-log.md (Execution phase, WI-012)
- **Status**: settled

## D-16: Role constraints applied to remote sessions
- **Decision**: Resolve role in `_handle_spawn_remote_session` before building HTTP payload.
- **Rationale**: Implements D-14 (Option A resolution); satisfies GP-8 (Role-Based Sessions).
- **Assumes**: Role constraints should apply equally to local and remote dispatch.
- **Source**: archive/cycles/003/decision-log.md (Execution phase, WI-015)
- **Status**: settled

## D-17: Role system_prompt not propagated to remote sessions (regression)
- **Decision**: WI-015 propagated `allowed_tools`, `permission_mode`, and `max_turns` to remote sessions but omitted `system_prompt`. Local spawn prepends system_prompt to the prompt at lines 289-292; the remote dispatch path has no equivalent. Three built-in roles (`reviewer`, `manager`, `proxy-human`) express behavioral contracts primarily through system_prompt. The omission silently degrades role guarantees for remote sessions.
- **Rationale**: WI-015 was scoped to tool constraints and permission mode. The system_prompt dimension was not explicitly in or out of scope, producing an incomplete fix. Whether to propagate system_prompt requires user decision (see Q-10).
- **Assumes**: P-4 (role constraints at spawn time) requires all role dimensions including system_prompt.
- **Source**: archive/cycles/004/code-quality.md (S1), archive/cycles/004/gap-analysis.md (CG1)
- **Status**: settled — resolved by D-18 in cycle 5

## D-18: Propagate role system_prompt to remote sessions
- **Decision**: After role resolution in `_handle_spawn_remote_session`, prepend the resolved role's `system_prompt` to `payload["prompt"]` using the same `[ROLE: {label}]\n{system_prompt}\n\n{prompt}` pattern used in local `spawn_session`. The `spawn_remote_session` schema was also updated to accept inline role dicts (`oneOf [string, object]`).
- **Rationale**: Cycle 4 critical finding (CG1): `allowed_tools` and `permission_mode` were propagated by WI-015, but `system_prompt` was not. Roles like `reviewer`, `manager`, and `proxy-human` express behavioral contracts primarily through system_prompt. Omission silently degraded role guarantees for remote sessions.
- **Assumes**: Remote workers accept the prepended system_prompt in the prompt field without additional handling.
- **Source**: archive/cycles/005/decision-log.md (D-018), archive/cycles/005/gap-analysis.md
- **Policy**: Restores full compliance with P-4
- **Status**: settled

## D-19: Establish policy for missing-binary error handling at subprocess call sites
- **Decision**: Both session-spawner and remote-worker must catch `FileNotFoundError` when invoking the `claude` CLI and return a structured error message rather than propagating a raw Python exception. This is the most common new-user failure mode and has been flagged in four consecutive review cycles without being scheduled as a work item.
- **Rationale**: Raw `FileNotFoundError` produces a Python traceback (session-spawner) or opaque "failed" job status (remote-worker), neither of which tells the user what to do. GP-3 (Graceful Degradation) requires structured error responses for predictable failure modes.
- **Source**: archive/cycles/007/gap-analysis.md (EC2/IR1), archive/cycles/007/decision-log.md (RV-005), session-lifecycle Q-6
- **Policy**: P-7
- **Status**: settled
