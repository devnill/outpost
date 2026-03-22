# Decision Log — Outpost Cycle 2

**Date**: 2026-03-21
**Cycle scope**: WI-028 through WI-033 (code fixes and documentation sweep from Cycle 7 capstone review)
**Prior decision logs**: None (this is the first cycle-level decision log in this directory; domain-level decisions are maintained in `specs/domains/*/decisions.md`)

---

## Overview

This document synthesizes the project's full decision history into a chronological record and identifies all open questions remaining at the end of the Cycle 2 review. Decisions are extracted from the interview transcript, guiding principles, journal entries, incremental reviews, and the three final reviews (code-quality, spec-adherence, gap-analysis). Open questions are extracted from unresolved findings, deferred gaps, and reviewer contradictions.

---

## Decision Log

### Phase: Planning (Project Initialization — 2026-03-11)

---

**D-001**
- **When**: Planning — Session 1 interview (2026-03-11)
- **Decision**: Extract outpost from ideate as a separate project
- **Rationale**: Ideate's core purpose is SDLC workflow (planning, execution, review). Session orchestration and remote dispatch are infrastructure concerns with their own design decisions, constraints, and evolution path. Separating them allows ideate to remain focused on SDLC.
- **Implications**: Outpost maintains its own steering documents, guiding principles, constraints, and review cycle. Features do not flow back into ideate.

---

**D-002**
- **When**: Planning — Session 1 interview (2026-03-11)
- **Decision**: Two dispatch modes — local subprocess spawning and remote HTTP dispatch — share the same job submission interface
- **Rationale**: Users choose whether sessions run locally or remotely based on resource requirements. Shared interface enables callers to switch dispatch modes without changing code.
- **Alternatives considered**: Local-only dispatch (dismissed — insufficient for distributed/GPU workloads); separate interfaces per mode (dismissed — creates coupling in callers)
- **Implications**: Both spawn_session and spawn_remote_session must accept the same parameter set (prompt, working_dir, role, max_turns, timeout, permission_mode, allowed_tools). Any new parameter added to one mode must be evaluated for the other.

---

**D-003**
- **When**: Planning — Session 1 interview (2026-03-11)
- **Decision**: Filesystem state — all session tracking uses files, not in-memory state (Guiding Principle 2, Guiding Principle 11, Constraint C4)
- **Rationale**: Simplicity and recoverability — a server restart does not lose session state. Matches the single-user, local-tooling deployment model.
- **Implications**: MCP server must be stateless between calls. All coordination passes through disk artifacts. This principle is subsequently violated by the in-memory session registry (see OQ-001).

---

**D-004**
- **When**: Planning — Session 1 interview (2026-03-11)
- **Decision**: Depth limiting — recursive session spawning is bounded server-side (Guiding Principle 9, Constraint C9)
- **Rationale**: Prevents runaway recursion. Client-side enforcement would be bypassable.
- **Implications**: OUTPOST_SPAWN_DEPTH env var propagates depth to child sessions. Depth check runs before any subprocess creation. Sessions at max depth receive a structured error.

---

**D-005**
- **When**: Planning — Session 1 interview (2026-03-11)
- **Decision**: Timeout enforcement — every session has a timeout; hung sessions are killed
- **Rationale**: Hung processes without timeout enforcement would exhaust system resources. C12 requires process termination on timeout.
- **Implications**: subprocess.run() with timeout parameter is used. Python stdlib internal behavior (kill on TimeoutExpired) satisfies this requirement without explicit kill code in session-spawner. Remote-worker uses Popen and calls proc.kill() explicitly.

---

**D-006**
- **When**: Planning — Session 1 interview (2026-03-11)
- **Decision**: Role-based sessions — sessions assigned roles that constrain tool access (Guiding Principle 8, Constraint C10)
- **Rationale**: Enables safe parallel execution with appropriate privilege levels.
- **Implications**: Four roles defined in default-roles.json (worker, reviewer, manager, proxy-human). Roles are static JSON loaded at startup. Role definitions cannot be modified at runtime.

---

**D-007**
- **When**: Planning — Session 1 interview (2026-03-11)
- **Decision**: Output truncation at 50 KB — large outputs truncated to prevent context overflow
- **Rationale**: Protects caller from context overflow. Defaults are conservative. GP-7 requires resource bounds.
- **Implications**: DEFAULT_MAX_OUTPUT_BYTES = 50_000. Cannot be disabled. Large outputs written to overflow file; path returned to caller. Truncation must be byte-aware, not character-count-based.

---

**D-008**
- **When**: Planning — Session 1 interview (2026-03-11)
- **Decision**: Remote workers require API key authentication; no anonymous access
- **Rationale**: Prevents unauthorized job submission to worker daemons.
- **Implications**: API key comparison uses hmac.compare_digest (constant-time) rather than equality to prevent timing attacks. This was corrected during WI-030 incremental review.

---

