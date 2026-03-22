# Review: WI-049 — Tests for containerized job execution

**Verdict: Pass**

All 6 new tests satisfy the stated acceptance criteria. No critical or significant defects found.

---

## Critical Findings

None.

---

## Significant Findings

None.

---

## Minor Findings

### M1: AC2 assertion does not verify adjacency of `--cap-drop` / `ALL`

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/test_server.py:1364-1367`
- **Issue**: The test asserts `"ALL" in cmd` as a free-floating membership check. It does not verify that `"ALL"` is the token immediately following `"--cap-drop"`. If the command were refactored so that `ALL` was passed differently (e.g., `--cap-drop=ALL` as a single token, or the order changed), the assertion would produce a false negative or false positive. The existing tests for `--security-opt` / `no-new-privileges` have the same gap: `"no-new-privileges" in cmd` does not assert it follows `"--security-opt"`.
- **Suggested fix**: Mirror the adjacency pattern used by the bind-mount test and the permission-mode test. For example:
  ```python
  cap_drop_index = cmd.index("--cap-drop")
  assert cmd[cap_drop_index + 1] == "ALL"
  security_opt_index = cmd.index("--security-opt")
  assert cmd[security_opt_index + 1] == "no-new-privileges"
  ```

### M2: Sync tests bypass the `_reset_globals` autouse fixture

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/test_server.py:1333-1445`
- **Issue**: All six new tests are synchronous (`def test_...`). The autouse `_reset_globals` fixture is an `async def` defined with `@pytest_asyncio.fixture`. In pytest-asyncio auto mode, async fixtures are not injected into synchronous test functions. As a result, `worker.job_store`, `worker._max_jobs`, and `worker.job_queue` are not reset between these tests. The tests work today because they call `_run_claude_job` directly without touching `job_store`, but the isolation contract is weaker than it appears.
- **Suggested fix**: Either convert the six new tests to `async def` (making them eligible for the existing autouse fixture), or extract the reset logic into a synchronous autouse fixture that applies universally:
  ```python
  @pytest.fixture(autouse=True)
  def _reset_sync_globals():
      worker.job_store.clear()
      worker._agent_image = ""
      worker._container_runtime = ""
      yield
      worker.job_store.clear()
      worker._agent_image = ""
      worker._container_runtime = ""
  ```
  Note that `monkeypatch` already handles `_agent_image` and `_container_runtime` within each test, so the practical risk is low — but the fixture gap is a latent trap for future test authors.

### M3: `_make_mock_proc` default `stdout` value is a plain string, not JSON

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/test_server.py:1325-1330`
- **Issue**: `_make_mock_proc` defaults `stdout="output"`, which is not valid JSON. `_run_claude_job` itself does not parse stdout (that happens upstream in the caller), so this does not cause a failure in the tests as written. However, if a future test reuses `_make_mock_proc` and passes the return value through the full `_process_job` path, it will produce an uninformative failure rather than a meaningful one.
- **Suggested fix**: Default to a valid JSON string consistent with what the rest of the test suite uses: `stdout='{"result": "ok"}'`.

---

## Unmet Acceptance Criteria

None. All seven criteria are satisfied:

1. `test_container_mode_uses_docker_run` asserts `cmd[0] == "docker"` and `"run" in cmd`.
2. `test_container_mode_includes_security_opts` asserts `"--cap-drop"`, `"ALL"`, `"--security-opt"`, and `"no-new-privileges"` are present in the command.
3. `test_container_mode_includes_bind_mount` asserts `cmd[v_index + 1] == f"{working_dir}:/workspace"`.
4. `test_container_mode_uses_dangerously_skip_permissions` sets `permission_mode="acceptEdits"` on the record and asserts the command contains `"dangerouslySkipPermissions"`.
5. `test_no_container_mode_uses_claude` asserts `cmd[0] == "claude"` when `_agent_image` is empty.
6. `test_container_mode_custom_runtime` asserts `"--runtime"` is present and `cmd[runtime_index + 1] == "runsc"`.
7. All 53 tests pass (`pytest mcp/remote-worker/test_server.py` — confirmed by execution).
