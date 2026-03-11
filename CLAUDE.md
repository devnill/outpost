# Outpost

Outpost is an MCP server for Claude Code that enables orchestration of work across separate Claude Code instances — either as local subprocesses or remote processes. It provides the infrastructure for parallel execution, session management, and remote dispatch.

## Purpose

Outpost serves as the orchestration layer for distributed Claude Code workflows. It allows a parent session to:
- Spawn local child sessions for parallel work item execution
- Dispatch jobs to remote worker daemons for distributed processing
- Manage session lifecycle and result collection

## Development Setup

### Prerequisites

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and available on PATH

### Installation

```bash
cd /path/to/outpost
pip install -r requirements.txt
```

### Running Tests

```bash
cd /path/to/outpost
pytest
```

For verbose output:

```bash
pytest -v
```

## Artifact Directory Structure

All planning and review artifacts are stored in the `specs/` directory:

```
specs/
├── steering/      # Research, interview notes, guiding principles
├── plan/         # Architecture, work items, execution strategy
│   └── work-items/
├── reviews/      # Incremental and final review artifacts
│   ├── incremental/
│   └── final/
└── journal.md    # Running log of execution progress
```

## MCP Server Setup

### Register the MCP server

```bash
claude mcp add outpost -- python /path/to/outpost/mcp/server.py
```

See the README.md for detailed configuration options and environment variables.

## License

MIT