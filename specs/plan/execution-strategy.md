# Execution Strategy — Outpost Cycle 8

## Mode
Sequential

## Parallelism
Max concurrent agents: 1

## Worktrees
Enabled: no

## Review Cadence
After each work item.

## Work Items

| ID | Title | Complexity | Depends |
|----|-------|------------|---------|
| 028 | Fix proc.terminate() race in cancel_job | easy | — |
| 029 | Handle FileNotFoundError for missing claude binary | easy | — |
| 030 | Fix conftest sys.modules key collision | easy | — |
| 031 | Add --cwd to _run_claude_job; add max_jobs to list_remote_workers | easy | — |
| 032 | Documentation sweep (cycle 7 minor gaps) | easy | — |

## Dependency Graph

All five work items are independent. No inter-item dependencies.

```
028 (independent)
029 (independent)
030 (independent)
031 (independent)
032 (independent)
```

## Work Item Groups and Recommended Order

**Group 1 (remote-worker code)**: 028, 031
Both modify `mcp/remote-worker/server.py`. Run sequentially to avoid conflicts.

**Group 2 (both servers code)**: 029
Modifies both `mcp/remote-worker/server.py` and `mcp/session-spawner/server.py` and both test files.

**Group 3 (test infrastructure)**: 030
Modifies all four conftest/test files. Run after the code changes so tests pass cleanly.

**Group 4 (documentation)**: 032
No code deps. Can run at any point; placed last to verify documentation against completed code.

Recommended sequential order: 028 → 031 → 029 → 030 → 032

Note: 028 and 031 both touch remote-worker/server.py. Run 028 first (smaller change), then 031. If they happen to be run in parallel by accident, the changes are in different functions (cancel_job vs _run_claude_job / _fetch_worker_health) and will not conflict, but sequential is safer.

## Agent Configuration
Model for development: sonnet
Model for review: sonnet
Permission mode: acceptEdits