**D-009**
- **When**: Planning — Session 1 interview (2026-03-11)
- **Decision**: Multi-tenant isolation is out of scope; persistent job queues are out of scope; web UI is out of scope
- **Rationale**: Multi-tenant isolation requires user identity propagation throughout the job model, significantly increasing deployment complexity. Persistent job queues require a database or durable message broker. Observability via manager agent reports instead of UI.
- **Implications**: These boundaries hold across all cycles. Separate worker instances per user for isolation. External orchestration for queue persistence.

---

**D-010**
- **When**: Planning — Work item 010 / ideate extraction (pre-outpost-project)
- **Decision**: spawn_session implemented as synchronous (blocks until subprocess exits)
- **Rationale**: Rationale not recorded. Architecture defined async spawn+poll model with poll_session, but implementation went synchronous without explanation.
- **Alternatives considered**: Async spawn+poll model as specified in architecture (not implemented)
- **Implications**: True parallel local dispatch (spawn N, poll each) is impossible. Callers block on each spawn_session call. This deviation was identified in Cycle 2 review and resolved in Cycle 3 — see D-021.

---

**D-011**
- **When**: Planning — Work item 022 (ideate, pre-outpost)
- **Decision**: In-memory session registry with opt-in JSONL disk logging (no default path)
- **Rationale**: Rationale not recorded. Contradicts D-003, GP-2, GP-11, and Constraint C4.
- **Implications**: Session history lost on server restart unless OUTPOST_LOG_FILE configured. Registry grows without bound. P-2 violation disclosed in session-lifecycle policies. Remains open as OQ-001.

---

### Phase: Planning (2026-03-15 — Refinement 1: Cleanup)

---

**D-012**
- **When**: Planning — Refinement interview 2026-03-15
- **Decision**: Retire work item 010 (stale); create work item 011 (session spawner verification)
- **Rationale**: WI-010 had a stale dependency on item "001" (completed in ideate before extraction). The session spawner already existed and was tested; what was needed was verification against original acceptance criteria.
- **Implications**: WI-011 scope: verify existing implementation, fix gaps. Not a re-implementation.

---

### Phase: Execution (2026-03-15 — Work item 011)

---

**D-013**
- **When**: Execution — WI-011 rework (2026-03-15)
- **Decision**: Timeout path uses byte-boundary truncation matching success path
- **Rationale**: Incremental review M1 identified that character-count slicing in the timeout path was inconsistent with byte-based truncation in the success path. Byte semantics required for correct Unicode handling.
- **Implications**: encode/slice/decode pattern used consistently in both paths.

---

**D-014**
- **When**: Execution — WI-011 rework (2026-03-15)
- **Decision**: Timeout path writes overflow file for large partial output
- **Rationale**: Without this, callers could not recover full partial output from timed-out sessions exceeding the inline truncation limit. Success path already had overflow-file logic; timeout path was missing it.
- **Implications**: Overflow file written on timeout path; output_truncated and full_output_path fields included in timeout response.

---

**D-015**
- **When**: Execution — WI-011 rework (2026-03-15)
- **Decision**: OUTPOST_TIMEOUT env var absence is an intentional deviation; timeout is per-call only
- **Rationale**: Per-call timeout gives callers fine-grained control without a global override. Architecture spec listed OUTPOST_TIMEOUT but implementation chose per-call parameters.
- **Implications**: Architecture row for OUTPOST_TIMEOUT annotated "(not implemented)". Setting this env var has no effect.

---

### Phase: Planning (2026-03-16 — Refinement 2: Cycle 2 findings)

---

**D-016**
- **When**: Planning — Refinement interview 2026-03-16 (pre-interview user decisions)
- **Decision**: Accept synchronous spawn_session as the final design; remove poll_session from architecture and README
- **Rationale**: Synchronous is acceptable for the use case. Architecture to be updated to document this as the final design.
- **Alternatives considered**: Implement async poll_session (rejected by user)
- **Implications**: Architecture updated by WI-016. Callers cannot do true parallel local dispatch. This decision closes OQ-004 from Cycle 2 summary.

---

**D-017**
- **When**: Planning — Refinement interview 2026-03-16 (pre-interview user decisions)
- **Decision**: Timed-out subprocess kill behavior verified via CPython source; no fix needed
- **Rationale**: subprocess.run() calls process.kill() internally before re-raising TimeoutExpired (CPython subprocess.py). C12 satisfied without explicit kill code in session-spawner.
- **Implications**: Closes reviewer contradiction OQ-002/Q-5 from Cycle 2 summary.

---

**D-018**
- **When**: Planning — Refinement interview 2026-03-16 (pre-interview user decisions)
- **Decision**: Role resolution for remote sessions uses Option A — session-spawner resolves role at dispatch time and sends resolved allowed_tools and permission_mode in HTTP payload
- **Rationale**: Simpler deployment; no need to synchronize role definitions across worker nodes.
- **Alternatives considered**: Option B — remote-worker loads role definitions locally and applies them (rejected — requires role file deployment on each worker)
- **Implications**: WI-015 implements this. Role definitions on session-spawner side are authoritative.

