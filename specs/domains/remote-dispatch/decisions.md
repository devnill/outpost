# Decisions: Remote Dispatch

## D-1: HTTP/REST transport, not gRPC or WebSocket
- **Decision**: Remote workers expose a simple HTTP/REST API. No other transport is supported.
- **Rationale**: Broad compatibility and deployment simplicity. HTTP is universally supported without additional client libraries.
- **Source**: steering/constraints.md (C5), steering/interview.md
- **Status**: settled

## D-2: In-memory job queue with no persistence across restarts
- **Decision**: Jobs are queued in the worker process's memory. A worker restart clears the queue. Persistent job queues require an external orchestration layer.
- **Rationale**: Deliberate scope boundary — adding queue persistence would require a database or durable message broker, significantly increasing deployment complexity.
- **Source**: steering/constraints.md (C16)
- **Status**: settled

## D-3: Single-user assumption for remote worker instances
- **Decision**: Each remote worker daemon assumes a single trusted user. Multi-tenant isolation is out of scope; separate worker instances with separate API keys serve multiple users.
- **Rationale**: Multi-tenant isolation requires user identity propagation throughout the job model, adding significant complexity that is not needed for the target use case.
- **Source**: steering/constraints.md (C17)
- **Status**: settled

## D-4: API key comparison uses hmac.compare_digest (not equality)
- **Decision**: API key validation uses `hmac.compare_digest` instead of `!=` string comparison.
- **Rationale**: Timing attack — constant-time comparison prevents character-by-character key recovery by a network-adjacent attacker.
- **Source**: archive/incremental/030-remote-worker-daemon.md (C1)
- **Status**: settled

## D-5: poll_remote_job returns auth error immediately on 401/403
- **Decision**: When polling a job across workers, a 401 or 403 response from any worker causes immediate return of an auth error. The fan-out loop does not continue to the next worker.
- **Rationale**: Auth failure means the caller has a misconfiguration, not a routing issue. Continuing the loop would produce a misleading "job not found" error.
- **Source**: archive/incremental/033-remote-dispatch-tools.md (S2)
- **Status**: settled — superseded by D-13

## D-6: Worker health polling uses concurrent asyncio.gather
- **Decision**: When listing remote workers, health checks for all workers run concurrently via asyncio.gather, not serially.
- **Rationale**: Serial polling creates worst-case latency of N x timeout when any worker is unreachable.
- **Source**: archive/incremental/033-remote-dispatch-tools.md (M3)
- **Status**: settled

## D-7: git_diff captured after job completion when workspace is a git repo
- **Decision**: The remote worker runs `git diff` after a job completes and returns the output to the caller. Non-git workspaces return null for git_diff.
- **Rationale**: Callers can inspect workspace changes without re-reading files. Not enforced as a requirement on the workspace.
- **Assumes**: git is available on the remote host.
- **Source**: plan/architecture.md S4, steering/constraints.md (C18)
- **Status**: settled

## D-8: poll_remote_job should prioritize found results over auth errors
- **Decision**: In the multi-worker fan-out, found results should be checked before auth errors. A single misconfigured worker should not block poll results from a correctly configured worker that has the job.
- **Rationale**: GP-3 (Graceful Degradation) requires that one worker's failure not block the system. The current auth-first priority means one stale API key in `OUTPOST_REMOTE_WORKERS` permanently breaks all polls that omit `worker_name`.
- **Source**: archive/cycles/002/code-quality.md (S1), archive/cycles/002/summary.md (OQ-005)
- **Policy**: Contradicts D-5 — see Q-3
- **Status**: settled — superseded by D-13

## D-9: Role constraints not applied to remote sessions (identified gap)
- **Decision**: The current implementation passes `role` as a label string to the remote worker, but the worker does not resolve the role definition or apply `allowed_tools`, `system_prompt`, or `permission_mode`. Architecture S5 and GP-8 require role constraints for all session types. This gap was identified by all three reviewers.
- **Rationale**: Rationale for the gap not recorded. The architecture and guiding principles do not carve out an exception for remote sessions.
- **Source**: archive/cycles/002/gap-analysis.md (IG2), archive/cycles/002/spec-adherence.md (P3), archive/cycles/002/summary.md (OQ-003)
- **Policy**: None — pending Q-4 resolution
- **Status**: settled — addressed by D-12/D-15

