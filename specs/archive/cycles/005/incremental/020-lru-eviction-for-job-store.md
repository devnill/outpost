## Verdict: Pass

All acceptance criteria satisfied after rework; 36 tests pass.

---
*Rework applied: C1 — eviction count now uses min(needed, len(terminal)) preventing silent under-eviction with warning log; S1 — added lifespan env var tests (valid and invalid); S2 — added max_jobs health field assertion; M2 — renamed function to _evict_terminal_jobs_locked.*

## Critical Findings

### C1: Eviction can remove terminal jobs needed to stay at _max_jobs when non-terminal jobs exceed the limit

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:302-309`
- **Issue**: `_evict_terminal_jobs` computes `evict_count = len(job_store) - _max_jobs` and then deletes exactly that many terminal jobs. If `len(terminal) < evict_count` — which happens whenever there are more non-terminal (running + queued) jobs than `_max_jobs` — the loop silently evicts all terminal jobs but still leaves the store over capacity. This is not a crash, but the invariant `len(job_store) <= _max_jobs` is violated for any store composition where active/queued jobs alone exceed the limit.
- **Impact**: The caller's implicit guarantee that the store is pruned to `_max_jobs` after eviction does not hold in these conditions. All terminal jobs get deleted without bringing the store to the target size, which can surprise callers relying on the invariant. More critically, if `evict_count > len(terminal)`, the slice `terminal[:evict_count]` silently does less work than expected with no warning.
- **Suggested fix**: Add a guard before the loop:
  ```python
  evict_count = min(len(job_store) - _max_jobs, len(terminal))
  ```
  Alternatively, after computing `evict_count`, if `len(terminal) < evict_count`, log a warning that the store cannot be fully pruned because non-terminal jobs exceed the capacity limit.

## Significant Findings

### S1: `_max_jobs` is only initialized during lifespan; tests bypass lifespan and directly mutate `worker._max_jobs`

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/test_server.py:874,919`
- **Issue**: The two new eviction tests set `worker._max_jobs = 2` and `worker._max_jobs = 1` directly, bypassing the lifespan startup that reads `IDEATE_WORKER_MAX_JOBS` from the environment. There is no test that verifies the env var is read correctly at startup — the only startup path coverage is via direct attribute mutation. This means the `ValueError` fallback branch at `server.py:91-92` is untested, and the integration between env var and the startup function is unverified.
- **Impact**: A regression in the env var parsing (e.g., the env var name being changed, or the `int()` conversion being moved) would not be caught by any test.
- **Suggested fix**: Add a test that sets `IDEATE_WORKER_MAX_JOBS` to a valid integer and a non-integer string in the environment, starts the lifespan, and asserts `worker._max_jobs` is set to the expected value. This requires using `AsyncClient` with `lifespan="auto"` or manually invoking the lifespan context manager.

### S2: `test_health_returns_expected_fields` does not assert `max_jobs` is present

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/test_server.py:397-406`
- **Issue**: Acceptance criterion 6 requires `GET /health` to include a `max_jobs` integer field. The new field is present in the implementation (`server.py:162`), but the pre-existing `test_health_returns_expected_fields` test does not assert `"max_jobs" in data`. The two new eviction tests do not check the health endpoint at all. No test verifies the `max_jobs` value in the health response.
- **Impact**: A future refactor that removes or renames the `max_jobs` field from the health response would pass all tests.
- **Suggested fix**: Add `assert "max_jobs" in data` and `assert isinstance(data["max_jobs"], int)` to `test_health_returns_expected_fields`. Optionally add a test that sets `_max_jobs = 42` and asserts the health response returns `"max_jobs": 42`.

## Minor Findings

### M1: Timestamp sort key is lexicographic string comparison, not parsed datetime

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:306`
- **Issue**: `terminal.sort(key=lambda r: r.completed_at or r.created_at or "")` compares ISO 8601 strings lexicographically. This works correctly only because the timestamp format is fixed (`YYYY-MM-DDTHH:MM:SS.mmmZ`) and always zero-padded. If the timestamp format ever changes (e.g., timezone offset instead of `Z`, or sub-millisecond precision), the sort order can silently become incorrect.
- **Suggested fix**: Parse timestamps before sorting, or use a sentinel that guarantees correct ordering:
  ```python
  terminal.sort(key=lambda r: r.completed_at or r.created_at or "0000-00-00T00:00:00.000Z")
  ```
  Better still, store timestamps as `datetime` objects internally and only format them as strings at the API boundary.

### M2: `_evict_terminal_jobs` is called with the lock held but is not marked as requiring the lock in a machine-checkable way

- **File**: `/Users/dan/code/outpost/mcp/remote-worker/server.py:300-309`
- **Issue**: The docstring says "Called under job_store_lock" but there is no enforcement. The function accesses `job_store` directly and is called from three call sites (`cancel_job` at lines 265, 274, and `_process_job` at line 396), all under the lock. If a future call site omits the lock, data will be corrupted silently.
- **Suggested fix**: This is a documentation/convention issue. Consider adding an assertion `assert job_store_lock.locked()` at the top of the function, or rename to `_evict_terminal_jobs_locked` to signal the contract.

## Unmet Acceptance Criteria

- [ ] **Criterion 6**: GET /health response includes `max_jobs` integer field showing configured limit — The field is implemented in the code, but no test asserts its presence or correct value. The pre-existing `test_health_returns_expected_fields` does not check for `max_jobs`, so this criterion is implemented but not verified by the test suite as required by criterion 7's spirit (the two new tests cover eviction behavior but not the health field).