---

**D-019**
- **When**: Planning — Refinement interview 2026-03-16
- **Decision**: Implement running job cancellation via SIGTERM/SIGKILL on Popen handle
- **Rationale**: Users running long remote jobs need an abort mechanism. Graceful termination (SIGTERM) preferred over forceful; SIGKILL as fallback.
- **Implications**: WI-017 implements this. JobRecord.process field added. cancel_job handles running jobs in addition to queued jobs.

---

### Phase: Execution (2026-03-16 — Cycle 1 brrr)

---

**D-020**
- **When**: Execution — WI-012 (2026-03-16)
- **Decision**: Fix plugin.json path and README installation commands (stale paths from ideate extraction)
- **Rationale**: Paths were stale from project restructuring; mechanical fixes required for correct MCP registration.
- **Implications**: Installation now functional. pytest --cov flag corrected to target mcp/session-spawner/.

---

**D-021**
- **When**: Execution — WI-013 (2026-03-16)
- **Decision**: poll_remote_job fan-out returns found results before checking auth errors
- **Rationale**: Auth-first priority violated GP-3 (Graceful Degradation). A single misconfigured worker with stale API key permanently blocked all poll calls that omit worker_name.
- **Implications**: Found result from any worker returned immediately. Auth errors accumulated and returned only if no found result.

---

**D-022**
- **When**: Execution — WI-014 (2026-03-16)
- **Decision**: poll_remote_job propagates timestamp fields (created_at, started_at, completed_at) from worker response to caller
- **Rationale**: Fields were present in worker response but dropped by _poll_one(). Callers had incomplete job lifecycle visibility.
- **Implications**: _poll_one() field copy list extended.

---

**D-023**
- **When**: Execution — WI-015 (2026-03-16)
- **Decision**: Resolve role in _handle_spawn_remote_session before building HTTP payload
- **Rationale**: Implements D-018 (Option A). Role constraints (allowed_tools, permission_mode, max_turns) propagated to remote sessions. system_prompt not yet propagated — see OQ-010 in session-lifecycle questions.
- **Implications**: Remote sessions now receive tool constraints. system_prompt propagation gap identified; addressed in later cycle.

---

**D-024**
- **When**: Execution — WI-016 (2026-03-16)
- **Decision**: Update architecture document to match implementation — remove poll_session, correct env var names, update spawn_session output schema, fix worker_name parameters, update DELETE endpoint description
- **Rationale**: Architecture was stale after multiple cycles of implementation divergence. WI-016 brings architecture into alignment with the implementation as deployed.
- **Implications**: Architecture.md is now the authoritative reference for deployed behavior.

---

**D-025**
- **When**: Execution — WI-017 (2026-03-16)
- **Decision**: JobRecord.process field stores Popen handle; cancel_job sends SIGTERM then SIGKILL after 2s
- **Rationale**: Process handle storage required for signal delivery. SIGTERM allows graceful shutdown; SIGKILL as fallback if process does not exit within 2 seconds.
- **Implications**: Running jobs can now be cancelled. _process_job preserves cancelled status after kill. Cancel-while-starting race not yet addressed — addressed in Cycle 2 WI-033.

---

### Phase: Planning (2026-03-20 — Refinement 3: Cycle 4 findings)

---

**D-026**
- **When**: Planning — Refinement interview 2026-03-20
- **Decision**: Role system_prompt propagation to remote sessions — Option A (session-spawner prepends to prompt before dispatch)
- **Rationale**: Consistent with how spawn_session handles system_prompt locally. Remote workers do not need to load role definitions.
- **Alternatives considered**: Option B — pass system_prompt as separate field for remote-worker to prepend (rejected in favor of consistency with local path)
- **Implications**: WI-018 implements this. reviewer, manager, and proxy-human role behavioral contracts now apply to remote sessions.

---

**D-027**
- **When**: Planning — Refinement interview 2026-03-20
- **Decision**: Add cancel_remote_job as MCP tool in session-spawner
- **Rationale**: No MCP-level cancellation tool existed. Callers had to use HTTP directly. Fan-out error-collection pattern (continue instead of early-return) aligns with GP-3.
- **Implications**: Fifth MCP tool added. Issues DELETE /jobs/{id} to named worker or fans out.

---

**D-028**
- **When**: Planning — Refinement interview 2026-03-20
- **Decision**: LRU eviction for job store with IDEATE_WORKER_MAX_JOBS env var (default 1000)
- **Rationale**: Completed and failed jobs accumulated indefinitely, each holding full output strings. Long-running daemons would exhaust heap memory.
- **Implications**: _evict_terminal_jobs_locked() called after each job reaches terminal state. max_jobs added to health response and forwarded by list_remote_workers.

---

**D-029**
- **When**: Planning — Refinement interview 2026-03-20
- **Decision**: Add integration tests between session-spawner and remote-worker
- **Rationale**: No end-to-end tests existed across the MCP tool boundary. Individual unit tests insufficient for verifying fan-out and error-collection logic.
- **Implications**: mcp/test_integration.py created. Covers job CRUD and role propagation through live uvicorn instance.

