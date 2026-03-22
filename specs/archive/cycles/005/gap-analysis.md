# Gap Analysis — Cycle 5

## Summary

The cycle 5 implementation satisfies all code-level acceptance criteria. Two significant gaps remain: WI-021 integration tests 2 and 3 exercise the remote-worker HTTP API directly instead of through the MCP tool handlers, leaving the session-spawner's fan-out and error-normalization paths untested end-to-end; and the session-spawner README still describes `token_usage` as omitted when absent, contradicting the WI-024 fix and observability P-3. Two minor gaps (missing env var documentation, missing edge-case test) are also identified.

## Critical Gaps

None.

## Significant Gaps

### SG1: WI-021 tests 2 and 3 bypass the MCP tool layer

- **Work item reference**: WI-021 criteria: "Test 2: poll_remote_job retrieves job status from in-process worker" and "Test 3: cancel_remote_job cancels a queued job via in-process worker."
- **Current state**: `test_get_job_newly_submitted_is_queued` (Test 2) calls `http_session.get(f"{base_url}/jobs/{job_id}")` directly. `test_delete_queued_job_cancels_it` (Test 3) calls `http_session.delete(f"{base_url}/jobs/{job_id}")` directly. Neither calls `_handle_poll_remote_job` or `_handle_cancel_remote_job`.
- **Gap**: The session-spawner MCP tool layer (fan-out logic, worker-name resolution, field normalization, auth error handling) is not exercised end-to-end against a real in-process worker for poll or cancel. Test 4 correctly uses `_handle_spawn_remote_session`. Tests 2 and 3 should do the same for their respective tools.
- **Recommendation**: Replace tests 2 and 3 with calls to `spawner_mod._handle_poll_remote_job` and `spawner_mod._handle_cancel_remote_job` using the configured in-process worker.

### SG2: session-spawner README describes token_usage as omitted when absent

- **Work item reference**: WI-024 implemented always-null token_usage.
- **Current state**: `mcp/session-spawner/README.md` lines 73 and 228 still state "token_usage is included when...Omitted otherwise."
- **Gap**: Documentation contradicts the implementation. Users will write incorrect integration code. WI-023 updated other README content but missed this.
- **Recommendation**: Update lines 73 and 228 to reflect the always-present null behavior.

## Minor Gaps

### MG1: IDEATE_WORKER_MAX_JOBS missing from remote-worker README environment variable table

- **Current state**: The env var table in `mcp/remote-worker/README.md` lists 5 variables but not `IDEATE_WORKER_MAX_JOBS` (added by WI-020).
- **Gap**: Operators cannot discover this configuration option from the README.
- **Recommendation**: Add the row; WI-023 scope was the right time for this.

### MG2: No test for cancel_remote_job with unknown worker_name

- **Current state**: `_handle_cancel_remote_job` handles unknown `worker_name` at lines 947–960 but there is no test for this path. `_handle_poll_remote_job` has an analogous test.
- **Gap**: Coverage asymmetry with poll_remote_job.
- **Recommendation**: Defer — code handles the case correctly; this is a coverage nicety.
