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
