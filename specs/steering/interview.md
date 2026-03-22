# Planning Interview — Outpost

---
## Refinement Interview — 2026-03-22

**Context**: Post-convergence direction change. User wants Outpost's primary use case to be remote execution with Docker-based sandboxing for safety (unattended agents running `--dangerously-skip-permissions` inside containers) and multi-tool/multi-model support. Research commissioned on container sandboxing and alternative AI coding tools. This interview covers the Docker sandboxing scope. Multi-tool abstraction deferred to a subsequent cycle pending further investigation.

**Q: Should the daemon itself be containerized, or just the jobs it runs?**
A: Daemon on host is acceptable for the initial implementation. Containerizing the daemon is a deployment concern — iterate on it later.

**Q: When a job runs in a container with a bind-mounted workspace, should writes persist back to a host directory, or is the workspace disposable?**
A: No strong opinion. Security and modularity are the only drivers. Don't want malicious or defective prompts to damage the machine running the agent.

**Q: Should this cycle add the multi-tool driver abstraction and opencode as the first alternative backend?**
A: No — defer. Investigate Claude Code alternatives before committing to a design. This cycle is Docker sandboxing only.

---
## Refinement Interview — 2026-03-21

**Context**: Cycle 7 capstone review found 0 critical, 0 significant findings. User requested all Category 1 (code fixes) and Category 2 (documentation) items from the review's proposed refinement plan. OQ-025 (in-memory session registry vs. filesystem-state design decision) deferred to next refinement cycle.

**Q: Are you here to address the cycle 7 findings, to make other changes, or both?**
A: Address cycle 7 findings — all of Category 1 (code fixes) and Category 2 (documentation). OQ-025 deferred.

**Q: Do the guiding principles still hold as-is?**
A: Yes, unchanged for now.

**Q: For FileNotFoundError handling — the session-spawner should return a structured MCP error response, and the remote-worker should mark the job failed with an actionable message. Does that match your intent?**
A: Yes, good proposal.

**Q: For the undocumented spawn_session additions in architecture (max_depth, output_format, team_name, exec_instructions, OUTPOST_LOG_FILE, OUTPOST_ROLES_FILE) — brief table-only update, full description, or defer?**
A: Defer — come back to this in the next refinement cycle.

## Session 1 — 2026-03-11

### Q: What is outpost?

**A:** Outpost is an MCP server for Claude Code that provides orchestration infrastructure for delegating work to separate Claude Code instances. It enables two dispatch modes: local session spawning (subprocess) and remote dispatch (HTTP API to worker daemons). The project was extracted from ideate as a separate concern.

### Q: Why was outpost extracted from ideate?

**A:** Ideate's core purpose is SDLC workflow (planning, execution, review). Session orchestration and remote dispatch are infrastructure concerns that have their own design decisions, constraints, and evolution path. Separating them allows ideate to remain focused on SDLC while outpost can specialize in MCP orchestration patterns.

### Q: What problem does outpost solve?

**A:** Claude Code does not support subagents spawning their own subagents. Outpost fills this gap by providing MCP tools that allow a parent Claude Code session to spawn child sessions for parallel work execution. It also enables remote dispatch to worker daemons running on other machines, which is useful for GPU-intensive work or distributed processing.

### Q: Who is the primary user of outpost?

**A:** Developers and teams using Claude Code for large projects that benefit from parallel execution. Users who need to dispatch work to multiple machines. Users running autonomous execution loops (brrr skill) that need worker management and job monitoring.

### Q: What are the core components?

**A:**
- **session-spawner**: MCP server for local session spawning via `claude --print`
- **remote-worker**: FastAPI HTTP service that accepts jobs and runs them locally
- **roles system**: JSON-based role definitions for constraining session capabilities
- **manager agent**: Claude Code agent that monitors worker status and produces reports

### Q: What are the key design decisions?

**A:**
1. **Filesystem state**: All session tracking uses files, not in-memory state
2. **Depth limiting**: Recursive spawning is bounded to prevent runaway recursion
3. **Timeout enforcement**: Every session has a timeout; hung sessions are killed
4. **Role-based permissions**: Sessions can be assigned roles that limit tool access
5. **Output truncation**: Large outputs are truncated to prevent context overflow
6. **Graceful degradation**: Worker failures don't crash the orchestrator

### Q: What are the security considerations?

**A:**
- Remote workers require API key authentication
- Safe root enforcement can restrict session file access to a directory tree
- Sessions inherit the parent's permissions by default but can be constrained via roles
- No anonymous access to remote workers

### Q: What is out of scope?

**A:**
- Multi-tenant isolation (run separate worker instances instead)
- Persistent job queues (use external orchestration)
- Work execution (outpost orchestrates; it does not do the work)
- Web UI or dashboard (observability via manager agent reports)

### Q: How should outpost evolve?

**A:**
Potential future directions:
- Session result caching for faster re-dispatch
- Priority queue support for job scheduling
- Worker pool auto-scaling based on queue depth
- WebSocket transport as an alternative to HTTP
- Integration with cloud provider APIs for worker provisioning

