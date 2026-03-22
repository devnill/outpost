# Review: WI-048 — Containerize job execution in `_run_claude_job` (re-review after rework)

**Verdict: Fail**

All three rework items (C1, C2, M2) are correctly implemented. The remaining blocker is S1 from the original review: no tests exercise any container code path, leaving AC2–AC6 and AC9 without automated verification.

---

## Critical Findings

None.

---

## Significant Findings

### S1: No tests exercise the container code path

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/test_server.py` (entire file)
- **Issue**: Every test in the suite runs with `worker._agent_image = ""`. None set that variable and exercise: (a) the `docker run` command built by `_build_container_cmd`, (b) `record.container_name` being set after the cancelled guard and after `record.process`, (c) `cancel_job` calling `docker stop` when `container_name` is set, or (d) `FileNotFoundError` on the `docker` binary producing an error message that names `docker` rather than `claude`. The existing `test_run_claude_job_file_not_found_marks_job_failed` at line 1176 only validates the non-container path, and its assertion `"claude" in data["error"]` would falsely pass even if the container-mode branch were broken to emit a message that still contained the word "claude".
- **Impact**: AC2, AC3, AC4, AC5, AC6, and AC9 have no automated verification. The C1 and C2 fixes in the rework are correct by inspection, but a future regression in either path will not be caught by the test suite.
- **Suggested fix**: Add tests that set `worker._agent_image = "myimage:latest"` before exercising the job path. Minimum required coverage:
  - `_build_container_cmd` contains `--rm`, `--name job-{id}`, `--memory`, `--cpus`, `-v {working_dir}:/workspace`, `--cwd /workspace`, `--permission-mode dangerouslySkipPermissions` (AC3, AC5).
  - `_build_container_cmd` includes `--runtime {value}` when `worker._container_runtime` is non-empty; omits the flag otherwise (AC4).
  - `record.container_name` equals `f"job-{record.job_id}"` after `Popen` succeeds and is `None` after job completion (AC6).
  - `cancel_job` issues `docker stop job-{id}` when `record.container_name` is set (cancel integration).
  - `FileNotFoundError` from `Popen` in container mode produces an error message containing `"docker"` and not `"claude CLI"` (C2 regression guard).

---

## Minor Findings

### M1: `_evict_terminal_jobs_locked` is not called on the cancel-while-starting return path

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:502-506`
- **Issue**: When `_run_claude_job` returns `None` (cancel-while-starting sentinel), `_process_job` updates `duration_ms` but does not call `_evict_terminal_jobs_locked`. The cancelled job was already marked terminal by `cancel_job` but eviction is not triggered. Pre-existing before WI-048 and not introduced by this work item.
- **Suggested fix**: Call `_evict_terminal_jobs_locked()` inside the lock in the `result is None` branch of `_process_job` (line 504).

---

## Rework Verification

### C1: `container_name` set after cancelled guard and after `record.process = proc`

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:461-470`
- **Status**: Correctly fixed. The cancelled guard is at line 462. `record.process = proc` is at line 468. `record.container_name = f"job-{record.job_id}"` is at lines 469-470, guarded by `if _agent_image`. Both assignments occur after the guard, in the correct order.

### C2: `FileNotFoundError` handler branches on `_agent_image`

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:449-460`
- **Status**: Correctly fixed. The `except FileNotFoundError` block branches on `_agent_image` and returns `"docker not found on PATH..."` in container mode and `"claude CLI not found on PATH..."` otherwise.

### M2: `_reset_globals` resets all four container vars

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/test_server.py:122-139`
- **Status**: Correctly fixed. Both the setup side (lines 128-131) and the teardown side (lines 136-139) of the `_reset_globals` fixture reset `_agent_image`, `_container_runtime`, `_container_memory`, and `_container_cpus` to their default values.

---

## Unmet Acceptance Criteria

- [ ] **AC2** — `_run_claude_job` builds `docker run` command when `OUTPOST_AGENT_IMAGE` is set — Implementation is present but has no test coverage.
- [ ] **AC3** — `docker run` command includes all required flags — Implementation is present but has no test coverage.
- [ ] **AC4** — `--runtime {value}` added when `OUTPOST_CONTAINER_RUNTIME` is set — Implementation is present but has no test coverage.
- [ ] **AC5** — Inside container: `--cwd /workspace` and `--permission-mode dangerouslySkipPermissions` — Implementation is present but has no test coverage.
- [ ] **AC6** — `record.container_name` set after cancelled guard and after `record.process = proc`, cleared in `finally` — Implementation is correct (rework confirmed), but has no test coverage.
- [ ] **AC10** — All existing remote-worker tests pass — The existing tests pass, but no new tests were added to cover the container path, so AC10 as written does not confirm container-mode correctness.
