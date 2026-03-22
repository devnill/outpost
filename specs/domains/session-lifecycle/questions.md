# Questions: Session Lifecycle

## Q-1: Output truncation — head vs tail preference
- **Question**: When truncating session output to `max_output_bytes`, does the implementation preserve the beginning or the end of the output? GP-10 states "preserves the most relevant content" but does not specify which end.
- **Source**: steering/guiding-principles.md (GP-10), plan/architecture.md §2
- **Impact**: Callers relying on truncated output for debugging get different information depending on which end is preserved. Documentation should match implementation behavior.
- **Status**: open
- **Reexamination trigger**: A caller reports that truncated output is missing the actionable part of a session's work.

## Q-2: Security posture of exec_instructions propagation
- **Question**: The `exec_instructions` parameter propagates to all descendant sessions via environment variable. If outpost is used with untrusted prompts, this creates a potential for prompt injection via crafted exec_instructions. Is this risk documented and accepted?
- **Source**: specs/journal.md — WI-024, steering/constraints.md (C13 OUTPOST_SAFE_ROOT)
- **Impact**: Untrusted callers with API key access could inject instructions into all descendant sessions.
- **Status**: open
- **Reexamination trigger**: Outpost is deployed in a context where the calling session is not fully trusted.

## Q-3: Should spawn_session remain synchronous, or should poll_session be implemented?
- **Question**: The architecture defines an async spawn+poll model where `spawn_session` returns immediately and `poll_session` retrieves results. The implementation is synchronous — `spawn_session` blocks until completion and `poll_session` does not exist. Should the async model be implemented, or should the architecture be updated to document synchronous as the final design?
- **Source**: archive/cycles/002/summary.md (OQ-004), archive/cycles/002/decision-log.md (D-006, D-010)
- **Impact**: Callers following the architecture contract receive `McpError -32601` when calling `poll_session`. True parallel local dispatch (spawn N then poll each) is impossible with the current synchronous design. Resolution determines cycle 3 scope.
- **Status**: resolved — 2026-03-16
- **Resolution**: Accept synchronous as the final design. Architecture updated to remove `poll_session` and document `spawn_session` as a blocking call. Addressed by D-12.

## Q-4: Should _session_registry move to filesystem-backed storage?
- **Question**: The implementation uses an in-memory `_session_registry` with opt-in JSONL logging (no default path), violating hard constraint C4 and policy P-2. Should filesystem-backed state be enforced (e.g., default `OUTPOST_LOG_FILE` path), or should the constraint be relaxed?
- **Source**: archive/cycles/002/summary.md (OQ-001), archive/cycles/002/gap-analysis.md (MR2)
- **Impact**: Session history is lost on server restart. Registry grows without bound in memory. P-2 is currently violated.
- **Status**: open — escalated in cycle 7
- **Reexamination trigger**: Cycle 3 scope is set; interacts with Q-3 resolution.
- **Cycle 7 note**: Gap analyst escalated to significant severity (OQ-025). Six cycles without user decision. Two options: A) add default `OUTPOST_LOG_FILE` path to make state durable by default; B) formally accept in-memory design and update interview record and constraint C4. Cannot be resolved by technical investigation alone — requires user decision. Source: archive/cycles/007/decision-log.md (RV-006), archive/cycles/007/gap-analysis.md (MR2).

## Q-5: Are timed-out subprocesses actually killed? (Reviewer contradiction)
- **Question**: The code-quality reviewer states `subprocess.run()` kills the child internally on `TimeoutExpired`. The spec-adherence reviewer and gap analyst state it does NOT (citing Python documentation that the caller must explicitly kill). These are opposite conclusions about the same code path. Which is correct?
- **Source**: archive/cycles/002/summary.md (OQ-002), archive/cycles/002/spec-adherence.md (P2), archive/cycles/002/gap-analysis.md (SC1, SC2)
- **Impact**: If not killed, constraint C12 is violated in both components and orphaned `claude` processes accumulate. If killed, no fix is needed. Must be resolved before cycle 3 work items are scoped.
- **Status**: resolved — 2026-03-16
- **Resolution**: Verified via CPython source (subprocess.py line 46 calls `process.kill()` internally before re-raising TimeoutExpired). C12 is satisfied. No fix required. Addressed by D-13.

## Q-6: Claude CLI not on PATH error handling
- **Question**: Should FileNotFoundError from missing `claude` binary be caught and converted to helpful error message?
- **Source**: Gap analysis EC2 (archive/cycles/003/gap-analysis.md)
- **Impact**: Users see internal exception rather than actionable error; violates implicit requirement IR1 (meaningful error messages).
- **Status**: open — escalated in cycle 7
- **Reexamination trigger**: User confusion reports or onboarding friction.
- **Cycle 7 note**: Gap analyst escalated to significant severity (OQ-024). Recommended "address now" in four consecutive cycles (3, 4, 5, 7) without scheduling. Both session-spawner and remote-worker are affected. See P-7 for the derived policy. Source: archive/cycles/007/gap-analysis.md (EC2/IR1), archive/cycles/007/decision-log.md (RV-005).

## Q-7: HTTP session creation per request
- **Question**: Should aiohttp ClientSession be reused across requests instead of creating per-request?
- **Source**: Gap analysis EC6 (archive/cycles/003/gap-analysis.md)
- **Impact**: Resource inefficiency; connection pooling not utilized for remote worker communication.
- **Status**: resolved — cycle 4
- **Resolution**: A shared `aiohttp.ClientSession` is now created in `main()` and reused via `_get_http_session()`. Confirmed resolved in archive/cycles/004/gap-analysis.md (Addressed Gaps, EC6).

## Q-8: Local session cancellation
- **Question**: Should local sessions support cancellation like remote jobs?
- **Source**: Gap analysis II4 (archive/cycles/003/gap-analysis.md)
- **Impact**: Inconsistent UX between local and remote dispatch; no way to abort long-running local sessions.
- **Status**: open
- **Reexamination trigger**: User request for local cancellation or timeout handling gaps.

## Q-9: Graceful shutdown handling
- **Question**: Should the MCP server track and terminate spawned processes on shutdown?
- **Source**: Gap analysis MI5 (archive/cycles/003/gap-analysis.md)
- **Impact**: Running local sessions become orphaned when MCP server terminates.
- **Status**: open
- **Reexamination trigger**: Production deployment with rolling restarts or graceful shutdown requirements.

## Q-10: Should remote dispatch propagate role system_prompt?
- **Question**: `_handle_spawn_remote_session` propagates `allowed_tools`, `permission_mode`, and `max_turns` from a resolved role but does not prepend the role's `system_prompt` to `payload["prompt"]`. Local `spawn_session` does this correctly. Should the remote path include system_prompt injection, or are remote roles formally tool-constraints-only?
- **Source**: archive/cycles/004/code-quality.md (S1), archive/cycles/004/gap-analysis.md (CG1), archive/cycles/004/decision-log.md (OQ-001)
- **Impact**: `reviewer`, `manager`, and `proxy-human` roles carry significant system prompts as their primary behavioral enforcement. Remote sessions receive tool restrictions but no behavioral framing. P-4 is violated for the system_prompt dimension.
- **Status**: resolved
- **Resolution**: WI-018 fixed the gap by prepending role system_prompt to the remote payload prompt using the same pattern as local spawn. All role dimensions now propagate to remote sessions.
- **Resolved in**: cycle 5
