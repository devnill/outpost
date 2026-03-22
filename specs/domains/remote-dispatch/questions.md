# Questions: Remote Dispatch

## Q-1: Caller recovery pattern when a worker restarts and clears the queue
- **Question**: The job queue is in-memory (C16). When a worker restarts, all queued and running jobs are lost. What is the expected caller-side recovery pattern? Should spawn_remote_session callers detect this and re-submit, or is this entirely caller-managed?
- **Source**: steering/constraints.md (C16)
- **Impact**: Without a documented recovery pattern, callers may silently lose work when a worker restarts during a long execution run.
- **Status**: open
- **Reexamination trigger**: A user reports lost jobs after a worker restart during brrr execution.

## Q-2: Worker selection strategy when multiple workers are configured
- **Question**: When `spawn_remote_session` is called without specifying `worker_url`, the job goes to "the first configured worker." Is there any load-balancing or affinity logic, or is it always index-0?
- **Source**: plan/architecture.md S3 (spawn_remote_session definition)
- **Impact**: Uneven load distribution across a worker pool; all unrouted jobs pile onto one worker while others are idle.
- **Status**: open
- **Reexamination trigger**: A user configures multiple workers and reports uneven utilization.

## Q-3: Should poll_remote_job prioritize found results over auth errors in multi-worker fanout?
- **Question**: D-5 (cycle 1) established that auth errors take priority and cause immediate return. Cycle 2 code-quality review S1 found this causes a single misconfigured worker to block all polls. Should the priority be reversed so found results are returned even when another worker has an auth error?
- **Source**: archive/cycles/002/code-quality.md (S1), archive/cycles/002/summary.md (OQ-005)
- **Impact**: One stale API key in `OUTPOST_REMOTE_WORKERS` permanently blocks all `poll_remote_job` calls that omit `worker_name`. GP-3 (Graceful Degradation) is violated.
- **Status**: resolved — 2026-03-16
- **Resolution**: Reorder fan-out to check found results before auth errors. Addressed by D-13.

## Q-4: Should role constraints apply to remote sessions, and where should resolution happen?
- **Question**: Remote worker receives `role` as a label but does not apply `allowed_tools`, `system_prompt`, or `permission_mode`. GP-8 requires role constraints for all sessions. Two options: (a) session-spawner resolves the role at dispatch time and sends resolved fields in the HTTP payload; (b) remote-worker loads role definitions locally and applies them. Each has different deployment implications.
- **Source**: archive/cycles/002/summary.md (OQ-003), archive/cycles/002/gap-analysis.md (IG2), archive/cycles/002/spec-adherence.md (P3)
- **Impact**: A "reviewer" session spawned remotely has unrestricted tool access despite the role definition limiting it to read-only.
- **Status**: resolved — 2026-03-16
- **Resolution**: Option A. Session-spawner resolves role at dispatch time and sends resolved `allowed_tools` and `permission_mode` in the HTTP payload. Addressed by D-11/D-15.

## Q-5: Should running remote jobs be cancellable?
- **Question**: `DELETE /jobs/{id}` returns HTTP 409 for `running` jobs. The `cancelled` state is defined but unreachable from `running`. No signal is sent to the subprocess.
- **Source**: archive/cycles/002/gap-analysis.md (IG3)
- **Impact**: Users running long remote jobs have no abort mechanism short of restarting the daemon. Requires tracking the subprocess handle in `JobRecord`.
- **Status**: resolved — 2026-03-16
- **Resolution**: Implement cancellation. Track `Popen` handle in `JobRecord.process`. `cancel_job` sends SIGTERM, waits 2s, then SIGKILL. Addressed by D-12/D-16.

