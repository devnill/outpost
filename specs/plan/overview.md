# Change Plan — Outpost Cycle 8

## Trigger

Cycle 7 capstone review (2026-03-21). No critical or significant findings. Five work items address long-deferred minor code fixes and documentation gaps that accumulated across cycles 3–7. OQ-025 (in-memory session registry design decision) deferred to a future refinement.

## What Is Changing

**Code fixes (WI-028 through WI-031):**
- `proc.terminate()` race condition in `cancel_job` — HTTP 500 risk on concurrent process exit
- `FileNotFoundError` handling in both servers — actionable error message when `claude` binary not on PATH
- conftest `sys.modules` key collision — rename keys to prevent module shadowing between test suites
- `--cwd` flag in `_run_claude_job` — close behavioral divergence between session-spawner and remote-worker subprocess invocation
- `max_jobs` field in `list_remote_workers` output — forward available field per architecture spec

**Documentation (WI-032):**
- Root README: add `cancel_remote_job` to tool list, add config cross-reference to component READMEs
- CLAUDE.md: correct stale `requirements.txt` path
- architecture.md Section 8: add `IDEATE_WORKER_MAX_JOBS` row

## What Is NOT Changing

- Architecture — no structural changes to either server
- Guiding principles — all unchanged
- Role system, job lifecycle, dispatch model — unchanged
- OQ-025 (in-memory session registry) — explicitly deferred

## Scope Boundary

Changes are confined to:
- `mcp/remote-worker/server.py` — proc.terminate guard, FileNotFoundError handling, --cwd flag
- `mcp/session-spawner/server.py` — FileNotFoundError handling, max_jobs forwarding
- `mcp/remote-worker/test_server.py` — new tests for WI-028, WI-029, WI-031
- `mcp/session-spawner/test_server.py` — new tests for WI-029, WI-031
- `mcp/remote-worker/conftest.py` — key rename
- `mcp/session-spawner/conftest.py` — key rename
- `README.md` — documentation
- `CLAUDE.md` — documentation
- `specs/plan/architecture.md` — one table row

## Expected Impact

121 tests continue to pass. New tests added for FileNotFoundError, proc.terminate race, --cwd verification, and max_jobs forwarding. All changes are backward-compatible — no interface changes, no new dependencies.

## Work Items

| ID | Title | Complexity |
|----|-------|------------|
| 028 | Fix proc.terminate() race in cancel_job | easy |
| 029 | Handle FileNotFoundError for missing claude binary | easy |
| 030 | Fix conftest sys.modules key collision | easy |
| 031 | Add --cwd to _run_claude_job; add max_jobs to list_remote_workers output | easy |
| 032 | Documentation sweep (cycle 7 minor gaps) | easy |
