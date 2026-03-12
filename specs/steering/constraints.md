# Constraints

## Technology Constraints

1. **MCP Protocol Compliance.** The server must implement the Model Context Protocol specification. Tool schemas must match expected input/output types. Error responses must use proper MCP error types. Async tool execution must follow MCP conventions.

2. **Claude Code CLI Dependency.** Session spawning requires the Claude Code CLI (`claude`) to be installed and available on PATH. There is no fallback. The system cannot spawn sessions without this binary.

3. **Python 3.10+.** The implementation uses Python 3.10+ features (type hints, match statements, async context managers). Earlier Python versions are not supported.

4. **Filesystem-Based State.** All state management uses the filesystem. No databases, no in-memory session stores, no external state services. This is a hard constraint for simplicity and recoverability.

5. **HTTP Transport for Remote Workers.** Remote dispatch uses HTTP/REST, not gRPC or WebSocket. This is a deliberate constraint for simplicity and broad compatibility. Workers expose a simple REST API.

## Design Constraints

6. **No Shared Working Directory.** Each session has its own working directory. The parent session's working directory is passed by path, not shared. Sessions cannot write to the parent's workspace.

7. **Output Size Limits.** Large outputs are truncated. The default limit (50KB) prevents overwhelming the parent session's context. Users can increase the limit but cannot disable truncation entirely.

8. **Prompt Size Limits.** Prompts exceeding 100KB are rejected. This protects against context overflow and ensures spawned sessions receive usable prompts.

9. **Depth Enforcement.** Maximum recursion depth (default 3) is enforced server-side. Clients cannot override this limit. Sessions at max depth cannot spawn further sessions.

10. **Role Definitions Are Static.** Roles are defined in JSON files loaded at server startup. There is no API for dynamic role creation. This is intentional for security and simplicity.

## Process Constraints

11. **Concurrent Session Limit.** A semaphore limits concurrent local sessions (default 5). This prevents resource exhaustion. Remote workers have their own concurrency limits configured independently.

12. **Timeout Is Mandatory.** Every session must have a timeout. The default (600 seconds) protects against hung sessions. Sessions that exceed timeout are terminated via SIGKILL.

13. **Safe Root Enforcement.** When `OUTPOST_SAFE_ROOT` is configured, sessions can only operate within that directory tree. This is a security constraint for untrusted prompts.

14. **API Key Required for Remote.** Remote workers require an API key for authentication. There is no anonymous access mode. Workers without an API key configured reject all requests.

## Scope Constraints

15. **Orchestration Only.** Outpost does not execute work itself. It spawns sessions that execute work. The server is infrastructure, not a participant in the work.

16. **No Built-In Queue Persistence.** Jobs are queued in memory. A server restart clears the queue. For persistent job queues, use an external orchestration layer. This is a deliberate scope boundary.

17. **Single-User Assumption.** The remote worker daemon assumes a single trusted user. Multi-tenant isolation is out of scope. For multi-user scenarios, run separate worker instances with separate API keys.

## Integration Constraints

18. **Git Required for Diff Capture.** The `git_diff` feature in remote workers requires the job workspace to be a git repository. Non-git workspaces return null for git_diff. This is documented, not enforced.

19. **Environment Variable Configuration.** All configuration uses environment variables. No config files, no command-line flags for the MCP server. This matches Claude Code's plugin model.
