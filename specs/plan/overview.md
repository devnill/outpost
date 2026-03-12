# Project Overview — Outpost

## Summary

Outpost is an MCP server for Claude Code that provides orchestration infrastructure for delegating work to separate Claude Code instances. It enables parallel execution through local session spawning and distributed execution through remote worker dispatch.

## Purpose

Claude Code does not support subagents spawning their own subagents. Outpost fills this gap by providing MCP tools that allow a parent session to:

1. **Spawn local sessions** — Create child Claude Code processes for parallel work execution
2. **Dispatch remote jobs** — Submit work to remote worker daemons via HTTP API
3. **Manage session lifecycle** — Control running sessions and collect results
4. **Monitor worker health** — Track remote worker status and job progress

## Core Value

- **Parallelism**: Execute multiple work items concurrently
- **Distribution**: Dispatch work to remote machines for GPU-intensive tasks
- **Isolation**: Each session runs in its own context with its own working directory
- **Observability**: Manager agent provides structured status reports

## Key Components

| Component | Purpose |
|-----------|---------|
| session-spawner | MCP server for local subprocess spawning |
| remote-worker | FastAPI daemon for remote job execution |
| roles system | JSON-based capability constraints |
| manager agent | Status monitoring and reporting |

## Users

- Developers running large projects that benefit from parallel execution
- Teams distributing work across multiple machines
- Autonomous execution systems (e.g., brrr skill) requiring worker management

## Relationship to Ideate

Outpost was extracted from ideate as a separate concern. Ideate handles SDLC workflow (planning, execution, review). Outpost handles MCP orchestration (session management, remote dispatch). They are complementary projects that can be used together or independently.

## Success Metrics

- Sessions spawn reliably and complete within timeout
- Remote workers accept jobs and return results
- Manager agent produces accurate status reports
- Error conditions are captured and reported
- Resource limits are enforced without crashes
