## Verdict: Pass

All findings resolved in rework: C1 (proc.terminate() now gated on `not container_name`), S1 (log message now uses correct binary name), S2 (test now uses monkeypatch.delenv/setenv), M1 (type annotation updated), M2 (test now uses tmp_path). 64 tests pass.

## Critical Findings

### C1: Double docker-stop race between `cancel_job` and `_run_claude_job` finally block

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:319` and `:499`
- **Issue**: `cancel_job` reads `container_name` from the record under the lock (line 305), then calls `docker stop <container>` outside the lock (lines 319–328). Concurrently, `_run_claude_job`'s `finally` block (line 499) sets `record.container_name = None` as soon as the container process exits normally or times out — with no lock held. If the container finishes on its own just as a cancel arrives, `_run_claude_job`'s finally clears `record.container_name` while `cancel_job` already has the name in a local variable and is about to invoke `docker stop`. This is harmless in the success case, but the symmetric race in the other direction is more serious: if `cancel_job` has already called `docker stop` and is waiting on `asyncio.to_thread`, and `_run_claude_job` returns from `proc.communicate()` (because docker stop terminated it), the finally block sets `record.process = None` and `record.container_name = None`. Then `_process_job` updates the record status. Meanwhile `cancel_job` also sets `record.status = "cancelled"` under the lock. Both code paths update `record.status` without coordinating on who wins, and both may call `_evict_terminal_jobs_locked()` in rapid succession — the second call runs after the first already deleted the record from `job_store`, causing a silent no-op eviction on a now-absent entry, which is safe, but the status written by `_process_job` (line 552–554) will overwrite the "cancelled" status written by `cancel_job` (line 306) if `_process_job`'s lock acquisition happens after `cancel_job` releases it but before `_process_job` checks `record.status != "cancelled"`. The check at line 552 guards against this only if `_process_job` acquires the lock after `cancel_job` has set the status. Because both run concurrently and the lock is the only ordering mechanism, the outcome depends on scheduling. In practice the cancel guard works, but the log message at line 536 ("claude not found") fires on the docker-not-found path even though docker was found; see S1 for that. The true critical concern here is that `proc.terminate()` at line 333 is called even when the process was already stopped by `docker stop`, because `proc` is the `docker run` parent process. `docker stop` sends SIGTERM/SIGKILL to the container, which causes `docker run` to exit, but `cancel_job` then also calls `proc.terminate()` on the already-exited `docker run` process. This is safe because `ProcessLookupError` is caught, so it is not a crash — but it means the exception handling path in `cancel_job` is exercised on every container cancel, not just on edge cases.
- **Impact**: No crash occurs because exceptions are swallowed. However, `cancel_job` unconditionally calls `proc.terminate()` on the `docker run` process that `docker stop` already caused to exit. The real exposure is the status race: on a slow event loop, `_process_job` can set status to "completed" or "failed" after `cancel_job` sets it to "cancelled" if `_process_job`'s `async with job_store_lock` block at line 546 is entered after `cancel_job` releases the lock at line 316 but before `_process_job` re-acquires it after `_capture_git_diff` at line 540. The `if record.status != "cancelled"` guard at line 552 prevents the status overwrite, so the status itself is safe. The double `_evict_terminal_jobs_locked()` invocation is also safe. The concrete harm is that `proc.terminate()` always fires on container jobs even when unnecessary; this is low-severity but is structurally wrong.
- **Suggested fix**: After calling `docker stop`, set a flag so the subsequent `proc.terminate()` block is skipped for container jobs. The simplest fix: replace the unconditional `if proc is not None:` block at line 331 with `if proc is not None and not container_name:` — since `docker stop` already caused `docker run` to exit, there is nothing for `proc.terminate()` to do. Alternatively, after `docker stop` returns, skip the terminate/wait block entirely by wrapping it:
  ```python
  if proc is not None and not container_name:
      try:
          proc.terminate()
      ...
  ```
  This is safe because `docker stop` already delivers SIGTERM (then SIGKILL after 10 s) to the container, and `docker run` exits as a result.

## Significant Findings

### S1: Log message hard-codes "claude not found" for the docker-missing case

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:536`
- **Issue**: The log line at line 536 reads `"Job %s failed (claude not found) in %dms"` for every `_FILE_NOT_FOUND` result, including the container-mode case where the actual error is "docker not found on PATH". The error text stored in `record.error` is correct (differentiates docker vs claude), but the log message always says "claude not found".
- **Impact**: Operators tailing logs in container mode will see "claude not found" when the real cause is a missing `docker` binary. This makes incident diagnosis slower and may send operators chasing the wrong binary.
- **Suggested fix**: Change line 536 to use the `error` variable already in scope:
  ```python
  logger.info("Job %s failed (binary not found: %s) in %dms", record.job_id, error, duration_ms)
  ```
  Or at minimum detect container mode:
  ```python
  label = "docker not found" if worker_mod._agent_image else "claude not found"
  logger.info("Job %s failed (%s) in %dms", record.job_id, label, duration_ms)
  ```