## D-10: Running remote jobs cannot be cancelled
- **Decision**: `DELETE /jobs/{job_id}` returns HTTP 409 for jobs in `running` state. The `cancelled` state is defined in the model but unreachable from `running`. No signal is sent to the subprocess.
- **Rationale**: Cancellation of running jobs requires tracking the subprocess handle in `JobRecord`, which was not implemented. Queued jobs can be cancelled; running jobs cannot.
- **Source**: archive/cycles/002/gap-analysis.md (IG3)
- **Status**: settled — superseded by D-14/D-16

## D-11: Role resolution for remote sessions — Option A
- **Decision**: Session-spawner resolves role definition at dispatch time and sends resolved `allowed_tools` and `permission_mode` in HTTP payload.
- **Rationale**: Option A chosen over Option B — simpler deployment, no need to synchronize role definitions across worker nodes.
- **Assumes**: Role definitions are stable during job execution; workers do not need dynamic role updates.
- **Source**: archive/cycles/003/decision-log.md (Planning phase, 2026-03-16)
- **Status**: settled

## D-12: Running job cancellation implementation
- **Decision**: Implement running job cancellation via SIGTERM/SIGKILL on Popen handle.
- **Rationale**: User confirmed support for cancellation is needed; graceful termination preferred over forceful.
- **Assumes**: Worker processes respond to SIGTERM within reasonable timeframe; SIGKILL as fallback.
- **Source**: archive/cycles/003/decision-log.md (Planning phase, 2026-03-16)
- **Status**: settled

## D-13: poll_remote_job auth-error priority reversal
- **Decision**: Reorder poll_remote_job fan-out so found results are returned before auth errors.
- **Rationale**: Previous behavior violated GP-3 (Graceful Degradation) by surfacing auth errors over successful results.
- **Assumes**: Multi-worker setups should prioritize successful responses over partial failures.
- **Source**: archive/cycles/003/decision-log.md (Execution phase, WI-013)
- **Status**: settled

## D-14: poll_remote_job timestamp field propagation
- **Decision**: Extend `_poll_one()` field copy list to include `created_at`, `started_at`, `completed_at`.
- **Rationale**: Fields were present in worker response but not propagated to caller; incomplete job lifecycle visibility.
- **Assumes**: All timestamp fields should be transparently passed through.
- **Source**: archive/cycles/003/decision-log.md (Execution phase, WI-014)
- **Status**: settled

## D-15: Role constraints applied to remote sessions
- **Decision**: Resolve role in `_handle_spawn_remote_session` before building HTTP payload.
- **Rationale**: Implements D-11 (Option A resolution); satisfies GP-8 (Role-Based Sessions).
- **Assumes**: Role constraints should apply equally to local and remote dispatch.
- **Source**: archive/cycles/003/decision-log.md (Execution phase, WI-015)
- **Status**: settled

## D-16: Running job cancellation via process tracking
- **Decision**: Add `process` field to `JobRecord`; store Popen handle; cancel via SIGTERM/SIGKILL.
- **Rationale**: Implements D-12; requires process handle storage for signal-based cancellation.
- **Assumes**: Process handles remain valid for signal delivery throughout job lifecycle.
- **Source**: archive/cycles/003/decision-log.md (Execution phase, WI-017)
- **Status**: settled

## D-17: Role system_prompt not propagated to remote sessions (regression)
- **Decision**: WI-015 propagated `allowed_tools`, `permission_mode`, and `max_turns` to remote sessions but omitted `system_prompt`. The local spawn path prepends system_prompt to the prompt; the remote dispatch path has no equivalent. This is a regression that silently degrades behavioral role guarantees for remote sessions.
- **Rationale**: WI-015 was scoped to tool constraints and permission mode; system_prompt was not explicitly addressed. The fix is technically straightforward (prepend to `payload["prompt"]`) but requires user decision on whether remote roles should carry full behavioral semantics.
- **Source**: archive/cycles/004/code-quality.md (S1), archive/cycles/004/gap-analysis.md (CG1)
- **Status**: settled — resolved by D-19 in cycle 5

