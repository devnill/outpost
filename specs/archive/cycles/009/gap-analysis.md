## Verdict: Pass

Cycle 9 closed all three significant findings from cycle 8 — container mode documentation gaps (DG1, DG2) and the missing eviction call (IG1) — and added the ANTHROPIC_API_KEY pre-flight check, docker stop async handling, and test coverage for those paths. One significant gap and two additional gaps remain.

## Critical Gaps

None.

## Significant Gaps

### SG1: No test for `FileNotFoundError` when docker binary is absent in container mode

The existing `FileNotFoundError` test (`test_run_claude_job_file_not_found_marks_job_failed`) runs with `_agent_image = ""` (autouse fixture resets to empty). It asserts `"claude" in data["error"]`. No test sets `_agent_image` to a non-empty value and raises `FileNotFoundError` from `subprocess.Popen` to exercise the container-mode branch (`"docker not found on PATH. Ensure Docker is installed..."`). The container-mode `FileNotFoundError` branch in `_run_claude_job` is unexercised.

- **Impact**: A deployment where `OUTPOST_AGENT_IMAGE` is set but Docker is not on PATH will produce correct behavior (job marked failed with actionable message), but that behavior is not verified by the test suite.
- **Recommendation**: Add a unit test that (a) sets `_agent_image` to a non-empty string, (b) patches `subprocess.Popen` to raise `FileNotFoundError`, (c) drives `_process_job`, and (d) asserts `"docker"` and `"PATH"` appear in `record.error` and `record.status == "failed"`.

### SG2: `POST /jobs` API reference table omits HTTP 500

The API Reference section of `mcp/remote-worker/README.md` lists only 400 and 401 as error responses for `POST /jobs`. HTTP 500 (ANTHROPIC_API_KEY not set when container mode is active) is documented in prose in the Container Mode section but does not appear in the error responses table. A caller consulting the API Reference for error-handling code will not find 500 listed.

- **Impact**: Callers may treat HTTP 500 from the pre-flight check as an unexpected server fault rather than a configuration error to report to the operator.
- **Recommendation**: Add `500 — ANTHROPIC_API_KEY not set on the worker and container mode is active` to the error responses list under `POST /jobs` in `mcp/remote-worker/README.md`.

## Minor Gaps

### MG1: Container mode integration test bypasses the HTTP layer

`test_container_mode_uses_docker_command_in_worker` drives the worker path by directly enqueuing a job, bypassing `create_job` and the HTTP layer. The ANTHROPIC_API_KEY pre-flight check lives in `create_job`, not in `_process_job` or `_run_claude_job`. A regression where the pre-flight check is removed or misplaced would not be caught by this test.

- **Recommendation**: Add a companion integration test using `worker_server` and `http_session` fixtures to submit a container-mode job via `POST /jobs`, asserting HTTP 201 and correct queue state. Monkeypatching `_agent_image` and the env var is sufficient — no real docker binary needed.

## Suggestions

- The architecture document Section 7 Remote Worker Errors table lists only 400/401 cases. Add the HTTP 500 ANTHROPIC_API_KEY condition as a row for completeness.
- `test_run_claude_job_file_not_found_marks_job_failed` asserts `"claude" in data["error"]` — consider asserting `"PATH"` as well to verify actionability of the message.
