# Questions: Observability

## Q-1: Manager agent re-poll frequency and report trigger conditions
- **Question**: The manager agent monitors worker status and produces structured reports, but there is no specification for how frequently it should re-poll or what conditions trigger a new report. Is it event-driven (called on demand), polling on a schedule, or both?
- **Source**: specs/plan/work-items/035-manager-agent.md, archive/incremental/035-manager-agent.md
- **Impact**: Without a defined trigger model, integrations with the manager agent (e.g., brrr skill) cannot reliably know when reports are current.
- **Status**: open
- **Reexamination trigger**: The manager agent is integrated into an automated loop and callers need to reason about report freshness.

## Q-2: JSONL log retention and rotation policy
- **Question**: JSONL log entries are appended per session. There is no documented rotation policy, maximum log file size, or retention window. Long-running deployments will accumulate unbounded log files.
- **Source**: steering/guiding-principles.md (GP-4), specs/journal.md — WI-022
- **Impact**: Log files grow without bound on long-running deployments; disk pressure may eventually affect session spawning.
- **Status**: open
- **Reexamination trigger**: A user reports disk pressure from log accumulation or asks how to configure log rotation.

## Q-3: token_usage absent rather than null in normal-path spawn_session response
- **Question**: In the non-timeout path of `spawn_session`, `token_usage` is omitted when extraction fails rather than set to null. The timeout path correctly emits null. Should the normal path be fixed to match P-3 (absent token data is null, not omitted)?
- **Source**: archive/cycles/004/spec-adherence.md (MA1), archive/cycles/004/decision-log.md (OQ-010)
- **Impact**: Consumers expecting `token_usage` in all responses get KeyError on normal-path responses where extraction fails. P-3 is violated in this code path.
- **Status**: resolved
- **Resolution**: WI-024 fixed the code to unconditionally assign `response["token_usage"] = outcome_token_usage`. Normal path now emits null when extraction fails, matching the timeout path and P-3.
- **Resolved in**: cycle 5

## Q-4: Session-spawner README contradicts token_usage always-present contract
- **Question**: `mcp/session-spawner/README.md` lines 73 and 228 state "token_usage is included when...Omitted otherwise." WI-024 changed the implementation to always include `token_usage: null` when absent. The README was not updated. Should lines 73 and 228 be corrected to reflect the always-present null behavior?
- **Source**: archive/cycles/005/spec-adherence.md (GP-4/P-3 violation), archive/cycles/005/gap-analysis.md (SG2), archive/cycles/005/decision-log.md (OQ-013)
- **Impact**: Users reading the README will write incorrect integration code (`"token_usage" in response` rather than `response.get("token_usage") is not None`). Violates GP-4 (Transparency and Observability) and P-3 (absent token data is null, not omitted).
- **Status**: resolved
- **Resolution**: WI-026 updated README lines 73, 252, and 277 to consistently describe `token_usage` as always present with null value when extraction fails.
- **Resolved in**: cycle 6

## Q-5: conftest.py sys.modules key collision across test directories
- **Question**: Both `mcp/remote-worker/conftest.py` and `mcp/session-spawner/conftest.py` register their server module under the same `sys.modules["server"]` key. The second registration overwrites the first when pytest collects both directories. Current tests pass because importlib mode resolves imports before the collision manifests, but a future `import server` statement in either test file would silently import the wrong module. Should the keys be renamed to distinct values (e.g., `remote_worker_server` / `session_spawner_server`)?
- **Source**: archive/cycles/006/code-quality.md (M1), archive/cycles/006/gap-analysis.md (MG2), archive/cycles/006/decision-log.md (OQ-021)
- **Impact**: Low — no current test failure. Future maintenance risk if test files add bare `import server` statements.
- **Status**: open
- **Reexamination trigger**: A test failure caused by importing the wrong server module, or a test infrastructure refactor.
