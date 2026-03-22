# Decision Log — Cycle 8

**Produced**: 2026-03-22
**Scope**: Cycle review — WI-047 through WI-050 (Docker container sandboxing for remote-worker).
**Work Items Completed**: 4 (WI-047, WI-048, WI-049, WI-050). WI-048 incremental verdict was Fail (no container tests); closed by WI-049.
**Prior state entering this cycle**: Cycle 7 pass with 0 critical, 0 significant findings. Eight open questions carried forward (OQ-021–OQ-028), including six undocumented `spawn_session` additions and three root README documentation gaps.
**Final Verdict**: Fail — 2 significant findings. No critical findings. S1 (API key in process table) is a security concern requiring a one-line fix. S2 (no test for docker stop cancel path) is a test coverage gap.

---

## Decisions Made

### D-028: Container sandboxing via ephemeral Docker containers (per-job)
- **Context**: Refinement interview 2026-03-22 Q1 — security and modularity requirements for running unattended Claude Code with `--dangerously-skip-permissions`.
- **Decision**: Each remote-worker job runs in an ephemeral Docker container (`--rm`) when `OUTPOST_AGENT_IMAGE` is set. Container is named `job-{job_id}` for cancel coordination. Host working directory is bind-mounted to `/workspace`. Container boundary replaces interactive permission checks; `--permission-mode dangerouslySkipPermissions` is always used inside container.
- **Source**: WI-048, architecture.md §9, interview 2026-03-22

### D-029: Backward-compatible container mode activation via env var
- **Context**: Interview Q3 — defer multi-tool abstraction; Docker sandboxing only for this cycle.
- **Decision**: Container mode activates only when `OUTPOST_AGENT_IMAGE` is non-empty. Default is empty string (no container). When empty, `_run_claude_job` behaves identically to pre-cycle-8 behavior. No breaking changes for deployments that don't set the new env var.
- **Source**: WI-048, specs/plan/overview.md (cycle 10 change plan)

### D-030: usermod/groupmod to create agent user in Dockerfile
- **Context**: WI-047 C1 — `node:20-bookworm-slim` base image ships with a `node` user at uid 1000. `useradd -u 1000` fails with "UID 1000 is not unique".
- **Decision**: Rename the existing `node` user to `agent` via `usermod -l agent -d /home/agent -m node && groupmod -n agent node`. This avoids uid conflict and produces `uid=1000(agent) gid=1000(agent)` at runtime.
- **Source**: WI-047 incremental review (C1 rework)
- **Related**: D-028 (uid 1000 requirement in docker run --user 1000:1000)

### D-031: container_name assigned after process start and cancelled guard
- **Context**: WI-048 C1 — original code set `record.container_name` before `subprocess.Popen`, creating a race where `cancel_job` could call `docker stop` on a non-existent container.
- **Decision**: `record.process = proc` is assigned immediately after the cancelled guard. `record.container_name = f"job-{record.job_id}"` is set only after `record.process` is assigned, both inside the same guard section. Both are cleared in the `finally` block.
- **Source**: WI-048 incremental review (C1 rework), server.py:468-470

### D-032: FileNotFoundError message branches on container mode
- **Context**: WI-048 C2 — hardcoded "claude CLI not found on PATH" message returned even in container mode where Docker is the missing binary.
- **Decision**: `except FileNotFoundError` branches on `_agent_image`: container mode returns "docker not found on PATH…", bare subprocess mode returns "claude CLI not found on PATH…".
- **Source**: WI-048 incremental review (C2 rework), server.py:450-460

### D-033: Daemon runs on host; container isolation sufficient for initial implementation
- **Context**: Interview Q2 — host daemon vs containerized daemon for deployment.
- **Decision**: Remote-worker daemon runs directly on host for initial implementation. Per-job containers provide isolation for agent execution. Daemon containerization deferred as a deployment concern for a later iteration.
- **Source**: Interview 2026-03-22 Q2

---

## Open Questions

### OQ-029: ANTHROPIC_API_KEY exposed in process table in container mode
- **Question**: Should `_build_container_cmd` use `-e ANTHROPIC_API_KEY` (name-only, inherits from host env) instead of `-e ANTHROPIC_API_KEY={value}` (bakes secret into command list)?
- **Context**: code-quality S1 — current implementation passes the key value as a command-line argument, making it visible to any user with access to `ps aux` or `/proc/<pid>/cmdline` on the remote-worker host. Fix is one line: remove the `={value}` from the `-e` argument. Docker inherits the variable from the host process environment when only the name is passed.
- **Impact**: On multi-tenant machines, the Anthropic API key is readable from the process table during any container job execution. Fix is trivial.
- **Source**: code-reviewer (S1)
- **Related**: OQ-030 (empty key passthrough)

### OQ-030: No pre-flight check for missing ANTHROPIC_API_KEY in container mode
- **Question**: Should the server emit a clear error (HTTP 500, actionable message) at job submission time when `OUTPOST_AGENT_IMAGE` is set but `ANTHROPIC_API_KEY` is unset/empty?
- **Context**: code-quality M2 — current code passes an empty key into containers, causing Claude CLI auth failures with an opaque error inside the container. No pre-flight validation exists.
- **Impact**: Operators who set `OUTPOST_AGENT_IMAGE` without `ANTHROPIC_API_KEY` will see jobs fail with confusing errors rather than an immediate configuration error.
- **Source**: code-reviewer (M2)
- **Related**: OQ-029

