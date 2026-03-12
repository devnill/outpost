# Architecture — Outpost

## 1. Component Map

### MCP Servers

| Server | Purpose | Tools | Key Dependencies |
|--------|---------|-------|------------------|
| session-spawner | Local session spawning | `spawn_session`, `poll_session` | Claude Code CLI, asyncio |
| remote-worker | HTTP daemon for remote jobs | (REST API, not MCP) | FastAPI, uvicorn |

### Agents

| Agent | Purpose | Tools | Spawned By |
|-------|---------|-------|------------|
| manager | Monitor workers, produce status reports | Read, Grep, Glob, Bash | brrr skill (ideate) |

### Role Definitions

| Role | Purpose | Allowed Tools |
|------|---------|---------------|
| worker | General-purpose execution | All tools |
| reviewer | Read-only code analysis | Read, Grep, Glob |
| manager | Coordination and monitoring | Read, Grep, Glob, Bash |
| proxy-human | Andon decision-making | Read, Grep, Glob, Bash |

---

## 2. Data Flow

### Local Session Spawning

```
Claude Code Session
       |
       | spawn_session(prompt, working_dir, ...)
       v
+------------------+
| session-spawner  |
| (MCP Server)     |
+------------------+
       |
       | subprocess.Popen(["claude", "--print", prompt])
       v
+------------------+
| Child Session    |
| (claude process) |
+------------------+
       |
       | writes to stdout
       v
Output captured, truncated, returned
```

### Remote Job Dispatch

```
Claude Code Session
       |
       | spawn_remote_session(prompt, worker_url, ...)
       v
+------------------+
| session-spawner  |
| (MCP Server)     |
+------------------+
       |
       | HTTP POST /jobs
       v
+------------------+
| remote-worker    |
| (FastAPI daemon) |
+------------------+
       |
       | subprocess.run(["claude", "--print", prompt])
       v
+------------------+
| Claude Process   |
| (on remote host) |
+------------------+
       |
       | git diff capture, output capture
       v
+------------------+
| Job Result       |
| (status, output, |
|  git_diff, error)|
+------------------+
       |
       | HTTP GET /jobs/{id}
       v
Result returned to caller
```

### Worker Pool Management

```
+------------------+
| Worker Registry  |
| (environment var)|
+------------------+
       |
       | OUTPOST_REMOTE_WORKERS=[{name, url, api_key}, ...]
       v
+------------------+
| list_remote_workers |
| (MCP Tool)       |
+------------------+
       |
       | HTTP GET /health (per worker)
       v
+------------------+
| Worker Health    |
| Report            |
+------------------+
```

---

## 3. Tool Definitions

### `spawn_session`

**Purpose**: Spawn a local Claude Code session as a subprocess.

**Input**:
- `prompt` (required): The prompt for the spawned session
- `working_dir` (required): Working directory for the session
- `model` (optional): Model override (default: sonnet)
- `role` (optional): Role definition name or inline role object
- `max_turns` (optional): Maximum turns (default: 30)
- `timeout` (optional): Timeout in seconds (default: 600)
- `permission_mode` (optional): Permission mode (default: acceptEdits)
- `allowed_tools` (optional): Restrict available tools

**Output**:
- `session_id`: Unique identifier for the session
- `status`: "running"
- `started_at`: ISO timestamp

**Enforcement**:
- Depth limit enforced via `OUTPOST_SPAWN_DEPTH` environment variable
- Prompt size limit: 100KB
- Concurrency limit via semaphore (default: 5)

### `poll_session`

**Purpose**: Check status and retrieve results from a spawned session.

**Input**:
- `session_id` (required): Session ID from spawn_session

**Output**:
- `status`: "running" | "completed" | "failed" | "timeout"
- `output`: Session output (truncated to max_output_bytes)
- `exit_code`: Process exit code (if completed)
- `duration_ms`: Execution duration in milliseconds
- `error`: Error message (if failed)

### `spawn_remote_session`

**Purpose**: Submit a job to a remote worker daemon.

**Input**:
- `prompt` (required): The prompt for the remote session
- `working_dir` (required): Working directory on the remote host
- `worker_url` (optional): Worker URL (uses first configured worker if not specified)
- `role` (optional): Role definition name
- `max_turns` (optional): Maximum turns (default: 30)
- `timeout` (optional): Timeout in seconds (default: 600)
- `permission_mode` (optional): Permission mode (default: acceptEdits)
- `allowed_tools` (optional): Restrict available tools

