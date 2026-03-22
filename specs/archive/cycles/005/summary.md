# Review Summary — Cycle 5

## Overview

Cycle 5 addressed the critical system_prompt propagation regression and 6 significant findings from cycle 4. All 7 work items passed incremental review after rework. The implementation is functionally correct; documentation was not fully swept to match. Two significant documentation/test-coverage gaps remain and drive a refinement cycle.

## Critical Findings

None.

## Significant Findings

- [gap-analyst + spec-reviewer] session-spawner README lines 73 and 228 describe `token_usage` as "Omitted otherwise" — contradicts WI-024 which made it always-present null. Violates GP-4 and observability P-3. — relates to: WI-024 / observability P-3
- [gap-analyst] WI-021 integration Tests 2 and 3 call the remote-worker HTTP API directly rather than through `_handle_poll_remote_job` and `_handle_cancel_remote_job`. The session-spawner MCP tool layer is not exercised end-to-end for poll or cancel. — relates to: WI-021 / cross-cutting

## Minor Findings

- [spec-reviewer] `cancel_remote_job` absent from architecture.md component map tool list and session-spawner README tool table after WI-019 — relates to: WI-019 / WI-023
- [spec-reviewer + gap-analyst] `IDEATE_WORKER_MAX_JOBS` absent from remote-worker README env var table after WI-020 — relates to: WI-020 / WI-023
- [spec-reviewer] `max_jobs` field absent from architecture.md health endpoint schema after WI-020 — relates to: WI-020 / WI-023
- [code-reviewer] `pytest mcp/` fails due to duplicate `test_server.py` basenames with no `__init__.py` — relates to: cross-cutting
- [code-reviewer] `_evict_terminal_jobs_locked` lock contract is unenforced beyond naming convention — relates to: WI-020
- [code-reviewer] integration test `worker_server` fixture does not reset `_max_jobs` — relates to: WI-021

## Suggestions

None.

## Findings Requiring User Input

None — all findings can be resolved from existing context.

## Proposed Refinement Plan

The review identified 2 significant findings requiring a refinement cycle:

1. **WI-021 integration tests** (SG1): Replace Tests 2 and 3 in `mcp/test_integration.py` with calls to `spawner_mod._handle_poll_remote_job` and `spawner_mod._handle_cancel_remote_job`. The `worker_server` fixture is already correctly configured. This is a test body replacement — no new infrastructure needed.

2. **README token_usage contract** (SG2 + GP-4): Update `mcp/session-spawner/README.md` lines 73 and 228 to state that `token_usage` is always present with a `null` value when token information is unavailable.

Additional documentation gaps from WI-019 and WI-020 can be bundled into the same documentation work item:
- Add `cancel_remote_job` to architecture.md component map and session-spawner README tool table
- Add `IDEATE_WORKER_MAX_JOBS` to remote-worker README env var table
- Add `max_jobs` to architecture.md health endpoint schema

Minor code hygiene (pytest __init__.py, _max_jobs fixture reset, lock contract comment) can be a separate small work item.

Estimated scope: 2-3 work items, all easy/medium complexity.
