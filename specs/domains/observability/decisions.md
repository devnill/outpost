# Decisions: Observability

## D-1: Manager agent uses list_remote_workers MCP tool as primary status mechanism
- **Decision**: The manager agent invokes the `list_remote_workers` MCP tool to check worker health. A curl fallback is retained for cases where the MCP tool is unavailable.
- **Rationale**: Using the MCP tool is the correct integration path; curl bypasses the abstraction layer and does not benefit from the tool's structured response.
- **Source**: archive/incremental/035-manager-agent.md (S1)
- **Status**: settled

## D-2: Token usage is null when extraction fails, not omitted
- **Decision**: If token usage cannot be extracted from the session's output JSON, the `token_usage` field is explicitly set to null. The field is always present in log entries.
- **Rationale**: Callers and log consumers can distinguish "no token data available" from "field not applicable." Silent omission causes KeyError in consumers that expect the field.
- **Source**: archive/incremental — WI-046 rework note in journal.md
- **Status**: settled

## D-3: Status table written to stdout at session completion
- **Decision**: The session-spawner prints an ASCII status table to stdout after each session completes (or times out). The table is not written to a log file.
- **Rationale**: Intended for interactive visibility in the parent session's output stream. An empty registry produces no output.
- **Source**: specs/journal.md — WI-023
- **Status**: settled

## D-4: job_id included in mid-flight poll responses
- **Decision**: GET /jobs/{job_id} returns the job_id in the response body even when the job is still running.
- **Rationale**: Callers polling multiple jobs concurrently cannot correlate results without the job_id in the response. It was absent in the initial implementation and added in WI-038 rework.
- **Source**: specs/journal.md — WI-038 rework note
- **Status**: settled

## D-5: poll_remote_job drops timestamp fields from worker response
- **Decision**: `_poll_one()` copies only `output`, `git_diff`, `exit_code`, `duration_ms`, and `error` from the worker's `GET /jobs/{id}` response. The `created_at`, `started_at`, and `completed_at` fields documented in the README are dropped. This was identified as a gap; the fields should be included.
- **Rationale**: Omission was unintentional. Both the architecture spec and the session-spawner README document these fields as part of the response. P-2 (status queries return complete information) requires them.
- **Source**: archive/cycles/002/gap-analysis.md (IG4), archive/cycles/002/spec-adherence.md (D4)
- **Status**: settled

## D-6: list_remote_workers status values differ from architecture spec
- **Decision**: Implementation uses `"ok"` and `"auth_error"` for worker status; architecture specifies `"healthy"` and `"unhealthy"`. The architecture document is stale on this point. Identified as a documentation gap requiring architecture update.
- **Rationale**: Implementation values are more descriptive (distinguishing auth failures from general unhealthiness).
- **Source**: archive/cycles/002/spec-adherence.md (N1)
- **Status**: settled

## D-7: token_usage omitted in normal-path response when extraction fails
- **Decision**: In the non-timeout path of `spawn_session`, `token_usage` is conditionally added only when extraction succeeds (`if outcome_token_usage is not None`). When extraction fails, the field is absent from the response. The timeout path correctly emits `"token_usage": null`. The two paths are inconsistent, and the normal path violates P-3.
- **Rationale**: Rationale not recorded. The conditional pattern was likely an oversight — the timeout path was fixed separately and correctly emits null.
- **Source**: archive/cycles/004/spec-adherence.md (MA1), archive/cycles/004/decision-log.md (OQ-010)
- **Status**: settled — resolved by D-8 in cycle 5

## D-8: Fix token_usage to always-present null in spawn_session normal path
- **Decision**: Unconditionally assign `response["token_usage"] = outcome_token_usage` in the normal (non-timeout) code path. When extraction fails, `outcome_token_usage` is `None`, so the response contains `"token_usage": null`. This makes the normal path consistent with the timeout path and compliant with P-3.
- **Rationale**: P-3 requires absent token data to be explicitly null, not omitted. The conditional pattern caused KeyError in consumers expecting the field. Session-spawner README was not updated in this cycle (see Q-4).
- **Source**: archive/cycles/005/decision-log.md (D-024)
- **Status**: settled

## D-9: Startup configuration validation warnings
- **Decision**: Add WARNING log messages at startup in both session-spawner and remote-worker when credentials or critical configuration are absent.
- **Rationale**: Operators had no feedback when starting servers with missing configuration. Startup warnings surface misconfigurations before the first request fails.
- **Source**: archive/cycles/005/decision-log.md (D-022)
- **Status**: settled

## D-10: Integration tests replaced to exercise MCP tool layer (cycle 6)
- **Decision**: Tests 2 and 3 in `mcp/test_integration.py` were replaced. Prior versions called the remote-worker HTTP API directly, bypassing the session-spawner MCP tool layer. Replacements call `_handle_poll_remote_job` and `_handle_cancel_remote_job` against an in-process worker, exercising the fan-out logic end-to-end. All 5 integration tests pass.
- **Rationale**: Cycle 5 significant finding (SG1/OQ-012): integration tests 2 and 3 bypassed the MCP tool layer, leaving the session-spawner fan-out and error-collection logic untested at the integration level.
- **Source**: archive/cycles/006/decision-log.md (D-025)
- **Status**: settled

## D-11: Code hygiene — test infrastructure fixes (cycle 6)
- **Decision**: Three minor fixes: empty `__init__.py` added to both test directories so `pytest mcp/` works; `_evict_terminal_jobs_locked` lock precondition merged into docstring; `_max_jobs` reset to 1000 added to `worker_server` fixture teardown. The `sys.modules["server"]` key collision in conftests was identified but not addressed (see Q-5).
- **Rationale**: OQ-017/018/019 were minor hygiene items that posed no functional risk but improved test reliability and code clarity.
- **Source**: archive/cycles/006/decision-log.md (D-027)
- **Status**: settled