**Output**:
- `job_id`: Unique identifier for the job
- `worker_name`: Name of the assigned worker
- `status`: "queued"

### `poll_remote_job`

**Purpose**: Retrieve results from a remote job.

**Input**:
- `job_id` (required): Job ID from spawn_remote_session
- `worker_url` (optional): Worker URL (uses first configured worker if not specified)

**Output**:
- `status`: "queued" | "running" | "completed" | "failed" | "cancelled"
- `output`: Job output
- `git_diff`: Git diff from the job (if completed)
- `exit_code`: Process exit code
- `duration_ms`: Execution duration
- `error`: Error message (if failed)

### `list_remote_workers`

**Purpose**: Check health status of configured remote workers.

**Input**: None (uses `OUTPOST_REMOTE_WORKERS` environment variable)

**Output**:
- Array of worker status objects:
  - `name`: Worker name
  - `url`: Worker URL
  - `status`: "healthy" | "unhealthy" | "unreachable"
  - `active_jobs`: Number of running jobs
  - `queued_jobs`: Number of queued jobs
  - `max_concurrency`: Maximum concurrent jobs

---

## 4. Remote Worker API

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Worker health and load status |
| POST | `/jobs` | Submit a new job |
| GET | `/jobs` | List all jobs |
| GET | `/jobs/{job_id}` | Get job status and result |
| DELETE | `/jobs/{job_id}` | Cancel a queued job |

### Job States

| State | Description |
|-------|-------------|
| queued | Waiting for worker availability |
| running | Currently executing |
| completed | Finished successfully |
| failed | Finished with error |
| cancelled | Cancelled while queued |

### Authentication

All endpoints require `X-API-Key` header matching `IDEATE_WORKER_API_KEY` environment variable.

---

## 5. Role System

### Role Definition Format

```json
{
  "name": "worker",
  "description": "General-purpose worker agent",
  "system_prompt": "Optional system prompt override",
  "allowed_tools": ["Read", "Grep", "Glob", "Bash", "Write", "Edit"],
  "max_turns": 30,
  "permission_mode": "acceptEdits"
}
```

### Role Loading

1. Built-in roles loaded from `mcp/roles/default-roles.json`
2. Roles passed inline to `spawn_session` override loaded roles
3. Role name resolves to loaded role definition
4. Role constraints are applied to session parameters

---

## 6. Depth Tracking

### Mechanism

1. Server sets `OUTPOST_SPAWN_DEPTH=0` at root level (or reads from environment)
2. Server sets `OUTPOST_MAX_DEPTH` from configuration (default: 3)
3. `spawn_session` increments `OUTPOST_SPAWN_DEPTH` when spawning
4. Sessions at `depth >= max_depth` receive error if they try to spawn

### Enforcement

- Depth check happens before session creation
- Error returned: "Maximum spawn depth (N) exceeded"
- Prevents runaway recursion

---

## 7. Error Handling

### Local Session Errors

| Condition | Behavior |
|-----------|----------|
| Prompt too large | Return error, no spawn |
| Working directory invalid | Return error, no spawn |
| Timeout exceeded | SIGKILL process, return partial output |
| Process crash | Return exit code and stderr |
| Depth limit exceeded | Return error, no spawn |

### Remote Worker Errors

| Condition | Behavior |
|-----------|----------|
| API key missing | Return 401, reject request |
| Invalid API key | Return 401, reject request |
| Working directory outside base | Return 400, reject job |
| Prompt too large | Return 400, reject job |
| Worker unreachable | Return error to caller |

---

## 8. Configuration

### Environment Variables

| Variable | Component | Purpose | Default |
|----------|-----------|---------|---------|
| `OUTPOST_MAX_DEPTH` | session-spawner | Maximum recursion depth | 3 |
| `OUTPOST_CONCURRENCY` | session-spawner | Max concurrent sessions | 5 |
| `OUTPOST_TIMEOUT` | session-spawner | Default session timeout | 600 |
| `OUTPOST_SAFE_ROOT` | session-spawner | Restrict file access | None |
| `OUTPOST_REMOTE_WORKERS` | session-spawner | JSON array of worker configs | [] |
| `IDEATE_WORKER_API_KEY` | remote-worker | API key for authentication | Required |
| `IDEATE_WORKER_MAX_CONCURRENCY` | remote-worker | Max concurrent jobs | 3 |
| `IDEATE_WORKER_PORT` | remote-worker | Listen port | 7432 |
| `IDEATE_WORKER_BASE_DIR` | remote-worker | Restrict working directories | None |
