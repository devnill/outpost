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
