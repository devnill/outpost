## Verdict: Fail

Container mode introduces a secret-in-process-args vulnerability and is missing a cancel-path test for the `docker stop` branch.

## Critical Findings

None.

## Significant Findings

### S1: ANTHROPIC_API_KEY embedded in command list, visible in process table
- **File**: `mcp/remote-worker/server.py:415`
- **Issue**: The API key is passed as `"-e", f"ANTHROPIC_API_KEY={os.environ.get('ANTHROPIC_API_KEY', '')}"` — the value is baked into the command list as a single string element `ANTHROPIC_API_KEY=<secret>`. On Linux/macOS, any user with access to `ps aux` or `/proc/<pid>/cmdline` can read the full `docker run` command line, including the key value.
- **Impact**: Any local user on the remote-worker host can extract the Anthropic API key from the process table while a container job is running. On a multi-tenant machine this is a full key compromise.
- **Suggested fix**: Pass the key via `--env-file` (write a temp file readable only by the server process user) or pass the key name only and rely on the key already being present in the server environment that Docker inherits: `"-e", "ANTHROPIC_API_KEY"` (without a value). When the value is omitted, Docker inherits the variable from the host process environment without embedding it in the command line. Replace line 415 with:
  ```python
  "-e", "ANTHROPIC_API_KEY",
  ```
  This works because the remote-worker process itself already has `ANTHROPIC_API_KEY` in its environment; `docker run -e VAR` without a value passes the host value through without exposing it in `cmdline`.

### S2: No test for `docker stop` invocation on cancel of running containerized job
- **File**: `mcp/remote-worker/test_server.py` (no such test)
- **Issue**: `cancel_job` calls `subprocess.run(["docker", "stop", container_name], ...)` when `container_name` is set (server.py:308-316). There is no test that sets `record.container_name` and verifies that `docker stop` is called with the correct container name (`job-{job_id}`). The six new container-mode tests (WI-049) cover `_build_container_cmd` and `_run_claude_job`, but none exercise the cancel path.
- **Impact**: A regression in the `docker stop` call (wrong name format, wrong timeout, suppressed exceptions) will go undetected by the test suite.
- **Suggested fix**: Add an async test that sets `record.status = "running"` and `record.container_name = f"job-{job_id}"`, patches `subprocess.run`, calls `DELETE /jobs/{job_id}`, and asserts `subprocess.run` was called with `["docker", "stop", f"job-{job_id}"]`.

## Minor Findings

### M1: WI-048 M1 — `_evict_terminal_jobs_locked` not called in cancel-while-starting path
- **File**: `mcp/remote-worker/server.py:502-506`
- **Issue**: When `_run_claude_job` returns `None` (cancel-while-starting sentinel), `_process_job` acquires the lock and sets `record.duration_ms` but does not call `_evict_terminal_jobs_locked()`. The record is already in `cancelled` state (set by `cancel_job`, which did call the eviction function at line 299), so no eviction is needed at that moment. However, if the job was cancelled *before* it was ever picked up by a worker (i.e., the `cancel_job` eviction ran when the store was not over capacity, then more jobs arrived), and now the store is at capacity, this path silently skips eviction.
- **Suggested fix**: Add `_evict_terminal_jobs_locked()` after setting `record.duration_ms` in the `result is None` branch (server.py line 505), consistent with every other terminal-state transition in `_process_job`.

### M2: `-e ANTHROPIC_API_KEY=` passes empty string to container when key is not set in environment
- **File**: `mcp/remote-worker/server.py:415`
- **Issue**: `os.environ.get('ANTHROPIC_API_KEY', '')` falls back to an empty string if the env var is absent. This means the container starts with `ANTHROPIC_API_KEY=` (empty), and the Claude CLI inside the container will fail with an unhelpful auth error rather than a clear configuration error surfaced at job submission time.
- **Suggested fix**: At job submission time (in `create_job`) or in `_build_container_cmd`, check that `ANTHROPIC_API_KEY` is non-empty when `_agent_image` is set and return an actionable error (HTTP 500 with a message like "ANTHROPIC_API_KEY is not set on the worker") before starting the container. This is independent of the S1 fix.

### M3: `_build_container_cmd` reads module-level `_agent_image`/`_container_*` globals at call time, not at startup
- **File**: `mcp/remote-worker/server.py:34-37, 403-415`
- **Issue**: `_agent_image`, `_container_runtime`, `_container_memory`, and `_container_cpus` are read from `os.environ` at module import time. If the environment changes after the process starts (uncommon but possible via `os.environ` mutation in tests or dynamic reconfiguration), the values used in `_build_container_cmd` may not reflect the current state. The test fixture works around this by directly setting `worker._agent_image = ""`, which works but couples tests to implementation internals.
- **Suggested fix**: This is acceptable for a production server (env vars are fixed at startup). The test coupling is the practical concern — it is already handled correctly by the fixture. No code change is required, but document in a comment that these are intentionally snapshot-at-import-time.

## Suggestions

### Suggestion 1: Add `--read-only` to the container command
The container runs with `--cap-drop ALL` and `--no-new-privileges`, which is good. Adding `--read-only` with a writable `/workspace` tmpfs overlay would prevent writes to any path outside the bind mount. This would make escaping the workspace directory via the container filesystem much harder.

### Suggestion 2: Consider `--network none` for jobs that do not require network access
The current container command has no `--network` constraint. For worker roles that are purely file-manipulation (e.g., `reviewer`), `--network none` would eliminate a class of exfiltration risk. The `allowed_tools` field on the request could inform this decision.
