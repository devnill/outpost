# Gap Analysis — Cycle 4

## Summary

Two new gaps were introduced by cycle 3 work: WI-015 silently drops role `system_prompt` for remote dispatch (a correctness regression), and WI-017 left the remote-worker README documenting only queued-job cancellation when running-job cancellation was also implemented. Eleven significant and minor gaps from cycle 3 remain unaddressed.

---

## Critical Gaps

### CG1: Role system_prompt Silently Dropped for Remote Sessions

`_handle_spawn_remote_session` in `mcp/session-spawner/server.py` (lines 751–768) builds the HTTP payload with resolved `allowed_tools`, `permission_mode`, and `max_turns` from the role — but never prepends the role's `system_prompt` to the `prompt` field.

The local `spawn_session` path (lines 289–292) does this correctly:

```python
if role_system_prompt:
    prompt = f"[ROLE: {role_name}]\n{role_system_prompt}\n\n{prompt}"
```

The remote dispatch path has no equivalent. Three of the four built-in roles have non-trivial system prompts: `reviewer` instructs the session not to modify files; `manager` instructs it to coordinate rather than implement; `proxy-human` carries a 1,000-word decision protocol. When any of these roles is used with `spawn_remote_session`, the role's behavioral constraints — expressed entirely through the system prompt — are discarded without error.

A caller who passes `role="reviewer"` to `spawn_remote_session` expects a read-only session with behavioral enforcement. They get tool restrictions but no behavioral framing. The failure is silent.

**What is missing**: In `_handle_spawn_remote_session`, check for `resolved_role.get("system_prompt")` and prepend it to `payload["prompt"]` using the same format as the local path, before dispatching the HTTP POST.

**Relates to**: GP-8 (Role-Based Sessions), session-lifecycle P-4 (role constraints applied at spawn time)

---

## Significant Gaps

### SG1: DELETE /jobs/{job_id} README Contradicts Implementation After WI-017

`mcp/remote-worker/README.md` states: "Cancel a queued job. Only jobs with status `queued` can be cancelled. Running, completed, or failed jobs cannot be cancelled." The 409 error condition says: "job is not in `queued` status (already running, completed, failed, or cancelled)."

WI-017 implemented running-job cancellation. `cancel_job` (lines 260–284 of `mcp/remote-worker/server.py`) handles the `running` case: captures process reference, sets status to `cancelled`, sends SIGTERM with 2-second SIGKILL fallback. The job lifecycle diagram in the README also omits the `running → cancelled` transition.

A caller reading the README will attempt to cancel a running job, expect 409, and not retry — while the actual behavior is 204 with cancellation.

### SG2: No MCP Tool to Cancel a Remote Job from Session-Spawner

The remote-worker exposes `DELETE /jobs/{job_id}`. The session-spawner provides `spawn_remote_session` and `poll_remote_job` but no `cancel_remote_job` tool. A caller who dispatches a job and determines it should stop has no MCP-level mechanism to cancel it. They must call the remote worker's HTTP API directly — requiring independent knowledge of the worker URL and API key.

Identified as II4 in cycle 3. WI-017 was scoped to the remote-worker side only; no corresponding MCP tool was added to session-spawner.

**What is missing**: A `cancel_remote_job` tool in session-spawner that issues `DELETE /jobs/{job_id}` to the appropriate worker using the same worker resolution and auth key logic already present in `_handle_poll_remote_job`.

### SG3: Job Store Memory Leak in Remote Worker (Persistent: EC1)

`job_store` in `mcp/remote-worker/server.py` accumulates completed, failed, and cancelled jobs indefinitely. No eviction, no TTL, no size cap. Memory grows linearly with total jobs processed over the lifetime of the process. Identified in cycle 3. Still unaddressed.

### SG4: Role Documentation Contradiction Persists and Is Now Worse (Persistent: II2)

`mcp/session-spawner/README.md` and `mcp/remote-worker/README.md` both state the role is "an observability label for remote dispatch" and that "tool restrictions, system prompt injection, and permission mode overrides defined in the role are not applied to the remote claude subprocess."

WI-015 made `allowed_tools` and `permission_mode` propagate to remote sessions. Both READMEs still describe the pre-WI-015 behavior. The contradiction now has two dimensions: tool restrictions and permission mode are applied (documentation is wrong); system prompt injection is not applied (documentation happens to be accidentally correct on this point, per CG1).

### SG5: No Integration Tests Between Components (Persistent: II1)

No test file exercises the HTTP integration between session-spawner and remote-worker. All session-spawner tests mock aiohttp; all remote-worker tests use in-process ASGI transport. The contract — payload field names, status codes, response shapes — is untested end-to-end. Identified as II1 in cycle 3. Still unaddressed.

### SG6: No Configuration Validation at Startup (Persistent: MI4)

