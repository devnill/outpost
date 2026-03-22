# Decision Log — Cycle 1 (New brrr Session)

**Produced**: 2026-03-22
**Scope**: New brrr session — WI-043 through WI-046 (test additions and minor code fixes addressing 9 deferred gaps from prior brrr session cycle 4)
**Work Items Completed**: 4 (WI-043, WI-044, WI-045, WI-046)
**Final Review Verdict**: Converged — 0 critical, 0 significant (code-quality S1–S4 all stale; see PO-001)

---

## Phase: Planning — Refinement Interview (2026-03-22)

### D-014: Address all 9 minor deferred gaps from prior brrr session cycle 4
- **Decision**: Scope this brrr session to address CF2, CF3, CF5, CF7, NG2, NG3, NG4, NC1, NC2.
- **Rationale**: User confirmed all 9 items should be addressed. No critical or significant issues pending.
- **Implications**: All changes are tests or minor code fixes. No architecture changes.

### D-015: Guiding principles confirmed unchanged
- **Decision**: All 12 guiding principles remain unchanged.

### D-016: OQ-025 explicitly deferred again
- **Decision**: In-memory session registry vs. filesystem-state (OQ-025) not in scope for this session.
- **Implications**: `_session_registry` deque remains in process memory. Session history still lossy on restart unless `OUTPOST_LOG_FILE` configured.

### D-017: Undocumented architecture additions deferred again
- **Decision**: `max_depth`, `output_format`, `team_name`, `exec_instructions`, `OUTPOST_LOG_FILE`, `OUTPOST_ROLES_FILE` absent from architecture sections 3/8 remain deferred.
- **Rationale**: User deferred in 2026-03-21 interview ("come back to this in the next refinement cycle").

---

## Phase: Execution

### D-018: Fix list_jobs to include started_at and completed_at (NG2)
- **Decision**: Add `started_at` and `completed_at` conditionally to each entry in `GET /jobs` list response when non-None.
- **Rationale**: Fields already present on `JobRecord`; simply omitted from list serialization.

### D-019: Store-then-enqueue ordering with QueueFull rollback (NG4)
- **Decision**: Reorder `create_job` to insert into `job_store` before `put_nowait` on `job_queue`. On `QueueFull`, roll back by deleting store entry.
- **Rationale**: Prior ordering created a race where worker could dequeue a job_id not yet in the store.

### D-020: Three cancel-path tests added to remote-worker (CF2, CF3, CF5)
- **Decision**: `test_cf2_worker_skips_cancelled_queued_job`, `test_cf3_process_job_cancel_while_starting_sentinel`, `test_cf5_cancel_running_job_kill_after_terminate_timeout`.
- **Note**: CF5 test produces RuntimeWarning (unawaited coroutine) at teardown. Tests pass. Not fixed in this session.

### D-021: Three session-spawner tests added (NC1, NC2, CF7)
- **Decision**: `test_nc1_spawn_remote_session_all_workers_unreachable`, `test_nc2_cancel_remote_job_mixed_error_fallback`, `test_cf7_tool_schema_required_fields`.
- **Note**: NC2 assertions reworked during incremental review from disjunctive `or` to direct assertions (both "not found" and "Connection refused" must appear).

### D-022: Integration test auth coverage added (NG3)
- **Decision**: Two tests in `mcp/test_integration.py` — wrong-key returns auth error, correct-key returns job_id.
- **Note**: AC1 reworked to add `worker_name` to bypass health-check path and directly exercise POST /jobs 401 branch.

---

## Phase: Review

### Process Observation PO-001: Code-quality reviewer reported four stale significant findings
- **Observation**: S1–S4 reported as significant (FileNotFoundError lock race, communicate() no timeout, unbounded registry, sequential cancel fan-out). All four already addressed by prior work items: S1 by WI-041, S2 by WI-034, S3 by WI-035, S4 by WI-036.
- **Root cause**: Reviewer operated from an outdated mental model. Prior session's WI-034–036 fixes not reflected in reviewer's context.
- **Impact**: Actual significant count: 0. Session converged. No remediation work items created.

### D-023: No new work items from Cycle 1 review
- **Decision**: All S1–S4 confirmed stale. Remaining minor findings and deferred gap items below convergence threshold. Session converged.

---

## Open Questions

**OQ-025**: In-memory session registry vs. filesystem-state (Principle 11, Constraint C4). User decision required. Eight consecutive cycles deferred. Options: (A) default `OUTPOST_LOG_FILE` path; (B) formally accept in-memory design and amend C4.

**OQ-UND**: Undocumented architecture additions (`max_depth`, `output_format`, `team_name`, `exec_instructions`, `OUTPOST_LOG_FILE`, `OUTPOST_ROLES_FILE`). Technical documentation pass, no design decision needed. User deferred.

**OQ-IR1**: `spawn_session` FileNotFoundError response missing `output`, `session_id`, `duration_ms`, `token_usage`. Small fix — add four fields to one return statement.

**OQ-MR1**: `OUTPOST_TIMEOUT` "not implemented" row in architecture Section 8 should be removed (D-11 settled per-call timeout). One-line deletion.

**OQ-CF5-W**: CF5 test RuntimeWarning from unawaited coroutine mock strategy. Technical fix available.

**OQ-GAP-EC1**: `_capture_git_diff` output unbounded. Defer until large workspaces become a concern.

**OQ-GAP-II1**: No full MCP handler round-trip integration test.

---

## Cross-References

**CR1**: Code-quality S1–S4 (stale) vs. spec-adherence/gap-analysis (accurate). When a new brrr session follows prior cycles with many changes, passing a prior-cycle summary to the code reviewer would reduce stale findings.

**CR2**: OQ-025 severity divergence — code-quality: significant (stale); spec-adherence: minor accepted deviation (D3); gap-analysis: minor deferred (MR2). All agree the tension exists; root question requires user decision.

**CR3**: FileNotFoundError coverage gap — code-quality M4 found missing test in remote-worker; gap-analysis IR1 found missing schema fields in session-spawner. Different reviewers, different angles on the same unfinished feature.
