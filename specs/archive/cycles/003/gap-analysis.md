# Gap Analysis — Cycle 003

**Date**: 2026-03-16
**Scope**: Full project — session-spawner, remote-worker, roles, manager agent, integrations, infrastructure

---

## Missing Requirements from Interview

None.

All requirements from the interview have been implemented. Future directions mentioned (session result caching, priority queue support, worker pool auto-scaling, WebSocket transport, cloud provider integration) were explicitly listed as "not currently planned" in the interview.

---

## Unhandled Edge Cases

### EC1: Job Store Memory Leak in Remote Worker
- **Component**: `mcp/remote-worker/server.py` — `job_store` dictionary
- **Scenario**: Over long-running operation, the job_store accumulates completed/failed/cancelled jobs indefinitely.
- **Current behavior**: Jobs are never removed from job_store. Memory usage grows linearly with total jobs submitted.
- **Expected behavior**: Should have a mechanism to purge old completed jobs.
- **Severity**: Significant
- **Recommendation**: Address now — Long-running workers will eventually exhaust memory.

### EC2: Claude CLI Not on PATH Produces Unclear Error
- **Component**: Both `mcp/session-spawner/server.py` and `mcp/remote-worker/server.py`
- **Scenario**: The `claude` binary is not installed or not on PATH.
- **Current behavior**: subprocess.Popen will raise FileNotFoundError.
- **Expected behavior**: Should catch this and provide a helpful error message.
- **Severity**: Significant
- **Recommendation**: Address now — Per Constraint 2, there's no fallback. Clear error message essential.

### EC3: Very Large git_diff Output
- **Component**: `mcp/remote-worker/server.py` — `_capture_git_diff()`
- **Scenario**: A job makes extensive changes resulting in a very large git diff.
- **Current behavior**: The full diff is captured and stored in memory. No size limits.
- **Expected behavior**: Should apply truncation logic similar to session output.
- **Severity**: Significant
- **Recommendation**: Address now — Consistent with Constraint 7 (Output Size Limits).

### EC4: Remote Worker URL with Trailing Slash
- **Component**: `mcp/session-spawner/server.py` — URL construction
- **Scenario**: Worker URL configured with trailing slash.
- **Current behavior**: URLs constructed by simple string concatenation may create double slashes.
- **Expected behavior**: Should normalize URLs to avoid double slashes.
- **Severity**: Minor
- **Recommendation**: Defer — Most HTTP servers handle double slashes gracefully.

### EC5: Simultaneous Cancellation and Completion Race
- **Component**: `mcp/remote-worker/server.py` — `cancel_job()` and `_process_job()`
- **Scenario**: A job is cancelled at the exact moment it completes naturally.
- **Current behavior**: Potential race between status check and process signal.
- **Expected behavior**: Should handle the case where the process has already exited.
- **Severity**: Minor
- **Recommendation**: Defer — Current implementation handles this reasonably well.

### EC6: Session Spawner HTTP Session Creation Per Request
- **Component**: `mcp/session-spawner/server.py` — `_get_http_session()`
- **Scenario**: New aiohttp ClientSession created for each HTTP request.
- **Current behavior**: While timeouts are configured, creating a new session per request is inefficient.
- **Expected behavior**: Should reuse a single ClientSession or use connection pooling.
- **Severity**: Significant
- **Recommendation**: Address now — Resource efficiency for orchestration tool.

---

## Incomplete Integrations

### II1: No Integration Tests Between Components
- **Interface**: HTTP API between session-spawner and remote-worker
- **Gap**: No integration tests that verify the two components work together. All tests use mocks.
- **Severity**: Significant
- **Recommendation**: Address now — Integration tests essential for verifying contract.

### II2: Role System Documentation Contradicts Implementation
- **Interface**: Role constraints propagation
- **Gap**: README states role is "observability label only" but implementation propagates constraints.
- **Severity**: Significant
- **Recommendation**: Address now — Documentation should match implementation.

### II3: No Health Check for Local Session Spawner
- **Interface**: MCP server health/monitoring
- **Gap**: No health endpoint or status reporting for session-spawner itself.
- **Severity**: Minor
- **Recommendation**: Defer — MCP server is stateless per Principle 11.

### II4: Missing Cancellation Support for Local Sessions
- **Interface**: spawn_session tool
- **Gap**: No mechanism to cancel a running local session (remote jobs can be cancelled).
- **Severity**: Significant
- **Recommendation**: Address now — Inconsistent UX between local and remote dispatch.

---

## Missing Infrastructure