The remote-worker does not validate at startup that `IDEATE_WORKER_API_KEY` is set — it only rejects requests at runtime. An operator who starts the server without configuring the API key discovers the misconfiguration only when the first authenticated request arrives. Session-spawner silently accepts worker entries without `api_key` (treats missing key as empty string). Identified in cycle 3. Still unaddressed.

---

## Minor Gaps

### MG1: proc.terminate() Unguarded Against ProcessLookupError (Persistent: EC5)

In `cancel_job` in `mcp/remote-worker/server.py:275`, `proc.terminate()` is called outside the lock after setting status to `cancelled`. If the process exited between capturing `record.process` inside the lock and calling `proc.terminate()` outside the lock, `proc.terminate()` raises `ProcessLookupError` (Linux) or `OSError` (macOS). `subprocess.Popen.terminate()` does not suppress this. A `try/except OSError` wrapping `proc.terminate()` is absent.

### MG2: Remote Worker URL Trailing Slash (Persistent: EC4)

URL construction uses `.rstrip('/')` before appending paths. This handles simple trailing slashes. An internal double slash in the path component is not normalized. Deferred in cycle 3 as most servers handle this gracefully.

### MG3: Claude CLI Not on PATH Produces Unhelpful Error (Persistent: EC2)

Both components invoke `claude` as a subprocess without checking its existence. A `FileNotFoundError` from `subprocess.Popen` propagates as a generic Python exception. Neither component catches this and returns an actionable error naming the missing dependency.

### MG4: git_diff Output Not Truncated (Persistent: EC3)

`_capture_git_diff` in `mcp/remote-worker/server.py` captures `git diff HEAD` with no size limit. For large changesets this produces unbounded memory usage and unbounded HTTP response payloads. Session output has a 50KB truncation limit; git diff has none.

### MG5: No Graceful Shutdown for Orphaned Local Sessions (Persistent: MI5)

If session-spawner is terminated while local sessions are running, the `claude` subprocesses continue as orphans. No signal handler or atexit hook cleans them up. The remote-worker lifespan cancels worker coroutines but does not terminate running `claude` subprocesses.

### MG6: No Retry Logic for Remote Worker HTTP Calls (Persistent: MI6)

`_handle_spawn_remote_session` and `_handle_poll_remote_job` make single HTTP attempts with no retry. Transient network failures or brief worker restarts return errors immediately to the caller.

---

## Persistent Gaps (from Prior Cycles, Still Open)

| Prior ID | Current ID | Description |
|----------|-----------|-------------|
| EC1 | SG3 | Job store memory leak — no eviction |
| EC2 | MG3 | Claude CLI not on PATH produces unhelpful error |
| EC3 | MG4 | git_diff output not size-limited |
| EC4 | MG2 | Remote worker URL with trailing slash (deferred) |
| EC5 | MG1 | proc.terminate() unguarded against ProcessLookupError |
| II1 | SG5 | No integration tests between session-spawner and remote-worker |
| II2 | SG4 | Role documentation contradiction — worsened by WI-015 |
| II4 | SG2 | No cancel_remote_job MCP tool in session-spawner |
| MI4 | SG6 | No configuration validation at startup |
| MI5 | MG5 | No graceful shutdown / orphaned subprocess cleanup |
| MI6 | MG6 | No retry logic for remote worker HTTP calls |

---

## Addressed Gaps

The following gaps were resolved in cycle 3:

- **WI-012**: Installation paths fixed in plugin manifest and READMEs.
- **WI-013**: poll_remote_job auth error priority corrected.
- **WI-014**: poll_remote_job missing timestamp fields (`created_at`, `started_at`, `completed_at`) added to `_poll_one`.
- **WI-015**: Role constraints (`allowed_tools`, `permission_mode`, `max_turns`) now propagated to remote sessions via HTTP payload. The cycle 2 critical finding that role constraints were never applied to remote sessions is resolved for these fields. (`system_prompt` propagation is the new gap CG1.)
- **WI-016**: Architecture document synchronized with implementation.
- **WI-017**: Running-job cancellation implemented in remote-worker. `DELETE /jobs/{job_id}` handles both queued and running jobs. (README documentation of this feature is the new gap SG1.)
- **EC6 (cycle 3)**: Session-spawner HTTP session reuse resolved — a shared `aiohttp.ClientSession` is created in `main()` and reused via `_get_http_session()`.

---

## Verification Answers

**Does cancel_running_job properly handle the race where _process_job completes just before terminate() is called?**

The `if record.status != "cancelled"` guard in `_process_job` (line 369) correctly prevents overwriting a cancelled status. However, `proc.terminate()` in `cancel_job` (line 275) is called outside the lock with no exception handling. If the process exited before `terminate()` runs, `OSError`/`ProcessLookupError` is raised unhandled. The race is mostly resolved but terminate() is unguarded. See MG1.

**Is there a gap where inline role dict passed to spawn_remote_session doesn't include system_prompt?**

Yes, and broader: even named roles with system_prompt don't get it propagated. The entire remote dispatch path does not prepend system_prompt for any role, named or inline. This is CG1.
