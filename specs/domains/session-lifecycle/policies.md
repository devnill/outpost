# Policies: Session Lifecycle

## P-1: Session working directory isolation
Each spawned session receives its own working directory. The parent session's path is passed by reference; sessions cannot write to the parent workspace.
- **Derived from**: GP-1 (Session Isolation)
- **Established**: planning phase
- **Status**: active

## P-2: Filesystem-only session state
Session tracking uses filesystem files exclusively. In-memory state is not authoritative and must not be used as the source of truth.
- **Derived from**: GP-2 (Explicit State Management), GP-11 (Stateless Server)
- **Established**: planning phase
- **Status**: provisional — under review

> _Conflict identified in cycle 002: the implementation uses an in-memory `_session_registry` with opt-in JSONL logging (no default path), violating this policy. See Q-4 and D-8 for the contradicting finding._

## P-3: Resource limits are always enforced
Concurrency (semaphore), timeout (SIGKILL), output size (bytes), and prompt size (100 KB) limits are always enforced. The default configuration is conservative; unlimited is never an allowed default.
- **Derived from**: GP-7 (Resource Bounds)
- **Established**: planning phase
- **Status**: active

## P-4: Role constraints applied at spawn time by the caller
The spawning session specifies the role; role constraints are applied before the child session starts. A spawned session cannot self-elevate beyond the role it was assigned.
- **Derived from**: GP-8 (Role-Based Sessions)
- **Established**: planning phase
- **Status**: active
- **Amended**: cycle 5 — violation note removed. WI-018 (D-18) fixed the system_prompt propagation gap for remote sessions. All role dimensions (allowed_tools, permission_mode, max_turns, system_prompt) are now applied in both local and remote dispatch paths.

## P-5: Depth enforcement is server-side and hard
Sessions at maximum depth must receive an error response before session creation. Soft limits and warnings are not acceptable substitutes for hard enforcement.
- **Derived from**: GP-9 (Depth Limits)
- **Established**: planning phase
- **Status**: active

## P-6: Server restart must not lose visibility into already-running jobs
All session state lives in the OS process table and filesystem. The session-spawner server can restart without orphaning jobs that were running before the restart.
- **Derived from**: GP-11 (Stateless Server)
- **Established**: planning phase
- **Status**: active

## P-7: Subprocess call sites must catch missing-binary errors
All subprocess invocations of the `claude` CLI must catch `FileNotFoundError` and return a structured, actionable error message ("claude CLI not found on PATH") rather than propagating a raw Python exception. This applies to both session-spawner and remote-worker.
- **Derived from**: GP-3 (Graceful Degradation), Q-6 (open since cycle 3, escalated cycle 7)
- **Established**: cycle 7
- **Status**: active
