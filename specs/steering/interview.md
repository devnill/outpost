# Planning Interview — Outpost

## Session 1 — 2026-03-11

### Q: What is outpost?

**A:** Outpost is an MCP server for Claude Code that provides orchestration infrastructure for delegating work to separate Claude Code instances. It enables two dispatch modes: local session spawning (subprocess) and remote dispatch (HTTP API to worker daemons). The project was extracted from ideate as a separate concern.

### Q: Why was outpost extracted from ideate?

**A:** Ideate's core purpose is SDLC workflow (planning, execution, review). Session orchestration and remote dispatch are infrastructure concerns that have their own design decisions, constraints, and evolution path. Separating them allows ideate to remain focused on SDLC while outpost can specialize in MCP orchestration patterns.

### Q: What problem does outpost solve?

**A:** Claude Code does not support subagents spawning their own subagents. Outpost fills this gap by providing MCP tools that allow a parent Claude Code session to spawn child sessions for parallel work execution. It also enables remote dispatch to worker daemons running on other machines, which is useful for GPU-intensive work or distributed processing.

### Q: Who is the primary user of outpost?

**A:** Developers and teams using Claude Code for large projects that benefit from parallel execution. Users who need to dispatch work to multiple machines. Users running autonomous execution loops (brrr skill) that need worker management and job monitoring.

### Q: What are the core components?

**A:**
- **session-spawner**: MCP server for local session spawning via `claude --print`
- **remote-worker**: FastAPI HTTP service that accepts jobs and runs them locally
- **roles system**: JSON-based role definitions for constraining session capabilities
- **manager agent**: Claude Code agent that monitors worker status and produces reports

### Q: What are the key design decisions?

**A:**
1. **Filesystem state**: All session tracking uses files, not in-memory state
2. **Depth limiting**: Recursive spawning is bounded to prevent runaway recursion
3. **Timeout enforcement**: Every session has a timeout; hung sessions are killed
4. **Role-based permissions**: Sessions can be assigned roles that limit tool access
5. **Output truncation**: Large outputs are truncated to prevent context overflow
6. **Graceful degradation**: Worker failures don't crash the orchestrator

### Q: What are the security considerations?

**A:**
- Remote workers require API key authentication
- Safe root enforcement can restrict session file access to a directory tree
- Sessions inherit the parent's permissions by default but can be constrained via roles
- No anonymous access to remote workers

### Q: What is out of scope?

**A:**
- Multi-tenant isolation (run separate worker instances instead)
- Persistent job queues (use external orchestration)
- Work execution (outpost orchestrates; it does not do the work)
- Web UI or dashboard (observability via manager agent reports)

### Q: How should outpost evolve?

**A:**
Potential future directions:
- Session result caching for faster re-dispatch
- Priority queue support for job scheduling
- Worker pool auto-scaling based on queue depth
- WebSocket transport as an alternative to HTTP
- Integration with cloud provider APIs for worker provisioning

These are not currently planned; they represent potential directions based on user feedback.

---

## Completion

Interview completed. Guiding principles, constraints, and architecture derived from this session.