### MI1: No Structured Logging Configuration
- **Category**: Logging
- **Gap**: Session-spawner uses basic logging with no configuration.
- **Severity**: Minor
- **Recommendation**: Defer — Code works, operational visibility reduced.

### MI2: No Metrics or Telemetry Export
- **Category**: Observability
- **Gap**: No Prometheus metrics or other telemetry export.
- **Severity**: Minor
- **Recommendation**: Defer — Out of scope per interview.

### MI3: No Request ID Propagation
- **Category**: Observability
- **Gap**: No correlation IDs passed between parent and child sessions.
- **Severity**: Minor
- **Recommendation**: Defer — Nice to have but not essential.

### MI4: No Configuration Validation at Startup
- **Category**: Configuration
- **Gap**: Invalid configuration only discovered when relevant tool is called.
- **Severity**: Significant
- **Recommendation**: Address now — Fail fast on invalid configuration.

### MI5: No Graceful Shutdown Handling
- **Category**: Process Management
- **Gap**: If MCP server is terminated, running local sessions continue (orphaned).
- **Severity**: Significant
- **Recommendation**: Address now — Should track and terminate spawned processes on shutdown.

### MI6: No Retry Logic for Transient Failures
- **Category**: Resilience
- **Gap**: No retry with backoff for transient remote worker failures.
- **Severity**: Significant
- **Recommendation**: Address now — Principle 3 (Graceful Degradation) mentions handling worker unavailability.

---

## Implicit Requirements

### IR1: Meaningful Error Messages
- **Expectation**: Clear, actionable error messages for configuration issues.
- **Current state**: Some errors expose internal details or are too terse.
- **Severity**: Significant
- **Recommendation**: Address now — Part of basic usability.

### IR2: API Documentation for Error Responses
- **Expectation**: All API endpoints should document error responses.
- **Current state**: Some errors not documented (e.g., 500 internal server error).
- **Severity**: Minor
- **Recommendation**: Defer — Main error cases are documented.

### IR3: Consistent Environment Variable Naming
- **Expectation**: Consistent naming pattern (all `OUTPOST_*`).
- **Current state**: Remote-worker uses `IDEATE_WORKER_*` prefix.
- **Severity**: Minor
- **Recommendation**: Defer — Breaking change to rename.

### IR4: Working Directory Permission Validation
- **Expectation**: Verify read/write access before spawning.
- **Current state**: Only checks if directory exists.
- **Severity**: Minor
- **Recommendation**: Defer — Subprocess error is usually clear.

### IR5: Confirmation for Destructive Operations
- **Expectation**: Safeguards for job cancellation.
- **Current state**: DELETE immediately cancels without confirmation.
- **Severity**: Minor
- **Recommendation**: Defer — API not interactive CLI.

### IR6: Version Compatibility Check
- **Expectation**: Components verify version compatibility.
- **Current state**: No version checking between components.
- **Severity**: Minor
- **Recommendation**: Defer — Components deployed together from same repo.

### IR7: Security Hardening Documentation
- **Expectation**: Security-sensitive deployment documentation.
- **Current state**: Basic auth documented, no hardening guide.
- **Severity**: Significant
- **Recommendation**: Address now — Essential for production use.

### IR8: Clear Documentation of Resource Limits
- **Expectation**: Single reference for resource limits.
- **Current state**: Limits documented but scattered.
- **Severity**: Minor
- **Recommendation**: Defer — Information exists, just not consolidated.

---

## Summary

| Category | Critical | Significant | Minor | Total |
|----------|----------|-------------|-------|-------|
| Missing Requirements | 0 | 0 | 0 | 0 |
| Unhandled Edge Cases | 0 | 3 | 3 | 6 |
| Incomplete Integrations | 0 | 3 | 1 | 4 |
| Missing Infrastructure | 0 | 3 | 2 | 5 |
| Implicit Requirements | 0 | 2 | 5 | 7 |
| **Total** | **0** | **11** | **11** | **22** |

**Key Findings**:

1. **Job Store Memory Leak**: The remote worker's job store grows without bound.

2. **Missing Integration Tests**: No end-to-end tests verifying HTTP integration between components.

3. **Documentation Contradiction**: Role system README contradicts implementation.

4. **No Local Session Cancellation**: Inconsistent UX between local and remote dispatch.

5. **Configuration Validation**: Invalid config only discovered at runtime.

**Recommendations**:

- **Address Now (Significant)**: EC1, EC2, EC3, EC6, II1, II2, II4, MI4, MI5, MI6, IR1, IR7
- **Defer**: EC4, EC5, II3, MI1, MI2, MI3, IR2, IR3, IR4, IR5, IR6, IR8
