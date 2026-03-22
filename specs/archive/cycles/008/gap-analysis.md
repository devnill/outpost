## Summary

Cycle 8 delivered container sandboxing in the remote-worker and updated the architecture document, but the remote-worker README and root README were not updated to document the new feature. Two significant documentation gaps leave container mode invisible to users. One minor functional correctness gap exists in the cancel-while-starting code path where eviction is not triggered. Integration tests do not cover container mode.

## Missing Requirements

None.

## Integration Gaps

### II1: No integration test for container mode
- **Interface**: Container-mode job submission (session-spawner → remote-worker with `OUTPOST_AGENT_IMAGE` set)
- **Producer**: `mcp/remote-worker/server.py` — `_build_container_cmd` / `_run_claude_job`
- **Consumer**: `mcp/test_integration.py`
- **Gap**: `mcp/test_integration.py` contains no test that sets `worker_mod._agent_image` and verifies the container code path is invoked through the HTTP API. The 6 container unit tests in `mcp/remote-worker/test_server.py` cover command construction in isolation; none exercise the full `POST /jobs` → container invocation path.
- **Severity**: Minor

## Documentation Gaps

### DG1: remote-worker README missing all container mode documentation
- **Expected**: The environment variable table in `mcp/remote-worker/README.md` lists `OUTPOST_AGENT_IMAGE`, `OUTPOST_CONTAINER_RUNTIME`, `OUTPOST_CONTAINER_MEMORY`, and `OUTPOST_CONTAINER_CPUS`. The Prerequisites section notes that Docker must be installed when container mode is in use. A note clarifies that `ANTHROPIC_API_KEY` must be set on the host because it is forwarded into the container.
- **Actual**: The env var table lists only the 6 pre-cycle-8 variables. None of the 4 new container variables appear. Docker is not mentioned in Prerequisites. `ANTHROPIC_API_KEY` is not mentioned.
- **Impact**: A user following the README to deploy container mode has no discoverable configuration. A worker started with `OUTPOST_AGENT_IMAGE` set but without `ANTHROPIC_API_KEY` will silently forward an empty key into each container, causing all container jobs to fail authentication with the Anthropic API.
- **Severity**: Significant

### DG2: Root README has no mention of container mode
- **Expected**: `README.md` mentions Docker sandboxing as a deployment option for the remote-worker, references `mcp/remote-worker/Dockerfile`, and names `OUTPOST_AGENT_IMAGE` as the activation variable.
- **Actual**: The root `README.md` contains no reference to containers, Docker, sandboxing, or the Dockerfile. The Configuration section defers to `mcp/remote-worker/README.md` for the full variable list, which is itself incomplete (DG1).
- **Impact**: Container sandboxing — the primary feature of cycle 8 — is invisible to any user reading the project's primary entry point.
- **Severity**: Significant

## Infrastructure Gaps

### IG1: `_evict_terminal_jobs_locked` not called in cancel-while-starting path
- **Location**: `mcp/remote-worker/server.py:502-507`
- **Gap**: When `_run_claude_job` returns `None` (the cancel-while-starting sentinel), `_process_job` updates `duration_ms` and returns without calling `_evict_terminal_jobs_locked()`. The record is already in `cancelled` state, making it terminal and eligible for eviction. The other three result paths all call `_evict_terminal_jobs_locked()`, but this path does not.
- **Impact**: A job cancelled during Popen initialization remains counted against store capacity without triggering compaction. If the store is at `_max_jobs` and many cancels arrive through this path, the store remains over capacity until the next non-cancel completion triggers eviction. Contradicts Guiding Principle 7 (Resource Bounds).
- **Severity**: Minor
