# Guiding Principles

## 1. Session Isolation
Each spawned session operates in complete isolation. No shared state, no shared working directory, no shared environment variables beyond explicit passing. Sessions are independent processes that cannot interfere with each other.

## 2. Explicit State Management
All coordination between sessions happens via durable artifacts on disk. The session registry, status files, and result outputs are the only communication mechanism. No in-memory state persists between tool invocations.

## 3. Graceful Degradation
When a session fails, the system captures the failure reason and continues. Remote worker unavailability is handled gracefully with queueing and fallback. Timeouts are enforced with clear error reporting. The orchestrator never crashes due to worker failures.

## 4. Transparency and Observability
Every session lifecycle event is logged. Status queries return complete information about job state, timing, and outcomes. The manager agent has full visibility into worker health and job progress. Nothing is hidden.

## 5. Configurable Dispatch
The user chooses whether sessions run locally or remotely. Local dispatch uses subprocess spawning with resource limits. Remote dispatch uses HTTP APIs to worker daemons. Both modes share the same job submission interface.

## 6. Protocol Compliance
The MCP server implementation follows the Model Context Protocol specification precisely. Tool schemas, error handling, and async semantics match what Claude Code expects. Deviations from protocol are bugs.

## 7. Resource Bounds
Concurrency limits, timeouts, and output truncation protect the system from runaway resource consumption. Defaults are conservative. User configuration can adjust limits, but unlimited is never the default.

## 8. Role-Based Sessions
Sessions can be assigned roles that constrain their capabilities. A worker role, reviewer role, and manager role each have defined tool sets and permissions. This enables safe parallel execution with appropriate privilege levels.

## 9. Depth Limits
Recursive session spawning is bounded. The depth limit prevents infinite recursion when a spawned session itself tries to spawn. Limits are enforced server-side and communicated via environment variables.

## 10. Result Integrity
Job results are captured completely and accurately. Output truncation preserves the most relevant content. Git diffs capture workspace changes. Exit codes and error messages are preserved. The caller receives enough information to understand what happened.

## 11. Stateless Server
The MCP server maintains no persistent state between tool calls. All session tracking uses the filesystem. This allows the server to be restarted without losing visibility into running sessions. Process state lives in the OS; job state lives in files.

## 12. Minimal Dependencies
The implementation uses the standard library and minimal external packages. FastAPI and aiohttp for remote workers, mcp for protocol. No heavy frameworks. This reduces attack surface and deployment complexity.
