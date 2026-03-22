# Gap Analysis — Cycle 6

## Summary

Both significant gaps from cycle 5 are closed: SG1 (integration tests bypass MCP layer) is fixed by WI-025, and SG2 (README token_usage contract contradiction) is fixed by WI-026. No new critical or significant gaps were introduced by the cycle 6 changes. Two minor items carry forward from prior cycles.

## Critical Gaps

None.

## Significant Gaps

None.

## Minor Gaps

### MG1: IDEATE_WORKER_MAX_JOBS absent from architecture.md env var table

WI-026 added `IDEATE_WORKER_MAX_JOBS` to the remote-worker README env var table and to the health schema in architecture.md. However, `architecture.md` Section 8 (Configuration env vars reference table) was not in scope for WI-026 and still does not list `IDEATE_WORKER_MAX_JOBS`. The health schema update and README update are complete; only the architecture env var table entry is missing.

**Severity**: Minor — the env var is documented in the README; the architecture table is secondary documentation.

### MG2: Both conftest.py files register as `sys.modules["server"]`

Carry-forward from WI-027 M1. The conftests in `mcp/remote-worker/` and `mcp/session-spawner/` both set `sys.modules["server"]`, which would cause the second registration to overwrite the first. Current tests pass because importlib mode resolves test imports before the collision manifests. Risk arises only if a test file explicitly does `import server`.

**Severity**: Minor — no current test failure; future maintenance risk.

### MG3: OQ-011 remains unaddressed — proc.terminate() without guard

`cancel_job` in `mcp/remote-worker/server.py` calls `record.process.terminate()` without guarding against the process having already exited between lock release and the terminate call. This predates all cycle 5/6 work and was explicitly deferred. No change in status.

**Severity**: Minor — race window is narrow; worst case is a `ProcessLookupError` exception propagating to the caller.
