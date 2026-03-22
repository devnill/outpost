# Policies: Remote Dispatch

## P-1: Worker failures must not crash the orchestrator
Unreachable or failing remote workers return a structured error status. The session-spawner continues operating. No worker failure propagates as an unhandled exception to the caller.
- **Derived from**: GP-3 (Graceful Degradation)
- **Established**: planning phase
- **Status**: active

## P-2: HTTP/REST is the only supported transport for remote dispatch
Remote dispatch uses HTTP/REST. WebSocket and gRPC are out of scope. This applies to both the job submission API and the health check endpoint.
- **Derived from**: GP-5 (Configurable Dispatch), steering/constraints.md (C5)
- **Established**: planning phase
- **Status**: active

## P-3: All remote worker endpoints require API key authentication
Every endpoint on the remote worker daemon, including /health, /docs, and /openapi.json, requires a valid `X-API-Key` header. There is no anonymous access mode.
- **Derived from**: GP-6 (Protocol Compliance), steering/constraints.md (C14)
- **Established**: implementation phase (C1/S1 fixed in WI-030)
- **Status**: active

## P-4: Working directories must be validated against the configured base
When `IDEATE_WORKER_BASE_DIR` is set, any job whose `working_dir` falls outside that tree is rejected with HTTP 400. No path traversal is permitted.
- **Derived from**: GP-7 (Resource Bounds), steering/constraints.md (C13 analogue for remote)
- **Established**: implementation phase (S3 fixed in WI-030)
- **Status**: active

## P-5: Job queue is in-memory only; callers must handle worker restarts
The remote worker queues jobs in memory. A worker restart clears all queued and running jobs. Callers are responsible for re-submitting jobs after a restart. Persistent queuing is out of scope.
- **Derived from**: steering/constraints.md (C16)
- **Established**: planning phase
- **Status**: active

## P-6: Container mode activates via OUTPOST_AGENT_IMAGE; all security flags required
When `OUTPOST_AGENT_IMAGE` is non-empty, each job runs in an ephemeral Docker container with all security flags: `--cap-drop ALL`, `--security-opt no-new-privileges`, `--user 1000:1000`, `--memory`/`--memory-swap`, `--cpus`, `--pids-limit 512`, `--rm`. Container is named `job-{job_id}`. `--permission-mode dangerouslySkipPermissions` is always used inside the container. When `OUTPOST_AGENT_IMAGE` is empty (default), the daemon falls back to direct host subprocess execution with no breaking changes.
- **Derived from**: GP-1 (Session Isolation), GP-7 (Resource Bounds), architecture.md Section 9
- **Established**: cycle 8
- **Status**: active

## P-7: container_name must be set after process start and cancelled guard
`record.container_name` must be assigned only after `record.process = proc` and the cancelled guard check, never before `subprocess.Popen`. Both `process` and `container_name` must be cleared in the `finally` block. This prevents `cancel_job` from calling `docker stop` on a non-existent container.
- **Derived from**: D-26, cancel-path race condition identified in WI-048 incremental review
- **Established**: cycle 8
- **Status**: active

## P-8: In container mode, cancel_job must not call proc.terminate() after docker stop
When cancelling a containerized job, `docker stop` terminates the container and causes the host-side `docker run` process to exit. A subsequent `proc.terminate()` is always hitting an already-exited process. The `proc.terminate()` block must be gated on `not container_name` to avoid structurally incorrect exception-path execution on every container cancel.
- **Derived from**: D-33, cycle 9 capstone code review (C1)
- **Established**: cycle 9
- **Status**: active