## Q-6: Should job_store in remote-worker have an eviction policy?
- **Question**: Completed and failed jobs accumulate in `job_store` indefinitely, each holding the full output string. A long-running daemon will grow memory without bound. Should there be a bounded eviction strategy (e.g., max stored jobs, TTL, or delete-after-retrieval)?
- **Source**: archive/cycles/002/code-quality.md (M1), archive/cycles/002/gap-analysis.md (RB1)
- **Impact**: Long-running worker daemon will exhaust heap memory.
- **Status**: resolved
- **Resolution**: LRU eviction implemented via `_evict_terminal_jobs_locked()` with `IDEATE_WORKER_MAX_JOBS` env var (default 1000). Terminal jobs are evicted oldest-first when the store exceeds the limit.
- **Resolved in**: cycle 5

## Q-7: Git diff size limits
- **Question**: Should git_diff output have size limits like session output?
- **Source**: Gap analysis EC3 (archive/cycles/003/gap-analysis.md)
- **Impact**: Very large diffs consume memory; inconsistent with Constraint 7 (Output Size Limits).
- **Status**: open
- **Reexamination trigger**: Memory issues with large workspace changes or consistency requirements.

## Q-8: URL normalization for trailing slash
- **Question**: Should worker URLs with trailing slash be normalized to avoid double slashes?
- **Source**: Gap analysis EC4 (archive/cycles/003/gap-analysis.md)
- **Impact**: URLs constructed by string concatenation may create `//` paths.
- **Status**: open
- **Reexamination trigger**: Worker URL configuration issues or HTTP errors.

## Q-9: Cancellation/completion race condition
- **Question**: Should cancel_job handle the case where process exits between status check and signal?
- **Source**: Gap analysis EC5 (archive/cycles/003/gap-analysis.md)
- **Impact**: Potential race between status check and process signal; exception handling gap.
- **Status**: open
- **Reexamination trigger**: Cancellation reliability issues or error reports.

## Q-10: Retry logic for transient failures
- **Question**: Should remote worker calls have retry with backoff for transient failures?
- **Source**: Gap analysis MI6 (archive/cycles/003/gap-analysis.md)
- **Impact**: Temporary network issues cause immediate failure; violates GP-3 (Graceful Degradation).
- **Status**: open
- **Reexamination trigger**: Network reliability issues or resilience requirements.

## Q-11: Remote-worker README contradicts WI-017 cancellation behavior
- **Question**: `mcp/remote-worker/README.md` states only queued jobs can be cancelled and running jobs return 409. WI-017 extended cancellation to running jobs. Should the README and job lifecycle diagram be updated to reflect this?
- **Source**: archive/cycles/004/gap-analysis.md (SG1), archive/cycles/004/spec-adherence.md (MA2)
- **Impact**: Callers reading the README will not attempt to cancel running jobs, or will expect 409 and not retry. Actual behavior is 204 with successful cancellation.
- **Status**: resolved
- **Resolution**: README updated by WI-023 to reflect that running jobs can be cancelled.
- **Resolved in**: cycle 5

## Q-12: Architecture job-states table incorrect after WI-017
- **Question**: `specs/plan/architecture.md:223` describes `cancelled` as "Cancelled while queued." WI-017 made `cancelled` reachable from both `queued` and `running`. Should the description be corrected to reflect both transitions?
- **Source**: archive/cycles/004/spec-adherence.md (MA2), archive/cycles/004/decision-log.md (OQ-004)
- **Impact**: Architecture document is the definitive reference for job state machine; current description is incomplete.
- **Status**: resolved
- **Resolution**: Architecture job-states table corrected by WI-023 to include both transitions.
- **Resolved in**: cycle 5

## Q-13: cancel_remote_job absent from architecture.md and session-spawner README tool list
- **Question**: WI-019 added `cancel_remote_job` as the fifth MCP tool. WI-023 updated adjacent documentation but did not add it to the architecture.md component map tool list or the session-spawner README tool table. Should both be updated?
- **Source**: archive/cycles/005/spec-adherence.md (Architecture Deviation), archive/cycles/005/decision-log.md (OQ-014)
- **Impact**: Architecture and README describe only 4 tools while the implementation has 5. Callers reading documentation will not discover the cancellation tool.
- **Status**: resolved
- **Resolution**: WI-026 added `cancel_remote_job` to architecture.md component map and session-spawner README tool list.
- **Resolved in**: cycle 6

