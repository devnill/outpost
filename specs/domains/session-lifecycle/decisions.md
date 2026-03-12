# Decisions: Session Lifecycle

## D-1: Filesystem-only state (no database, no in-memory store)
- **Decision**: All session tracking uses the filesystem. No databases, no in-memory session stores, no external state services.
- **Rationale**: Simplicity and recoverability — a server restart does not lose session state. Matches the single-user, local-tooling deployment model.
- **Assumes**: The filesystem is durable and accessible by the server process.
- **Source**: steering/constraints.md (C4), steering/interview.md
- **Status**: settled

## D-2: Role definitions are static JSON loaded at startup
- **Decision**: Roles are defined in JSON files loaded when the server starts. There is no API for dynamic role creation or modification at runtime.
- **Rationale**: Security and simplicity — static roles cannot be injected at request time by a malicious caller.
- **Assumes**: Role changes require a server restart, which is acceptable for this deployment model.
- **Source**: steering/constraints.md (C10), plan/architecture.md §5
- **Status**: settled

## D-3: Depth limit enforced server-side; error returned before session creation
- **Decision**: The depth check runs before any subprocess is created. Sessions at max depth receive a structured error, not a warning.
- **Rationale**: Prevents runaway recursion. Client-side enforcement would be bypassable.
- **Source**: plan/architecture.md §6, steering/constraints.md (C9)
- **Status**: settled

## D-4: Timed-out sessions are killed via SIGKILL
- **Decision**: When a session exceeds its timeout, the process is terminated with SIGKILL and partial output is returned.
- **Rationale**: SIGTERM could be ignored by the subprocess. SIGKILL guarantees termination.
- **Source**: steering/constraints.md (C12)
- **Status**: settled

## D-5: model parameter uses caller-wins pattern
- **Decision**: If the caller specifies a model, it overrides any model defined in the role. Role default is used only when the caller omits the parameter.
- **Rationale**: Consistent with the pattern used for other role-overridable parameters (max_turns, permission_mode, allowed_tools). Caller has the most context about what model is needed.
- **Source**: specs/journal.md — WI-039 rework note
- **Status**: settled

## D-6: exec_instructions propagate to child sessions via environment variable
- **Decision**: The `exec_instructions` parameter is injected into the child session's prompt and propagated to grandchild sessions via the `IDEATE_EXEC_INSTRUCTIONS` environment variable.
- **Rationale**: Enables consistent execution context across session depth without requiring callers to re-pass instructions at every level.
- **Source**: specs/journal.md — WI-024
- **Status**: settled
