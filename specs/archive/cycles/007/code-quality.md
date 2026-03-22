# Code Quality Review — Cycle 7

## Overview

Comprehensive review of the current implementation state across both MCP servers: `mcp/session-spawner/server.py` and `mcp/remote-worker/server.py`. No new work items were executed this cycle; this is a capstone quality pass on the converged codebase. No critical or significant findings. Four minor findings, including one new item (M4) identifying a false claim in a docstring related to the `--cwd` discrepancy between the two servers.

---

## Critical Findings

None.

---

## Significant Findings

None.

---

## Minor Findings

### M1: proc.terminate() race condition in cancel_job

- **File**: `mcp/remote-worker/server.py:288` and `:296`
- **Issue**: After the job store lock is released, `proc.terminate()` is called without a `ProcessLookupError` guard. If the subprocess exits in the window between lock release and `terminate()`, the call raises `ProcessLookupError` and the endpoint returns HTTP 500 instead of the expected 204. The same applies to `proc.kill()` at line 296 in the `TimeoutError` handler.
- **Suggested fix**:
  ```python
  if proc is not None:
      try:
          proc.terminate()
      except ProcessLookupError:
          pass
      try:
          await asyncio.wait_for(
              asyncio.to_thread(proc.wait),
              timeout=2.0
          )
      except asyncio.TimeoutError:
          try:
              proc.kill()
          except ProcessLookupError:
              pass
  ```

### M2: conftest.py sys.modules["server"] collision risk

- **File**: `mcp/session-spawner/test_server.py` (conftest fixture) and `mcp/remote-worker/test_server.py` (conftest fixture)
- **Issue**: Both test files register their respective server module under `sys.modules["server"]`. If both test suites are collected in the same pytest session (e.g., `pytest` run from the repo root), the second registration silently overwrites the first. Tests that import `server` after both modules are registered will resolve whichever was loaded last, producing incorrect test behavior that may be intermittent depending on collection order. No current failure because the two test files are in separate directories and are typically run independently.
- **Suggested fix**: Register each module under a distinct key (`sys.modules["session_spawner_server"]` and `sys.modules["remote_worker_server"]`), and update imports in the respective test files to match.

### M3: IDEATE_WORKER_MAX_JOBS absent from architecture.md Section 8 table

- **File**: `specs/plan/architecture.md` (Section 8 configuration table)
- **Issue**: `IDEATE_WORKER_MAX_JOBS` is a documented and implemented configuration variable (described in `mcp/remote-worker/server.py:9`, consumed at line 90) that controls the maximum number of job records retained in the job store. It is absent from the architecture Section 8 environment variable reference table, making the table incomplete for operators configuring the remote worker.
- **Suggested fix**: Add a row to the Section 8 table: `IDEATE_WORKER_MAX_JOBS | remote-worker | Max jobs retained in the in-memory store before LRU eviction (default: 1000)`.

### M4: _run_claude_job docstring claims identical subprocess pattern to session-spawner, but omits --cwd

- **File**: `mcp/remote-worker/server.py:347`
- **Issue**: The docstring states "Uses the same subprocess pattern as session-spawner." This claim is false. `session-spawner` passes `"--cwd", working_dir` as an explicit CLI argument to the `claude` binary (session-spawner line 447–448) in addition to setting `cwd=working_dir` on the subprocess (line 483). `_run_claude_job` sets `cwd=record.working_dir` on the subprocess (line 367) but does not pass `--cwd` to the CLI. The `--cwd` flag instructs the Claude CLI where to anchor its project root for `.claude/` config discovery, `CLAUDE.md` loading, and trust boundary enforcement. Since the subprocess `cwd` is set correctly, Claude CLI will inherit the right working directory from the OS, and in practice the behavior is likely equivalent for most use cases. However, the inconsistency is a latent correctness risk: if Claude CLI's `--cwd` handling ever diverges from process cwd inheritance (e.g., when invoked from a wrapper script that changes cwd), remote-worker jobs will silently use a different project root than session-spawner jobs dispatched to the same directory. The docstring amplifies the risk by asserting equivalence that does not exist.
- **Suggested fix**: Either add `"--cwd", record.working_dir` to `cmd` after `"--max-turns", str(record.max_turns)` (matching session-spawner exactly), or remove the false equivalence claim from the docstring and add a comment explaining the intentional difference.

---

## Suggestions

- The `--cwd` flag addition to `_run_claude_job` (M4 fix) is low-effort and eliminates the divergence entirely. It is the preferred fix over updating only the docstring.
- Once M2 is resolved, running `pytest` from the repo root should be added to the CI/CD script to prevent reintroduction of the silent module shadowing issue.

---

## Verdict

Pass.

No critical or significant findings. Four minor findings: M1 and M2 are pre-existing tracked open items carried forward from cycle 6. M3 is a pre-existing documentation gap. M4 is a new finding: a false docstring claim that also surfaces a latent behavioral divergence between the two servers. All four are minor in isolation; none indicates a defect that will produce incorrect results under current normal operating conditions.
