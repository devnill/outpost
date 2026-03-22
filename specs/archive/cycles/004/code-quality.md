# Code Quality Review — Cycle 4

**Review Date**: 2026-03-20
**Scope**: Full codebase re-verification after Cycle 3 PASS. Focus on cross-cutting concerns and cycle 3 change correctness.

---

## Verdict: Fail

One significant finding: role `system_prompt` is silently dropped for remote dispatch, creating silent behavioral divergence between local and remote roles.

---

## Critical Findings

None.

---

## Significant Findings

### S1: Role system_prompt Not Propagated to Remote Sessions

**File**: `mcp/session-spawner/server.py:751–768` (payload construction in `_handle_spawn_remote_session`)

**Description**: `_handle_spawn_remote_session` correctly resolves role constraints (`allowed_tools`, `permission_mode`, `max_turns`) and includes them in the HTTP POST payload. However, `resolved_role.get("system_prompt")` is never applied to `payload["prompt"]`. The local `spawn_session` handler (lines 289–292) prepends the system prompt correctly:

```python
if role_system_prompt:
    prompt = f"[ROLE: {role_name}]\n{role_system_prompt}\n\n{prompt}"
```

The remote dispatch path has no equivalent.

**Impact**: Three of the four built-in roles carry significant system prompts: `reviewer` ("do not modify files"), `manager` (coordination-only instruction), `proxy-human` (1,000-word decision protocol). A caller who passes `role="reviewer"` to `spawn_remote_session` expects a read-only session with behavioral enforcement. The session receives tool restrictions but no behavioral framing. For the `reviewer` role, the only behavioral constraint communicated to the spawned session is through the system prompt — the omission silently degrades the role's guarantees. The failure is invisible at call time.

**Regression**: This was introduced by WI-015. The fix was scoped to `allowed_tools` and `permission_mode` propagation but did not include `system_prompt`. Local and remote behavior now diverge silently for any role with a non-empty system_prompt.

**Fix**: In `_handle_spawn_remote_session`, after resolving the role, check `resolved_role.get("system_prompt")` and prepend it to `payload["prompt"]` using the same format as the local path (before payload construction).

**Relates to**: GP-8 (Role-Based Sessions), session-lifecycle P-4 (role constraints applied at spawn time by the caller)

---

## Minor Findings

### M1: proc.terminate() Unguarded Against Process-Already-Exited

**File**: `mcp/remote-worker/server.py:275`

**Description**: In `cancel_job`, `proc.terminate()` is called outside the lock with no exception handling. If the process has already exited between capturing `record.process` inside the lock and calling `terminate()` outside the lock, Python raises `ProcessLookupError` (Linux) or `OSError` (macOS) since the PID no longer exists. `subprocess.Popen.terminate()` does not suppress this.

The race window is small (lock-release to terminate call), but the unguarded call is technically incorrect. Wrapping the call in `try/except OSError` would close it.

**Relates to**: GP-3 (Graceful Degradation)

### M2: Variable Naming Mismatch in _run_claude_job Timeout Handling

**File**: `mcp/remote-worker/server.py:340–342`

**Description**: After `proc.kill()` on timeout, the code uses:
```python
stdout_bytes, stderr_bytes = proc.communicate()
partial_stdout = stdout_bytes if isinstance(stdout_bytes, str) else stdout_bytes.decode(...)
```
With `text=True`, `proc.communicate()` returns `(str, str)`, so `stdout_bytes` is already a string. The variable name suggests bytes handling; the `isinstance(stdout_bytes, str)` guard is correct but the naming is misleading. Minor cosmetic issue.

### M3: spawn_remote_session Tool Schema Declares role as string-only But Code Accepts Dict

**File**: `mcp/session-spawner/server.py:169–171` (inputSchema) vs. `server.py:692` (handler)

**Description**: The tool's `inputSchema` declares `role` as `"type": "string"`. However, the handler also accepts an inline role dict (line 692: `elif isinstance(role_arg, dict)`). The dict path allows bypassing role validation entirely — an inline dict is used as-is without looking it up in `_roles`. This is undocumented in the schema and would be invisible to any schema-driven client.

### M4: Tiny Race Window Between Popen() and record.process Assignment

**File**: `mcp/remote-worker/server.py:327–334`

**Description**: In `_run_claude_job`, `subprocess.Popen(...)` is called at line 327 and `record.process = proc` is assigned at line 334. If `cancel_job` runs in the event loop between the worker coroutine setting `status = "running"` (line 390 of `_worker`) and the thread executing line 334, `cancel_job` would capture `record.process = None`. The terminate call is skipped (`if proc is not None` guard at line 274). The process would run to completion without being killed; the job status would remain `"cancelled"` (correct per the guard at line 369 in `_process_job`). The process would run to completion despite the cancellation request. The race window is very small (Popen returns before line 334 executes), but the consequence is a cancelled job still executing.

---

## Suggestions

1. **Version alignment**: session-spawner (0.4.0) and remote-worker (0.1.0) have diverged significantly in version numbering. Consider a shared versioning scheme or documenting the versioning policy to prevent confusion.

2. **Datetime formatting utility**: Both servers independently implement ISO 8601 UTC timestamp formatting (`datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")`). This pattern appears 7 times across both files. A shared utility function would reduce duplication.

3. **IDEATE_WORKER_HOST undocumented**: `mcp/remote-worker/server.py:425` reads `IDEATE_WORKER_HOST` but this variable does not appear in the architecture env var table or any documentation.

4. **Output format documentation**: `output_format` parameter in `spawn_session` affects how session output is structured (JSON parsing for token usage extraction only works with `json` format). This behavioral dependency is not documented.