---

### Phase: Planning (2026-03-21 — Refinement 4: Cycle 7 capstone — current cycle)

---

**D-030**
- **When**: Planning — Refinement interview 2026-03-21
- **Decision**: Address all Cycle 7 Category 1 (code fixes) and Category 2 (documentation) items; defer OQ-025 (in-memory session registry design decision)
- **Rationale**: Cycle 7 found 0 critical, 0 significant findings. Remaining minor items have accumulated across cycles 3–7. OQ-025 requires a binding user decision; not a code investigation.
- **Implications**: WI-028 through WI-032 scoped accordingly. OQ-025 carried forward explicitly.

---

**D-031**
- **When**: Planning — Refinement interview 2026-03-21
- **Decision**: Defer architecture.md documentation of undocumented spawn_session additions (max_depth, output_format, team_name, exec_instructions, OUTPOST_LOG_FILE, OUTPOST_ROLES_FILE, OUTPOST_EXEC_INSTRUCTIONS, OUTPOST_TEAM_NAME)
- **Rationale**: User explicitly deferred: "Defer — come back to this in the next refinement cycle." Session-spawner README is authoritative and complete.
- **Implications**: Architecture Section 3 and Section 8 remain incomplete for these parameters. Tracked as OQ-026 in gap analysis.

---

### Phase: Execution (2026-03-21 — Cycle 2 brrr)

---

**D-032**
- **When**: Execution — WI-028 (2026-03-21)
- **Decision**: Wrap proc.terminate() and proc.kill() in try/except (ProcessLookupError, OSError) to handle race with process exit
- **Rationale**: If a running process exits between the status check and the signal delivery, terminate()/kill() raises ProcessLookupError. Without the guard, cancel_job raises HTTP 500.
- **Implications**: Cancel-on-already-exited job returns normally. Comment added clarifying ProcessLookupError is a subclass of OSError (incremental review M1).

---

**D-033**
- **When**: Execution — WI-029 (2026-03-21)
- **Decision**: Catch FileNotFoundError in both servers and return structured error with actionable message naming claude and PATH
- **Rationale**: Raw FileNotFoundError produced Python traceback (session-spawner) or opaque "failed" status (remote-worker), neither indicating the cause. GP-3 requires structured error for predictable failure modes.
- **Implications**: session-spawner returns structured error with exit_code=1. remote-worker marks job failed with exit_code=1. Note: session-spawner FileNotFoundError response is still missing output, session_id, and duration_ms fields — see OQ-002.

---

**D-034**
- **When**: Execution — WI-030 (2026-03-21)
- **Decision**: Rename sys.modules keys in conftest files from "server" to "session_spawner_server" and "remote_worker_server"
- **Rationale**: Both conftests registered under the same key "server". Second registration overwrote the first during combined pytest runs. Key collision was a latent bug.
- **Implications**: All test files updated to import using new module names. Integration test isolation preserved.

---

**D-035**
- **When**: Execution — WI-031 (2026-03-21)
- **Decision**: Add --cwd flag to _run_claude_job in remote-worker; add max_jobs to list_remote_workers output
- **Rationale**: Session-spawner passes both cwd= subprocess kwarg and --cwd CLI flag; remote-worker passed only cwd= subprocess kwarg. Divergence is a latent correctness risk if Claude CLI behavior changes. max_jobs already in health response but not forwarded by _fetch_worker_health.
- **Implications**: --allowedTools also moved before prompt positional argument for correctness (incremental review M1). Architecture spec compliance restored for both changes.

---

**D-036**
- **When**: Execution — WI-032 (2026-03-21)
- **Decision**: Documentation sweep — add cancel_remote_job to root README, add config cross-references, correct CLAUDE.md requirements path, add IDEATE_WORKER_MAX_JOBS row to architecture.md Section 8
- **Rationale**: cancel_remote_job was added in cycle 5 but absent from root README tool list. CLAUDE.md referenced stale requirements.txt path. IDEATE_WORKER_MAX_JOBS was missing from architecture Section 8 despite being in remote-worker README.
- **Implications**: Documentation is now consistent across root README, CLAUDE.md, and architecture.md for these specific items.

---

**D-037**
- **When**: Execution — WI-033 (unplanned, added during cycle)
- **Decision**: Fix cancel-while-starting race — check record.status after Popen returns but before assigning record.process; kill and return None if already cancelled
- **Rationale**: A cancellation arriving between Popen() call and record.process assignment was a window where the cancel_job handler could not reach the process handle. The process would run to completion despite the cancellation request.
- **Implications**: _process_job wrapper now handles None return from _run_claude_job by setting completed_at when not already set (incremental review S1).

---

### Phase: Review (2026-03-21 — Cycle 2 final reviews)

---

