# Execution Strategy — Outpost

## Mode
Sequential

## Parallelism
Max concurrent agents: 1 (outpost is infrastructure, not typically run as parallel work items)

## Worktrees
Enabled: no
Reason: Outpost is an MCP server project. Development work items modify distinct files.

## Review Cadence
After each work item.

## Current State

Outpost is complete for its initial scope. The following components are implemented and tested:

- session-spawner MCP server with spawn_session and poll_session tools
- remote-worker FastAPI daemon with REST API for job submission
- Role system with default roles (worker, reviewer, manager, proxy-human)
- Manager agent for worker status monitoring

## Future Work Items

Work items will be numbered sequentially starting from 001 when new features are planned. The work-items directory is empty as of this writing, indicating no pending work items.

## Dependency Graph

No active dependencies. All components are independent and operational.

## Agent Configuration
Model for development: sonnet
Model for review: sonnet
Permission mode: acceptEdits
