# Spec Adherence Review — Cycle 5

## Verdict: Fail

The implementation satisfies all code-level criteria and guiding principles, but documentation artifacts introduced by WI-023 and WI-024 contain two inconsistencies that violate GP-4 (Transparency and Observability) and observability P-3.

## Principle Violations

### GP-4 / observability P-3: session-spawner README contradicts WI-024 implementation

- **Files**: `mcp/session-spawner/README.md:73`, `mcp/session-spawner/README.md:228`
- **Issue**: The README states "token_usage is included when the spawned session returns JSON output containing token information. Omitted otherwise." (line 73) and repeats this at line 228. WI-024 changed the implementation to always include `token_usage: null` when absent — this is the correct behavior per observability P-3. The README documentation was not updated to reflect the new contract.
- **Impact**: Users reading the README will write incorrect integration code, checking `"token_usage" in response` rather than `response.get("token_usage") is not None`.
- **Required fix**: Update lines 73 and 228 in README to state that `token_usage` is always present, with a `null` value when unavailable.

## Architecture Deviations

### cancel_remote_job not documented in architecture.md component map or session-spawner README tool list

- **File**: `specs/plan/architecture.md`, `mcp/session-spawner/README.md`
- **Issue**: WI-019 added `cancel_remote_job` as a new MCP tool. WI-023 updated documentation but did not add `cancel_remote_job` to the architecture.md component map tool list or to the session-spawner README tool summary.
- **Impact**: Architecture documentation is incomplete; the tool table and README tool list describe only 4 tools while the implementation has 5.
- **Required fix**: Add `cancel_remote_job` to architecture.md Component Map tool list and to session-spawner README tool table.

## Minor Deviations

### `IDEATE_WORKER_MAX_JOBS` absent from remote-worker README environment variable table

- **File**: `mcp/remote-worker/README.md` environment variable table
- **Issue**: WI-020 added `IDEATE_WORKER_MAX_JOBS` (default 1000, controls job store eviction). WI-023 updated documentation but the env var table in the README was not updated to include this new configuration option.
- **Impact**: Operators cannot discover this configuration option from the README.
- **Suggested fix**: Add `IDEATE_WORKER_MAX_JOBS` row to the env var table.

### Architecture.md health endpoint response not updated to include max_jobs field

- **File**: `specs/plan/architecture.md`
- **Issue**: WI-020 added `"max_jobs": _max_jobs` to the health endpoint response. The architecture.md health endpoint spec was not updated.
- **Impact**: Documentation of the health response is incomplete.
- **Suggested fix**: Add `max_jobs` to the health response schema in architecture.md.