### OQ-031: cancel_job docker stop path lacks test coverage
- **Question**: Should a test be added that verifies `docker stop job-{id}` is called when cancelling a running containerized job?
- **Context**: code-quality S2 — `cancel_job` calls `subprocess.run(["docker", "stop", container_name], ...)` when `record.container_name` is set, but no test exercises this path. A regression in the cancel path (wrong name format, suppressed exceptions) would go undetected.
- **Impact**: Container-mode cancel reliability is not regression-tested.
- **Source**: code-reviewer (S2), gap-analyst (II1 related)

### OQ-032: remote-worker README missing container mode documentation
- **Question**: Should `mcp/remote-worker/README.md` be updated to document `OUTPOST_AGENT_IMAGE`, `OUTPOST_CONTAINER_RUNTIME`, `OUTPOST_CONTAINER_MEMORY`, `OUTPOST_CONTAINER_CPUS`, Docker prerequisites, and the `ANTHROPIC_API_KEY` forwarding requirement?
- **Context**: gap-analyst DG1 — env var table lists only 6 pre-cycle-8 variables. Container mode is undiscoverable from the README. The `ANTHROPIC_API_KEY` forwarding requirement is especially important since its absence causes silent job failures.
- **Impact**: Users cannot deploy container mode following the README alone.
- **Source**: gap-analyst (DG1)
- **Related**: OQ-033

### OQ-033: Root README has no mention of Docker sandboxing
- **Question**: Should `README.md` mention Docker sandboxing as a deployment option, reference `mcp/remote-worker/Dockerfile`, and name `OUTPOST_AGENT_IMAGE` as the activation variable?
- **Context**: gap-analyst DG2 — container sandboxing is the primary cycle 8 feature but is invisible at the project entry point.
- **Impact**: Container mode is undiscoverable from the project's primary documentation.
- **Source**: gap-analyst (DG2)
- **Related**: OQ-032

### OQ-034: architecture.md §9 does not document ANTHROPIC_API_KEY passthrough
- **Question**: Should architecture §9 describe the `ANTHROPIC_API_KEY` injection into containers?
- **Context**: spec-adherence U7 — `_build_container_cmd` injects `ANTHROPIC_API_KEY` from host env into container. This is necessary for correct operation but absent from the architecture's container lifecycle description.
- **Impact**: Future reviewers will be surprised by the API key injection; operators cannot determine from the architecture whether this is intentional behavior.
- **Source**: spec-reviewer (U7)
- **Related**: OQ-029, OQ-032

### OQ-035: _evict_terminal_jobs_locked not called in cancel-while-starting path
- **Question**: Should `_process_job` call `_evict_terminal_jobs_locked()` in the `result is None` (cancel-while-starting sentinel) branch?
- **Context**: code-quality M1, gap-analyst IG1 — all other terminal-state paths in `_process_job` call eviction, but the cancel-while-starting sentinel path does not. The record is terminal at that point.
- **Impact**: Jobs cancelled during Popen initialization count against store capacity without triggering compaction. Minor under normal conditions; accumulates if many cancels arrive through this path.
- **Source**: code-reviewer (M1), gap-analyst (IG1) — two reviewers independently flagged this
- **Related**: D-031

---

## Carried-Forward Open Questions (from cycle 7, unresolved)

- **OQ-024**: FileNotFoundError on missing claude binary produces non-actionable errors (session-spawner path). Still open.
- **OQ-025**: In-memory session registry contradicts filesystem-state design decision (PL-003). Still open.
- **OQ-026**: CLAUDE.md references non-existent requirements.txt. Status: verify if WI-032 addressed this.
- **OQ-027**: cancel_remote_job absent from root README tool list. Status: verify if WI-032 addressed this.
- **OQ-028**: Root README configuration section omits most environment variables. Still open (partially — DG2/OQ-033 is now the container-specific sub-issue).
- **U1–U6**: Six undocumented `spawn_session` additions (max_depth, output_format, team_name, exec_instructions, OUTPOST_LOG_FILE, OUTPOST_ROLES_FILE) still absent from architecture spec. Carried forward by spec-reviewer U1–U4, U6.

---

## Cross-Cycle Patterns

**Documentation follows implementation by one cycle**: Cycle 8 repeats the cycle 5→6→7 pattern where implementation work items (WI-047, WI-048, WI-049) were completed but the corresponding documentation for the new feature was not updated in the same cycle. The architecture document (WI-050) was updated, but the user-facing READMEs were not. This pattern has occurred in cycles 4, 5, and now 8.

**Security findings arise at container boundaries**: The `ANTHROPIC_API_KEY` exposure (OQ-029) is the first security finding in the project. It arises at the new container/host boundary, where secrets must be explicitly forwarded. Prior cycles had no cross-trust-boundary integrations.

**Cancel-path correctness remains complex**: Cancel-while-starting races (cycles 7–8 D-031), `proc.terminate()` race (cycle 1 D-EX), and the eviction gap (OQ-035) all occur in the cancel code path. The cancel path has the highest defect density of any code area in the project.
