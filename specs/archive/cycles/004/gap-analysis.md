## Gap Analysis — Cycle 4

### Resolved This Cycle

- **CF1**: Integration test with real subprocess — CLOSED. `test_job_lifecycle_running_to_completed` starts a worker coroutine explicitly, submits via `put_nowait`, and drives a real `sys.executable` subprocess through `_process_job` to completion.

- **NG1**: Ambiguous FileNotFoundError sentinel — CLOSED. `_FILE_NOT_FOUND = object()` sentinel used; `_process_job` detects via identity check. Zero-stdout exit-1 results no longer misrouted.

### Carried Forward

- **CF2** (Minor): `_worker` silently drops cancelled-while-queued jobs — no test for this path.
- **CF3** (Minor): No test for `_process_job` cancel path (`result is None`, only `duration_ms` set).
- **CF5** (Minor): No test for `cancel_job` SIGKILL fallback (2s timeout branch).
- **CF7** (Minor): No test for MCP tool schema validation (missing required fields).
- **NG2** (Minor): `list_jobs` response omits `started_at` and `completed_at`.
- **NG3** (Minor): Auth layer not exercised in MCP handler integration test flows.
- **NC1** (Minor): No test for `_handle_spawn_remote_session` when all workers unreachable.
- **NC2** (Minor): No test for the mixed-error fallback branch added by WI-040 (error_workers + not_found_workers).

### New Gaps (Cycle 4)

- **NG4** (Minor): `put_nowait` in `submit_job` enqueues job_id before inserting into `job_store`. The asyncio event loop won't yield between these operations within the same coroutine frame, so no race occurs in practice — but the ordering is semantically incorrect (a worker could theoretically dequeue a job_id with no store entry). Correct ordering is: store-then-enqueue.

### Summary

CF1 and NG1 are fully closed. No significant gaps remain. All open gaps are Minor deferred items concerning edge-case test coverage, operational observability (list_jobs timestamps), and a low-risk ordering issue (NG4). The codebase is functionally correct and well-covered for the main execution paths.
