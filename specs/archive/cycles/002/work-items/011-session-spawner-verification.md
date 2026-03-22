# 011: Session Spawner Verification

## Source
Archived from plan/work-items.yaml#011 after cycle 2 review (Pass).

## Title
Session Spawner Verification

## Complexity
medium

## Scope
- mcp/session-spawner/server.py (modify)
- mcp/session-spawner/test_server.py (modify)
- mcp/session-spawner/README.md (modify)

## Dependencies
none

## Acceptance Criteria
1. All tests in mcp/session-spawner/test_server.py pass (run pytest)
2. spawn_session tool is implemented with parameters: prompt, working_dir, model, role, max_turns, timeout, permission_mode, allowed_tools
3. Tool returns structured result with fields: output, exit_code, session_id, duration_ms, error, token_usage
4. Depth tracking enforced via OUTPOST_SPAWN_DEPTH env var; spawned sessions receive OUTPOST_SPAWN_DEPTH=N+1
5. Depth limit enforced server-side before session creation; error returned when depth >= OUTPOST_MAX_DEPTH
6. Concurrency limited via asyncio.Semaphore (default controlled by OUTPOST_MAX_CONCURRENCY)
7. Output truncated at 50KB byte boundary with overflow written to temp file in working_dir
8. Prompt size validated (reject > 100KB)
9. Working directory validated (must exist); OUTPOST_SAFE_ROOT enforced when set
10. Structured error returned for all failure modes: prompt too large, invalid working_dir, depth exceeded, timeout, subprocess failure
11. mcp/session-spawner/README.md documents setup, all environment variables, and safety mechanisms
12. No acceptance criterion from the original spec (work item 010) is unimplemented; gaps found must be fixed or documented as intentional deviations

## Implementation Notes
See plan/notes/011.md

## Incremental Review
archive/cycles/002/incremental/011-session-spawner-verification.md — Verdict: Pass (after rework: 3 minor findings fixed)