**D-038**
- **When**: Review — Code quality review (2026-03-21)
- **Decision**: Accept six minor findings as carry-forward items (dead decode branch, unused stderr_bytes variable, undocumented lockless read, redundant @pytest.mark.asyncio decorators, %d format for exit_code, integration test module identity issue)
- **Rationale**: All six are minor. No critical or significant defects. Cycle 2 scope was defined as code fixes and documentation only.
- **Implications**: Dead decode branch (M1), unused stderr_bytes (M2), lockless read (M3), decorator inconsistency (M4), log format type risk (M5), and integration test module shadow (M6) are open for next cycle.

---

**D-039**
- **When**: Review — Spec-adherence review (2026-03-21)
- **Decision**: OUTPOST_TIMEOUT architecture row remains annotated "(not implemented)" rather than being removed
- **Rationale**: Annotation makes the deviation visible without removing historical traceability. Changing the architecture would also not affect any code path.
- **Implications**: Row persists in architecture.md Section 8. Setting OUTPOST_TIMEOUT has no effect; per-call timeout remains the only mechanism.

---

**D-040**
- **When**: Review — Spec-adherence review (2026-03-21)
- **Decision**: Three undocumented additions (team_name/exec_instructions, output_format, in-memory session registry) carry forward as low-risk deviations
- **Rationale**: All three are additive. No safety or resource implications. Policy conflict disclosed in session-lifecycle/policies.md.
- **Implications**: Architecture Section 3 does not document these parameters. session-spawner README is authoritative. Architecture documentation deferred to next cycle.

---

**D-041**
- **When**: Review — Gap analysis (2026-03-21)
- **Decision**: Four gap findings deferred — git diff size limit (EC1), session registry unbounded growth (EC2), list_remote_workers health integration test (II1), cancel_remote_job response missing worker_name in README (II2)
- **Rationale**: EC1 — large diffs uncommon in target use case. EC2 — bounded in practice by session lifetime. II1 — component unit tests provide sufficient coverage. II2 — implementation richer than documented, not poorer.
- **Implications**: All four carry forward to next cycle. EC2 overlaps with the still-open OQ-001 (session registry design).

---

## Open Questions

### OQ-001: In-memory session registry vs. filesystem-state design decision

