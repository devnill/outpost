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
- **Status**: active

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
