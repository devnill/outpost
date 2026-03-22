# Domain Registry

current_cycle: 7

## Domains

### session-lifecycle
Local subprocess session management — spawning, resource limits (concurrency, timeout, output size, depth), role-based capability constraints, and filesystem-based state tracking.
Files: domains/session-lifecycle/policies.md, decisions.md, questions.md

### remote-dispatch
Remote worker daemon and HTTP REST API — job submission, job lifecycle states, worker pool management, API key authentication, working directory validation, and git diff capture.
Files: domains/remote-dispatch/policies.md, decisions.md, questions.md

### observability
Session event logging, JSONL audit trail, token budget tracking, status table output, and the manager agent for structured worker status reporting.
Files: domains/observability/policies.md, decisions.md, questions.md

## Cross-Cutting Concerns

- **Configuration via environment variables only**: All three domains share this constraint (C19). No config files, no command-line flags. Applies equally to session-spawner and remote-worker.
- **Minimal dependencies**: GP-12 applies across all components. FastAPI/aiohttp for remote work, mcp for protocol — no heavy frameworks added by any domain.
- **Outpost is infrastructure, not a participant**: GP boundary that applies across all domains — Outpost orchestrates sessions; it does not execute the work itself (constraints C15).
- **Installation paths broken (cycle 2)**: Plugin manifest, root README `pip install` command, and root README `claude mcp add` command all reference non-existent file paths. Unanimous finding across all three cycle 2 reviewers. Mechanical fixes required before next release. Source: archive/cycles/002/summary.md (CI1, CI2, CI3), archive/cycles/002/decision-log.md (OQ-006). **RESOLVED in cycle 003** — D-15 fixed all installation paths.
- **Architecture document divergence (cycle 2)**: Multiple parameter names (`worker_url` vs `worker_name`), env var names (`OUTPOST_CONCURRENCY` vs `OUTPOST_MAX_CONCURRENCY`), status values, and the `spawn_session` output schema differ between the architecture document and the implementation. **RESOLVED in cycle 003** — D-009 (WI-016) synchronized architecture with implementation.
- **Integration tests gap (cycle 3)**: No integration tests verify HTTP interaction between session-spawner and remote-worker. All tests use mocks. Source: archive/cycles/003/gap-analysis.md (II1). **RESOLVED in cycle 6** — WI-021 added 5 integration tests (cycle 5); WI-025 replaced tests 2 and 3 to exercise the MCP tool layer end-to-end (cycle 6). All 5 integration tests now cover the full session-spawner fan-out path.
- **Role system documentation contradiction (cycle 3)**: README states role is "observability label only" but implementation propagates constraints. Source: archive/cycles/003/gap-analysis.md (II2). **RESOLVED in cycle 5** — WI-023 updated both READMEs. WI-018 fixed system_prompt propagation for remote sessions. Role documentation now accurately describes constraint propagation in both local and remote paths.
- **Partial-fix regression pattern (cycle 4)**: Cycle 3 work items that addressed multi-dimension gaps fixed only part of each gap. WI-015 fixed tool constraints but omitted system_prompt (CG1). WI-017 implemented cancellation but did not update README (SG1). WI-016 synchronized architecture but left residual inaccuracies (MA2, MA3). Source: archive/cycles/004/decision-log.md (Cross-Cycle Pattern 1). **Largely resolved in cycle 5** — WI-018 fixed system_prompt propagation, WI-023 updated README and architecture. Pattern recurred in cycle 5: WI-019/WI-020/WI-024 implemented changes correctly but documentation was not fully swept (OQ-013, OQ-014, OQ-015, OQ-016).
- **Architecture residual inaccuracies (cycle 4)**: After WI-016, the architecture document still contains an incorrect `cancelled` state description (OQ-004), a non-existent `OUTPOST_TIMEOUT` env var (OQ-005), and undocumented `IDEATE_WORKER_HOST` env var. Source: archive/cycles/004/spec-adherence.md (MA2, MA3), archive/cycles/004/code-quality.md (Suggestion 3). **Partially resolved in cycle 5** — WI-023 corrected the job-states table and OUTPOST_TIMEOUT annotation. New gaps: cancel_remote_job absent from architecture tool list (OQ-014), max_jobs absent from health schema (OQ-016). **RESOLVED in cycle 6** — WI-026 added cancel_remote_job and max_jobs to architecture. One minor residual: IDEATE_WORKER_MAX_JOBS absent from architecture Section 8 env var table (OQ-020).
- **Documentation sweep gap pattern (cycle 5)**: Cycle 5 work items correctly implemented all code changes but documentation was not fully swept to match. Three documentation gaps remained: cancel_remote_job absent from architecture/README tool lists, IDEATE_WORKER_MAX_JOBS absent from README env var table, README token_usage contract contradicts implementation. **RESOLVED in cycle 6** — WI-026 closed all three gaps. README and architecture now consistent with implementation.
- **Root README documentation gaps (cycle 7)**: Three minor documentation gaps at the project entry point identified by capstone review: `cancel_remote_job` absent from root README tool list (OQ-027), `CLAUDE.md` references non-existent `requirements.txt` (OQ-026), root README Configuration section omits most environment variables with no cross-reference to component READMEs (OQ-028). All are one-line fixes. Source: archive/cycles/007/gap-analysis.md (MR1, MI3, MR3), archive/cycles/007/decision-log.md (OQ-026, OQ-027, OQ-028).
- **Undocumented spawn_session additions (cycle 7)**: Six additions to `spawn_session` beyond architecture spec identified: `max_depth`, `output_format`, `team_name`, `exec_instructions` inputs; `OUTPOST_LOG_FILE` JSONL logging; `OUTPOST_ROLES_FILE` user role override. None harmful; several should be added to architecture sections 5 and 8. Source: archive/cycles/007/spec-adherence.md (U1–U6).