- **Question**: The guiding principles (GP-2, GP-11) and Constraint C4 require all session tracking to use the filesystem. The current implementation uses an in-memory Python list (_session_registry) with opt-in JSONL disk logging only when OUTPOST_LOG_FILE is configured. The manager agent's session-registry.json input contract cannot be satisfied by the current implementation. Requires a binding user decision: (A) add a default OUTPOST_LOG_FILE path to make state durable by default, or (B) formally update the interview record and constraints to accept the in-memory design.
- **Source**: interview.md Session 1 (key design decision #1), gap-analysis Cycle 2 (EC2), session-lifecycle Q-4, gap-analysis Cycle 7 (OQ-025). User explicitly deferred in 2026-03-21 refinement interview.
- **Impact**: Session history is lost on server restart when OUTPOST_LOG_FILE is not set. Registry grows without bound in memory for long-lived server processes. The manager agent cannot read session state from a registry file. GP-2, GP-11, C4 remain formally violated.
- **Who answers**: User decision (not resolvable by technical investigation alone)
- **Consequence of inaction**: The formal design principle record (interview.md, constraints.md) states filesystem-only state, while the shipped code uses in-memory state. Any developer relying on the principle to design integrations (e.g., tools that read session-registry.json) will build against a contract that the implementation cannot satisfy. Memory use grows linearly with spawn count until process restart.

---

### OQ-002: FileNotFoundError response from session-spawner is missing standard schema fields

- **Question**: The FileNotFoundError path introduced by WI-029 returns only two fields (error, exit_code). All other error return paths (prompt-too-large, invalid working-dir, safe-root violation, depth-exceeded) return six fields (output, exit_code, session_id, duration_ms, error, and path-specific additions). The inconsistency was identified in gap-analysis Cycle 1 (G2) and not addressed by WI-029.
- **Source**: gap-analysis Cycle 2 (IR1), spec-adherence Cycle 2 (Principle 3 / Graceful Degradation)
- **Impact**: Any orchestrator that destructures the spawn_session response expecting all six standard fields will receive None or KeyError on the FileNotFoundError path.
- **Who answers**: Technical fix (one-line addition per field)
- **Consequence of inaction**: Callers hitting this error (new users with missing claude binary) receive a partially structured response. Orchestrators that pattern-match on response fields will fail to parse the error correctly and may produce a secondary error.

---

### OQ-003: Architecture Section 2 data flow diagram shows subprocess.run for remote worker

- **Question**: Architecture.md Section 2 shows subprocess.run(["claude", "--print", prompt]) as the remote worker execution mechanism. WI-031 and WI-033 use subprocess.Popen + communicate() for running-job cancellation. WI-032 updated Section 8 only; the data flow diagram was not touched.
- **Source**: gap-analysis Cycle 2 (MI1)
- **Impact**: A developer reading the architecture to understand how cancellation works will find subprocess.run — a blocking call with no process handle — which directly contradicts the cancellation mechanism implemented in WI-028/WI-033.
- **Who answers**: Documentation fix (architecture.md Section 2)
- **Consequence of inaction**: Architecture document actively misleads any developer who reads it to understand the cancellation design. The module-level docstring in server.py is accurate, but the architecture is the expected reference for cross-component design.

---

### OQ-004: Architecture Section 3 missing six spawn_session parameters and four environment variables

- **Question**: Architecture.md Section 3 lists eight spawn_session input parameters. The implementation and session-spawner README document fourteen: max_depth, output_format, team_name, exec_instructions, role (inline dict variant), model parameter semantics. Section 8 is missing OUTPOST_LOG_FILE, OUTPOST_ROLES_FILE, OUTPOST_EXEC_INSTRUCTIONS, and OUTPOST_TEAM_NAME.
- **Source**: gap-analysis Cycle 2 (MI2), spec-adherence Cycle 2 (U1, U2). User explicitly deferred in 2026-03-21 refinement interview.
- **Impact**: The architecture is an incomplete reference. Callers relying only on architecture.md are unaware of observability (OUTPOST_LOG_FILE), role customization (OUTPOST_ROLES_FILE), and execution instruction propagation (exec_instructions, OUTPOST_EXEC_INSTRUCTIONS).
- **Who answers**: Documentation fix (architecture.md Sections 3 and 8)
- **Consequence of inaction**: Architecture continues to diverge from the implementation. Each future review cycle will carry this finding forward. Integrators using architecture.md as their primary reference will have an incomplete tool specification.

---

### OQ-005: Dead decode branch in _run_claude_job timeout path

- **Question**: In mcp/remote-worker/server.py line 399, subprocess.Popen is created with text=True (line 376), so proc.communicate() always returns (str, str). The isinstance(stdout_bytes, str) guard is always True; the .decode("utf-8", errors="ignore") branch can never execute.
- **Source**: code-quality Cycle 2 (M1)
- **Impact**: Dead code — no functional impact but misleads future maintainers about the type contract of the communicate() return value.
- **Who answers**: Technical fix (remove the conditional, use str value directly)
- **Consequence of inaction**: A future maintainer reading the code may believe the communicate() call can return bytes, leading to incorrect assumptions about the Popen configuration. The dead branch also makes test coverage metrics misleadingly low.

---

### OQ-006: Unused variable stderr_bytes in timeout path

- **Question**: stderr_bytes is captured from the second proc.communicate() call after a timeout but is never used. The timeout error message includes no stderr content from the killed process.
- **Source**: code-quality Cycle 2 (M2)
- **Impact**: Debugging information available from the killed process is discarded. Users investigating timed-out remote jobs have no stderr content to diagnose the failure.
- **Who answers**: Technical or design decision (discard with _ or include in error message)
- **Consequence of inaction**: Operators investigating timed-out jobs in production have less diagnostic information than the implementation could provide. The unused variable also creates a minor lint warning.

---

### OQ-007: Lockless read of record.status in sync thread is undocumented

- **Question**: record.status is read without holding job_store_lock at mcp/remote-worker/server.py line 386. This is intentional (the async lock cannot be acquired in an asyncio.to_thread context) but is not documented. A concurrent write to record.status from cancel_job is possible at this point.
- **Source**: code-quality Cycle 2 (M3)
- **Impact**: Low — worst case is the cancelled status is missed and the job runs briefly before the communicate-path detects cancellation on completion. However, the undocumented pattern invites future maintainers to introduce actual race conditions by analogy.
- **Who answers**: Documentation fix (add comment explaining the intentional lockless read and safety bound)
- **Consequence of inaction**: Future modifications to _run_claude_job may introduce similar lockless patterns in contexts where races are not safe. The absence of documentation makes it impossible to distinguish intentional from accidental lockless reads during code review.

---

### OQ-008: Redundant @pytest.mark.asyncio decorators in session-spawner tests

- **Question**: pytest.ini sets asyncio_mode = auto, making @pytest.mark.asyncio a no-op on all async test functions. The remote-worker tests correctly omit it; the session-spawner tests include it on every async test, creating inconsistency.
- **Source**: code-quality Cycle 2 (M4)
- **Impact**: Style inconsistency only. No functional impact.
- **Who answers**: Technical fix (remove decorators from mcp/session-spawner/test_server.py)
- **Consequence of inaction**: Future developers writing session-spawner tests will copy the decorator pattern, perpetuating the inconsistency. New developers may believe the decorator is required in this project.

---

### OQ-009: %d format specifier for exit_code in logger.info call

- **Question**: mcp/remote-worker/server.py line 448 uses %d for exit_code in a log format string. exit_code is typed as int | None on JobRecord. The current code flow prevents None from reaching this line, but the type annotation invites future confusion and the format would raise TypeError at log emission time if the None path were ever reached.
- **Source**: code-quality Cycle 2 (M5)
- **Impact**: Low — no current failure path. Future code changes that allow None to reach this log call would raise TypeError at log emission time, masking the original event.
- **Who answers**: Technical fix (change to %s or add assertion)
- **Consequence of inaction**: If a future code change allows the None path to reach this log call, the TypeError would be raised at log emission time (after the job has been processed), producing a confusing secondary error rather than the original exception.

---

### OQ-010: Integration test module identity — two separate module objects for same source file

- **Question**: mcp/test_integration.py re-imports both servers using keys "remote_worker" and "session_spawner", while conftest.py files register them as "remote_worker_server" and "session_spawner_server". Two separate module objects exist in sys.modules for the same source file during a combined test run. Mutations to one module object (e.g., spawner_mod._remote_workers) do not affect the other.
- **Source**: code-quality Cycle 2 (M6)
- **Impact**: Integration tests that mutate module-level state via spawner_mod._remote_workers may not affect the module object used by conftest-registered fixtures. This could cause integration tests to pass while testing against different state than the fixtures establish.
- **Who answers**: Technical fix (import using same module names registered by conftest files)
- **Consequence of inaction**: Integration tests silently test against a different module instance than the unit tests. A bug in module-level state handling could pass integration tests while failing in production.

---

### OQ-011: Git diff output has no size limit

- **Question**: _capture_git_diff in mcp/remote-worker/server.py stores the full stdout of git diff HEAD in JobRecord.git_diff with no truncation or byte cap. Output truncation at 50 KB is applied to job output but not to git diff output.
- **Source**: gap-analysis Cycle 2 (EC1), remote-dispatch Q-7
- **Impact**: A job run in a workspace with large generated or binary-adjacent files can produce hundreds of kilobytes of git diff output, stored in memory and returned verbatim in API responses. Inconsistent with Constraint 7 (Output Size Limits) and GP-7 (Resource Bounds).
- **Who answers**: Technical fix (apply same truncation pattern as job output)
- **Consequence of inaction**: Memory usage for job records is unbounded in workspaces with large diff output. GP-7 is formally violated for this field. Callers receiving large git_diff values may encounter context overflow.

---

### OQ-012: cancel_remote_job response worker_name field undocumented in session-spawner README

- **Question**: mcp/session-spawner/server.py line 990 returns {"job_id": job_id, "status": "cancelled", "worker_name": w["name"]} but the session-spawner README documents the response as {"job_id": "...", "status": "cancelled"} with no worker_name field (lines 170–175). WI-032 did not address this discrepancy.
- **Source**: gap-analysis Cycle 2 (II2)
- **Impact**: Callers reading the README will not know worker_name is available in the cancellation response.
- **Who answers**: Documentation fix (one-line addition to README response schema)
- **Consequence of inaction**: Implementation is richer than documented. Callers who would benefit from worker_name (e.g., for logging or follow-up queries) will not discover the field from the README.

---

### OQ-013: No integration test for list_remote_workers against a live uvicorn instance

- **Question**: mcp/test_integration.py contains five tests covering job CRUD and role propagation. None exercise _handle_list_remote_workers or the GET /health path end-to-end. The max_jobs field added by WI-031 is tested only via unit test against mocked health data; the full chain from MCP tool call through live HTTP to uvicorn is untested.
- **Source**: gap-analysis Cycle 2 (II1)
- **Impact**: Low — _fetch_worker_health is unit-tested and the health endpoint is unit-tested. Regression in the integration between them would not be caught by existing tests.
- **Who answers**: Technical investigation (add integration test)
- **Consequence of inaction**: A regression in max_jobs forwarding (e.g., key name mismatch between health response and _fetch_worker_health parsing) would pass all existing tests until observed in production.

---

### OQ-014: OUTPOST_TIMEOUT env var row — remove vs. annotate

- **Question**: Architecture.md Section 8 lists OUTPOST_TIMEOUT with annotation "(not implemented)". The row is accurate as annotated but represents an abandoned spec entry. No decision has been made about whether to remove the row or keep it as historical context.
- **Source**: spec-adherence Cycle 2 (D1)
- **Impact**: Minor — the annotation makes the deviation visible. Setting this env var has no effect.
- **Who answers**: User decision (preference for annotation vs. removal)
- **Consequence of inaction**: The annotated row remains indefinitely, potentially confusing operators who scan the env var table and miss the annotation.

---

### OQ-015: Worker selection strategy when multiple workers configured

- **Question**: When spawn_remote_session is called without specifying worker_url, the job goes to the first configured worker (index 0). No load-balancing or affinity logic exists.
- **Source**: remote-dispatch Q-2
- **Impact**: Uneven load distribution across a worker pool. All unrouted jobs pile onto one worker while others are idle.
- **Who answers**: Design review (choose load-balancing strategy if needed)
- **Consequence of inaction**: Users configuring multiple workers for parallel throughput will not get the expected load distribution. All jobs route to index-0 worker until that worker is at capacity.

---

### OQ-016: Caller recovery pattern for worker restart (in-memory queue loss)

- **Question**: The job queue is in-memory (D-003, remote-dispatch D-2). When a worker restarts, all queued and running jobs are lost. There is no documented caller-side recovery pattern for detecting this and re-submitting.
- **Source**: remote-dispatch Q-1
- **Impact**: Callers may silently lose work when a worker restarts during a long execution run (e.g., brrr session).
- **Who answers**: Design review (document expected recovery pattern)
- **Consequence of inaction**: Users running long brrr sessions across a worker restart have no documented procedure for detecting and recovering lost jobs.

---

### OQ-017: Local session cancellation not supported

- **Question**: Remote jobs support cancellation via cancel_remote_job (DELETE /jobs/{id}). Local sessions spawned via spawn_session have no cancellation mechanism. The only termination mechanism is timeout.
- **Source**: session-lifecycle Q-8
- **Impact**: Long-running local sessions cannot be aborted mid-execution. Users must wait for timeout.
- **Who answers**: Design review (decide whether local cancellation is in scope)
- **Consequence of inaction**: Asymmetry between local and remote dispatch remains. Users who need to abort a local session must restart the MCP server or kill the subprocess manually.

---

### OQ-018: Output truncation — head vs. tail preference undocumented

- **Question**: When truncating session output to max_output_bytes, it is not documented whether the beginning or end of the output is preserved. GP-10 states "preserves the most relevant content" but does not specify which end.
- **Source**: session-lifecycle Q-1
- **Impact**: Callers relying on truncated output for debugging may receive different information than expected depending on undocumented implementation behavior.
- **Who answers**: Documentation fix (document truncation semantics in README and architecture)
- **Consequence of inaction**: Callers cannot predict which portion of large session output is returned. A caller debugging a failed session may receive only the prologue and miss the actual error message at the end.

---

## Cross-References

### CR1: FileNotFoundError Response Schema Consistency

- **Code review**: No finding on this topic in Cycle 2 code-quality review
- **Spec review**: Principle 3 (Graceful Degradation) — FileNotFoundError handling noted as implemented; return of structured error confirmed
- **Gap analysis**: IR1 — FileNotFoundError response missing output, session_id, duration_ms fields present in all other error paths
- **Connection**: The spec-adherence review confirms GP-3 is satisfied (no raw traceback), while the gap analysis identifies that the response does not fully conform to the schema used by all other error paths. The two findings are not contradictory — GP-3 is satisfied, but the schema inconsistency (OQ-002) remains. Any orchestrator relying on schema uniformity will fail on this path.

---

### CR2: Module Identity in Test Infrastructure

- **Code review**: M6 — test_integration.py re-imports servers under different sys.modules keys than conftests; two separate module objects in combined test runs
- **Spec review**: No finding on this topic
- **Gap analysis**: No finding on this topic
- **Connection**: The code-quality review identified a correctness risk in the integration test layer. WI-030 (conftest key collision fix) was completed this cycle but did not address the integration test import pattern, which uses yet different keys. The two fixes are related: WI-030 fixed the conftest-to-conftest collision, but OQ-010 (the conftest-to-integration-test collision) remains.

---

### CR3: Architecture Document Staleness

- **Code review**: No finding on architecture staleness
- **Spec review**: D1 (OUTPOST_TIMEOUT row), U1–U3 (undocumented additions), N1 (JobRecord/JobRequest pattern)
- **Gap analysis**: MI1 (Section 2 still shows subprocess.run), MI2 (Section 3 missing six parameters and four env vars)
- **Connection**: The spec-adherence and gap-analysis reviews identify distinct but related architecture gaps: the spec-adherence review flags annotation and undocumented additions (carry-forward items), while the gap analysis identifies two new staleness issues introduced by this cycle's implementation changes (MI1 from WI-033, MI2 from deferred user decision). The combined picture shows architecture.md has at least four open divergences from the implementation: OUTPOST_TIMEOUT annotation (minor), undocumented parameters (deferred by user), Section 2 subprocess diagram (OQ-003), and Section 3/8 parameter table incompleteness (OQ-004).

---

### CR4: Cancel-While-Starting Race and proc.terminate Race

- **Code review**: M3 — lockless read of record.status in sync thread undocumented; inherent constraint of asyncio.to_thread context
- **Spec review**: WI-033 acceptance criteria verified as fully met
- **Gap analysis**: No finding on cancellation race conditions
- **Connection**: WI-028 addressed the proc.terminate() race (process exits between status check and signal); WI-033 addressed the cancel-while-starting race (cancellation arrives between Popen() and process handle assignment). The code-quality review identifies a third related pattern — the lockless read of record.status in the sync thread (OQ-007) — which is intentional but undocumented. All three relate to the same concurrency boundary between the async cancel_job handler and the sync _run_claude_job thread. The lockless read is the only one not yet addressed by a guard or comment.

---

*This decision log covers Planning through Cycle 2 review (2026-03-21). Decisions from prior cycles are reflected in domain-level decisions files at specs/domains/*/decisions.md.*