### S2: `patch.dict(os.environ, env_without_key, clear=True)` is not reliable across async context switches in the container-mode API-key test

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/test_server.py:667`
- **Issue**: `patch.dict` with `clear=True` replaces `os.environ` for the duration of the `with` block at the thread level. The test body is synchronous inside the `with` block (it constructs an `AsyncClient` and `await`s the POST), but `await` yields control to the event loop, which may run other coroutines or tasks that read `os.environ`. If those coroutines or tasks happen to set or read `ANTHROPIC_API_KEY`, the patched environment may bleed into or out of them unexpectedly. More concretely: `patch.dict` modifies the global `os.environ` dict in-place (it does not replace the dict object, so all threads and coroutines sharing the process see the change). Any concurrently-running coroutine that reads `os.environ.get("ANTHROPIC_API_KEY")` between the `patch.dict` enter and exit will observe the absence of the key, even if it belongs to a different test. In a sequential `pytest-asyncio` run with a single event loop this is acceptable, but if tests are ever parallelised (e.g. `pytest-xdist`) this becomes a cross-test data race.
- **Impact**: Test isolation is fragile. If the test suite is later run with worker threads or parallel event loops, this test can produce false positives or pollute other tests' environments. Currently the test passes reliably because `pytest-asyncio` uses a single-threaded event loop per test.
- **Suggested fix**: Use `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)` and `monkeypatch.setenv("IDEATE_WORKER_API_KEY", TEST_API_KEY)` instead of `patch.dict`. The `monkeypatch` fixture is already available in the test signature and restores the environment atomically at teardown, without the `clear=True` nuclear option:
  ```python
  monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
  monkeypatch.setenv("IDEATE_WORKER_API_KEY", TEST_API_KEY)
  monkeypatch.setattr(worker, "_agent_image", "outpost-agent:latest")
  async with AsyncClient(...) as ac:
      resp = await ac.post(...)
  ```

## Minor Findings

### M1: `_run_claude_job` return-type annotation is incorrect after cycle 9 changes

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:440`
- **Issue**: The function signature declares `-> tuple[str, int, str | None]` but the function now has three distinct return shapes: `(sentinel_object, str)`, `None`, and `(str, int, str | None)`. The annotation covers only the last case.
- **Suggested fix**: Update the annotation to reflect the union:
  ```python
  def _run_claude_job(record: JobRecord) -> tuple[str, int, str | None] | tuple[object, str] | None:
  ```
  Or introduce a named result type to avoid the opaque `object` sentinel in the annotation.

### M2: `test_cancel_running_container_job_calls_docker_stop` uses `/tmp` as `working_dir` without checking it exists

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/test_server.py:1488`
- **Issue**: The `JobRecord` is constructed with `working_dir="/tmp"` directly. The `create_job` endpoint validates `working_dir.is_dir()`, but this test bypasses the endpoint and inserts the record directly into `job_store`. On macOS `/tmp` is a symlink to `/private/tmp`, which does exist, but the test silently depends on a platform-specific path rather than using `tmp_path` (which is available in the `monkeypatch` fixture context and is always a real directory).
- **Suggested fix**: Declare `tmp_path` in the test signature and use `str(tmp_path)` for `working_dir`, consistent with the pattern used in other tests in the same file.

## Unmet Acceptance Criteria

None.
