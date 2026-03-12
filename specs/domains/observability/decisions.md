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