## Q-14: IDEATE_WORKER_MAX_JOBS absent from remote-worker README env var table
- **Question**: WI-020 added `IDEATE_WORKER_MAX_JOBS` (default 1000) to control job store eviction. The remote-worker README env var table was not updated. Should it be added?
- **Source**: archive/cycles/005/spec-adherence.md (Minor Deviation), archive/cycles/005/decision-log.md (OQ-015)
- **Impact**: Operators cannot discover this configuration option from the README.
- **Status**: resolved
- **Resolution**: WI-026 added `IDEATE_WORKER_MAX_JOBS` row to remote-worker README env var table.
- **Resolved in**: cycle 6

## Q-15: Architecture.md health endpoint schema missing max_jobs field
- **Question**: WI-020 added `max_jobs` to the health endpoint response. The architecture.md health endpoint spec was not updated. Should it be added?
- **Source**: archive/cycles/005/spec-adherence.md (Minor Deviation), archive/cycles/005/decision-log.md (OQ-016)
- **Impact**: Architecture documentation of the health response is incomplete.
- **Status**: resolved
- **Resolution**: WI-026 added `max_jobs` field to architecture.md health endpoint schema.
- **Resolved in**: cycle 6

## Q-16: IDEATE_WORKER_MAX_JOBS absent from architecture.md Section 8 env var table
- **Question**: WI-026 added `IDEATE_WORKER_MAX_JOBS` to the remote-worker README and health schema in architecture.md, but the architecture.md Section 8 configuration env var reference table was not updated. Should the env var be added there as well?
- **Source**: archive/cycles/006/gap-analysis.md (MG1), archive/cycles/006/decision-log.md (OQ-020)
- **Impact**: The architecture env var table is secondary documentation (README is primary), but completeness is expected. Operators consulting the architecture reference will not find this env var.
- **Status**: open
- **Reexamination trigger**: Next documentation or maintenance pass.

## Q-17: max_jobs absent from list_remote_workers output
- **Question**: `_fetch_worker_health` in session-spawner does not forward the `max_jobs` field from the remote-worker `/health` response, despite the field being specified in architecture.md section 3 and available in the worker response. Should `max_jobs` be added to the forwarded fields?
- **Source**: archive/cycles/007/spec-adherence.md (D1/MD1), archive/cycles/007/decision-log.md (OQ-022)
- **Impact**: Callers using `list_remote_workers` cannot see the job store capacity of each worker, making capacity planning opaque. One-line fix at `mcp/session-spawner/server.py:684`.
- **Status**: open
- **Reexamination trigger**: Next code fix or documentation pass.

## Q-18: --cwd flag absent from remote-worker _run_claude_job
- **Question**: Remote-worker's `_run_claude_job` sets `cwd=record.working_dir` on the subprocess but does not pass `--cwd` to the Claude CLI, unlike session-spawner which passes both. The `--cwd` flag controls Claude CLI project root for config discovery, CLAUDE.md loading, and trust boundary enforcement. A docstring falsely claims equivalent subprocess patterns between the two servers. Should `--cwd` be added to the remote-worker command, or is the difference intentional?
- **Source**: archive/cycles/007/code-quality.md (M4), archive/cycles/007/decision-log.md (OQ-023)
- **Impact**: Latent correctness risk if Claude CLI `--cwd` handling ever diverges from process cwd inheritance. False docstring claim amplifies the risk by asserting equivalence that does not exist. Preferred fix: add `"--cwd", record.working_dir` to `cmd` at `mcp/remote-worker/server.py:354`.
- **Status**: open
- **Reexamination trigger**: Next code fix pass or Claude CLI behavior change.
