# Outpost

An MCP server for Claude Code that provides orchestration infrastructure for delegating work to separate Claude Code instances — either as local subprocesses or remote processes.

## Features

- **Local Session Spawning**: Create child Claude Code sessions for parallel work execution
- **Remote Dispatch**: Distribute jobs to remote worker daemons across machines
- **Session Management**: Lifecycle control and result collection for spawned sessions
- **Worker Pool**: Automatic load balancing across available remote workers

## Prerequisites

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and available on PATH

## Installation

Add the plugin directly from the repository:

```bash
claude plugin add /path/to/outpost
```

Or clone and add manually to your Claude Code plugin search path.

### MCP Server Setup

1. Install dependencies:

```bash
cd /path/to/outpost
pip install -r requirements.txt
```

2. Register the MCP server:

```bash
claude mcp add outpost -- python /path/to/outpost/mcp/server.py
```

## Usage

Once configured, Outpost provides the following MCP tools:

- `spawn_session` — Spawn a local Claude Code session with a prompt
- `poll_session` — Check status and retrieve results from a spawned session
- `spawn_remote_session` — Submit a job to a remote worker daemon
- `poll_remote_job` — Retrieve results from a remote job
- `list_remote_workers` — Inspect worker health and load

## Configuration

### Environment Variables

- `OUTPOST_REMOTE_WORKERS` — JSON array of worker configurations

```bash
export OUTPOST_REMOTE_WORKERS='[{"name":"gpu-box-1","url":"http://gpu-box-1:7432","api_key":"your-secret-key"}]'
```

## Architecture

Outpost is designed as a thin orchestration layer:

1. **MCP Server**: Handles tool requests from Claude Code sessions
2. **Session Manager**: Manages local subprocess lifecycle
3. **Remote Dispatcher**: Routes jobs to remote workers via REST API
4. **Worker Pool**: Tracks remote worker health and load

## Development

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=mcp
```

## License

MIT