These are not currently planned; they represent potential directions based on user feedback.

---

## Completion

Interview completed. Guiding principles, constraints, and architecture derived from this session.

---

## Refinement Interview — 2026-03-15

**Context**: `/ideate:execute` failed plan validation. Work item 010 had a stale dependency on item "001" (completed in ideate before extraction). Artifact structure needed cleanup and session spawner verification.

**Q: Is this new work or cleanup?**
A: Cleanup. The last job failed. We should read the steering documents and fix the artifact structure.

**Q: For work item 010 — the session spawner already exists and is tested. Should it be removed (already done in ideate) or should we re-run it?**
A: We should verify that it was implemented correctly.

**Resolution**: Retired work item 010 (stale, implemented in ideate). Created work item 011: verify the session spawner implementation against its original acceptance criteria. Guiding principles, constraints, and architecture unchanged.

---

## Refinement Interview — 2026-03-16

**Context**: Post-review correction. Cycle 2 review produced 6 critical and 4 significant findings. Three open questions were resolved in the preceding conversation before this interview. This interview confirms scope and resolves the remaining open question.

**Pre-interview decisions (resolved before interview):**

- **Q: Should spawn_session remain synchronous or should poll_session be implemented?**
  A: Accept synchronous. Update architecture to document synchronous as the final design. Remove poll_session from architecture and README.

- **Q: Are timed-out subprocesses actually killed?**
  A: Verified via CPython source — subprocess.run() calls process.kill() internally before re-raising TimeoutExpired. No fix needed. C12 constraint is satisfied.

- **Q: Role resolution for remote sessions — which option?**
  A: Option A. Session-spawner resolves the role definition at dispatch time and sends the resolved allowed_tools and permission_mode in the HTTP payload to the remote worker.

**Q: Running job cancellation — should cycle 3 implement DELETE /jobs/{id} for running jobs by sending SIGTERM to the subprocess?**
A: Yes, support cancellation.

**Q: Are there any other areas the user wants to preserve as-is or explicitly exclude from this cycle?**
A: Scope is the 5 findings-driven items plus cancellation. No architecture redesign. No new features beyond what the cycle 2 review identified.

---
## Refinement Interview — 2026-03-20

**Context**: Cycle 4 comprehensive review (2026-03-20) identified 1 critical finding (role system_prompt not propagated to remote sessions), 6 significant findings (cancel_remote_job tool missing, job store unbounded, no integration tests, no startup validation, token_usage inconsistency, documentation divergence), and 11 minor findings. This refinement addresses all critical and significant findings plus all minor documentation fixes.

**Q: OQ-001 — Role system_prompt for remote sessions: Option A (session-spawner prepends system_prompt to prompt before dispatch) or Option B (pass system_prompt as separate field, remote-worker prepends)?**
A: Option A. Session-spawner resolves system_prompt from the role definition and prepends it to the prompt string before sending the HTTP payload to the remote worker. Consistent with how spawn_session handles it locally.

**Q: OQ-002 — Should cancel_remote_job be added as an MCP tool to session-spawner?**
A: Yes, add the cancel_remote_job tool.

**Q: OQ-007 — LRU eviction for job store in remote-worker?**
A: Yes, implement LRU eviction with configurable IDEATE_WORKER_MAX_JOBS env var (default 1000).

**Q: OQ-008 — Integration tests between session-spawner and remote-worker?**
A: Yes, worth it. Add integration tests.

**Q: Minor findings — address all documentation fixes (architecture.md, remote-worker README, session-spawner README), startup validation warnings, and token_usage null consistency?**
A: Yes, do all minor fixes.

---
## Refinement Interview — 2026-03-22

**Context**: Brrr session converged in cycle 4. Nine minor open items deferred from cycle 4 gap analysis: CF2, CF3, CF5, CF7 (test coverage gaps in remote-worker), NG2 (list_jobs missing fields), NG3 (auth not exercised in integration tests), NG4 (submit_job ordering), NC1, NC2 (session-spawner test gaps).

**Q: Are you addressing all 9 minor open items from the cycle 4 brrr session?**
A: Yes, all 9.

**Q: Do the guiding principles still apply, or do any need to change?**
A: All principles unchanged.

---
## Refinement Interview — 2026-03-22 (Cycle 9)

**Context**: Post-review correction. Cycle 8 capstone review produced 4 significant findings (S1 API key in process table, S2 no docker stop test, DG1 remote-worker README missing container docs, DG2 root README missing container sandboxing) plus one architect observation (AO1 blocking docker stop in async event loop) and two minor findings (M1 eviction call missing, M2 no ANTHROPIC_API_KEY pre-flight check). User elected to address all findings in this cycle.

**Q: Do the guiding principles still apply, or do any need to change?**
A: (Confirmed unchanged — all findings are bug fixes and documentation gaps within existing architecture.)

**Q: The review found 4 significant findings (S1, S2, DG1, DG2), one architect observation (AO1 — blocking docker stop on async loop), and two minor findings (M1 — missing eviction call, M2 — no API key pre-flight). Address all now, defer any, or dismiss any?**
A: Let's do them all.