## D-18: Remote-worker README not updated after WI-017 cancellation changes
- **Decision**: WI-017 extended `DELETE /jobs/{job_id}` to handle running jobs (SIGTERM with SIGKILL fallback), but the README still documents only queued-job cancellation and states running jobs return 409. The job lifecycle diagram also omits the `running -> cancelled` transition.
- **Rationale**: WI-017 was scoped to implementation; documentation update was not included in the work item scope.
- **Source**: archive/cycles/004/gap-analysis.md (SG1), archive/cycles/004/decision-log.md (OQ-003)
- **Status**: settled — resolved by D-21 in cycle 5

## D-19: cancel_remote_job MCP tool added
- **Decision**: Add `cancel_remote_job` as the fifth MCP tool in session-spawner. Issues `DELETE /jobs/{id}` to the named worker or fans out across all workers. Fan-out uses continue+error-collection instead of early-return so a misconfigured worker does not abort cancellation for remaining workers.
- **Rationale**: No MCP-level cancellation tool existed; callers had to use HTTP directly to cancel remote jobs. Fan-out error-collection pattern aligns with GP-3 (Graceful Degradation).
- **Source**: archive/cycles/005/decision-log.md (D-019)
- **Status**: settled

## D-20: LRU eviction for remote-worker job store
- **Decision**: Add `_evict_terminal_jobs_locked()` to remote-worker, called under `job_store_lock` after each job reaches terminal state. Eviction count capped at `min(needed, len(terminal))`. Controlled by `IDEATE_WORKER_MAX_JOBS` env var (default 1000). `max_jobs` added to health response.
- **Rationale**: Completed and failed jobs accumulated in `job_store` indefinitely, each holding full output. Long-running daemons would exhaust heap memory without bound. LRU eviction of terminal jobs prevents unbounded growth.
- **Source**: archive/cycles/005/decision-log.md (D-020)
- **Status**: settled

## D-21: README and architecture documentation fixes (cycle 5)
- **Decision**: Targeted corrections to three documentation artifacts: README cancel eligibility updated for running jobs, architecture job-states table corrected, OUTPOST_TIMEOUT annotated as not-implemented, role documentation contradiction resolved in both READMEs. Three documentation gaps remain open (OQ-014, OQ-015, OQ-016).
- **Rationale**: Cycle 4 identified multiple documentation/implementation divergences. WI-023 addressed the highest-impact items.
- **Source**: archive/cycles/005/decision-log.md (D-023)
- **Status**: settled

## D-22: Documentation sweep — cancel_remote_job, IDEATE_WORKER_MAX_JOBS, max_jobs (cycle 6)
- **Decision**: WI-026 closed three remaining documentation gaps: `cancel_remote_job` added to architecture.md component map and session-spawner README tool list; `IDEATE_WORKER_MAX_JOBS` added to remote-worker README env var table; `max_jobs` added to architecture.md health endpoint schema. The architecture.md Section 8 env var reference table was not in scope and still omits `IDEATE_WORKER_MAX_JOBS` (see Q-16).
- **Rationale**: Cycle 5 review identified these as documentation/implementation divergences (OQ-014, OQ-015, OQ-016). Straightforward additions with no design decisions required.
- **Source**: archive/cycles/006/decision-log.md (D-026)
- **Status**: settled

## D-23: --cwd flag divergence identified between session-spawner and remote-worker
- **Decision**: Cycle 7 capstone review identified that remote-worker's `_run_claude_job` sets `cwd=` on the subprocess but does not pass `--cwd` to the Claude CLI, unlike session-spawner which passes both. The `--cwd` flag controls project root for config discovery, CLAUDE.md loading, and trust boundary enforcement. A docstring falsely claims equivalent patterns. Preferred fix is adding `--cwd` to the remote-worker command array (one line) to eliminate the divergence.
- **Rationale**: Process cwd inheritance and `--cwd` flag are currently equivalent in practice, but the divergence is a latent correctness risk if Claude CLI behavior changes. The false docstring claim compounds the risk.
- **Source**: archive/cycles/007/code-quality.md (M4), archive/cycles/007/decision-log.md (RV-004/OQ-023)
- **Status**: settled
