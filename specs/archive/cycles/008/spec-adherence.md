## Verdict: Pass

Cycle 8 implementation matches the architecture spec for container sandboxing. All four new Section 8 env var defaults are correct, all seven Section 9 security properties are implemented in `_build_container_cmd`, and the Dockerfile produces a non-root uid-1000 agent user. Two cycle-7 open items (Q-18 `--cwd` gap and `max_jobs` list propagation) were closed in this cycle. Four undocumented `spawn_session` additions (U1–U6 from cycle 7) remain absent from the architecture spec and are carried forward.

## Architecture Adherence

### Section 2 — Remote Job Dispatch data flow

Expected (architecture.md §2): remote-worker spawns `docker run --rm --cap-drop ALL ... -v {working_dir}:/workspace` → Job Container (Docker) → `claude --print --permission-mode dangerouslySkipPermissions`.

Actual: `_build_container_cmd` at `mcp/remote-worker/server.py:400-425` produces exactly this command sequence. The image name, bind mount, `dangerouslySkipPermissions`, and `--cwd /workspace` flags all match the diagram.

No deviation.

### Section 7 — OOM error row

Expected (architecture.md §7): "OOM inside container | Job marked failed with exit_code 137".

Actual: `_process_job` at `mcp/remote-worker/server.py:526-547` marks the job `failed` when `exit_code != 0`. Docker OOM-killed containers exit with code 137, which routes through this path and sets `record.status = "failed"` with `exit_code = 137` preserved. No explicit 137-detection is required; the generic non-zero path covers it.

No deviation.

### Section 8 — Environment variable defaults

Expected (architecture.md §8): `OUTPOST_AGENT_IMAGE` default `""`, `OUTPOST_CONTAINER_RUNTIME` default `""`, `OUTPOST_CONTAINER_MEMORY` default `4g`, `OUTPOST_CONTAINER_CPUS` default `2`. `OUTPOST_TIMEOUT` row removed.

Actual: `mcp/remote-worker/server.py:34-37`:
- `_agent_image = os.environ.get("OUTPOST_AGENT_IMAGE", "")` — matches.
- `_container_runtime = os.environ.get("OUTPOST_CONTAINER_RUNTIME", "")` — matches.
- `_container_memory = os.environ.get("OUTPOST_CONTAINER_MEMORY", "4g")` — matches.
- `_container_cpus = os.environ.get("OUTPOST_CONTAINER_CPUS", "2")` — matches.

`OUTPOST_TIMEOUT` is absent from architecture.md Section 8. Confirmed removed.

`IDEATE_WORKER_MAX_JOBS` is present in Section 8 (resolved by WI-032). Prior cycle-7 deviation is closed.

No deviation.

### Section 9 — Security properties table

Expected (architecture.md §9): seven security measures — `--cap-drop ALL`, `--security-opt no-new-privileges`, `--user 1000:1000`, `--memory`/`--memory-swap`, `--cpus`, `--pids-limit 512`, `--rm`.

Actual: `mcp/remote-worker/server.py:402-413`:
- `--rm`: line 402 — present.
- `--user 1000:1000`: line 407 — present.
- `--cap-drop ALL`: line 408 — present.
- `--security-opt no-new-privileges`: line 409 — present.
- `--memory {_container_memory}` and `--memory-swap {_container_memory}`: lines 410-411 — present, swap set equal to memory (no swap).
- `--cpus {_container_cpus}`: line 412 — present.
- `--pids-limit 512`: line 413 — present.

No deviation.

### Section 9 — Permission mode

Expected (architecture.md §9): "`--permission-mode dangerouslySkipPermissions` is always passed to `claude` inside the container. The `permission_mode` field in the job request is ignored in container mode."

Actual: `_build_container_cmd` at line 418 hardcodes `"--permission-mode", "dangerouslySkipPermissions"` regardless of `record.permission_mode`. The direct-invoke path (`_build_claude_cmd`) uses `record.permission_mode`. Correct fallback/container mode split.

No deviation.

### Section 9 — Fallback behavior

Expected (architecture.md §9): "When `OUTPOST_AGENT_IMAGE` is not set, the daemon falls back to spawning `claude` directly as a host subprocess."

Actual: `mcp/remote-worker/server.py:435-438`: `if _agent_image: cmd = _build_container_cmd(record) else: cmd = _build_claude_cmd(record)`. Direct-subprocess fallback is unchanged.

No deviation.

### Dockerfile vs Section 9 (uid 1000, non-root user)

Expected (architecture.md §9 and WI-047): Non-root user `agent` at uid/gid 1000 running inside the container; `--user 1000:1000` in docker run.

Actual (`mcp/remote-worker/Dockerfile:11-14`): `usermod -l agent -d /home/agent -m node && groupmod -n agent node` renames the base image's pre-existing `node` user (uid 1000, gid 1000) to `agent`. `USER agent` and `WORKDIR /workspace` follow. The incremental WI-047 review verified `id agent` returns `uid=1000(agent) gid=1000(agent)` at runtime.

No deviation.

## Principle Violations

None.

- **Principle 1 (Session Isolation)**: Container mode adds a second isolation layer. Each job gets its own ephemeral container (`--rm`, unique `--name job-{job_id}`). Confirmed.
- **Principle 3 (Graceful Degradation)**: Container `FileNotFoundError` (docker not on PATH) returns a structured actionable error message (`server.py:450-460`). Confirmed.
- **Principle 7 (Resource Bounds)**: Container mode enforces memory, CPU, and process limits. Confirmed.
- **Principle 12 (Minimal Dependencies)**: No new dependencies added. Container execution uses `subprocess.Popen` with the Docker CLI binary, same pattern as the existing `claude` invocation. Confirmed.

## Constraint Violations

None.

Container sandboxing additions are backward-compatible. When `OUTPOST_AGENT_IMAGE` is unset (the default), all prior constraints hold unchanged.

## Undocumented Behaviors

### U1-U4, U6: Undocumented `spawn_session` inputs and configuration (carried forward from cycle 7)

- **Location**: `mcp/session-spawner/server.py`
- **Description**: Four `spawn_session` inputs (`max_depth`, `output_format`, `team_name`, `exec_instructions`) and two configuration items (`OUTPOST_LOG_FILE` JSONL logging, `OUTPOST_ROLES_FILE` user role override) are implemented but absent from architecture sections 3, 5, and 8. First identified in cycle-7 spec-adherence review as U1–U6. WI-050 was scoped to container sandboxing documentation only; these items were not addressed.

### U7: `ANTHROPIC_API_KEY` passthrough in container mode (new)

- **Location**: `mcp/remote-worker/server.py:415`
- **Description**: `_build_container_cmd` injects `ANTHROPIC_API_KEY` from the host environment into the container via `-e ANTHROPIC_API_KEY={value}`. This is necessary for correct operation and was specified in WI-048 AC3, but it is not described in architecture §9. Future reviewers should not be surprised by the API key being injected into containers.

## Suggestions

1. Add `ANTHROPIC_API_KEY` injection to architecture §9 lifecycle description. The current §9 mentions bind mount and `--rm` cleanup but not the API key passthrough, which is equally essential for operation.

2. Address the six undocumented `spawn_session` additions (U1–U6 from cycle 7, carried forward). The next documentation sweep work item should cover at minimum `exec_instructions` (risk-bearing per open question Q-2), `OUTPOST_LOG_FILE` (observability knob operators need), and `OUTPOST_ROLES_FILE` (extends the role system beyond what architecture §5 describes).
