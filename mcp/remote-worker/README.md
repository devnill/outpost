# outpost-remote-worker

HTTP daemon that runs on a remote machine, accepts Claude Code jobs via REST API, executes them using the local `claude` CLI, and exposes job status and results for polling.

Deploy one instance per machine you want to use as a remote worker. The local session-spawner MCP server submits jobs to configured workers via `spawn_remote_session`, polls for results via `poll_remote_job`, and checks worker health via `list_remote_workers`.

## Prerequisites

- Python 3.10+
- `claude` CLI installed and available on PATH
- `fastapi` and `uvicorn` Python packages
- Docker CE or Docker Engine (required only when `OUTPOST_AGENT_IMAGE` is set — see Container Mode below)

## Installation

```bash
cd mcp/remote-worker
pip install -e .
```

Or install dependencies directly:

```bash
pip install fastapi uvicorn
```

## Starting the Server

Set the required API key and start the daemon:

```bash
IDEATE_WORKER_API_KEY=your-secret-key python server.py
```

Or, if installed via `pip install -e .`, use the entry point:

```bash
IDEATE_WORKER_API_KEY=your-secret-key outpost-worker
```

The server listens on `0.0.0.0:7432` by default. All requests must include the `X-API-Key` header matching `IDEATE_WORKER_API_KEY`. If the key is not set, the server starts but rejects all requests.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IDEATE_WORKER_API_KEY` | *(unset)* | Required. API key for `X-API-Key` header authentication. All requests are rejected if not set. |
| `IDEATE_WORKER_HOST` | `0.0.0.0` | Host address to bind to. |
| `IDEATE_WORKER_PORT` | `7432` | Port to listen on. |
| `IDEATE_WORKER_MAX_CONCURRENCY` | `3` | Maximum number of jobs executed simultaneously. Additional jobs queue and wait. |
| `IDEATE_WORKER_MAX_JOBS` | `1000` | Maximum number of jobs to retain in the in-memory store. Terminal jobs are evicted oldest-first when the limit is exceeded. |
| `IDEATE_WORKER_BASE_DIR` | *(unset)* | When set, restricts `working_dir` in job requests to paths within this directory. Symlinks are resolved before comparison. |
| `OUTPOST_AGENT_IMAGE` | *(unset)* | Docker image to use for job containers. When set, each job runs inside an ephemeral Docker container rather than a bare subprocess. Empty string (default) disables container mode. |
| `OUTPOST_CONTAINER_RUNTIME` | *(unset)* | Container runtime override. Set to `runsc` to use gVisor for an additional kernel isolation boundary. Empty string uses the default Docker runtime. |
| `OUTPOST_CONTAINER_MEMORY` | `4g` | Memory limit for job containers. Passed as `--memory` and `--memory-swap` to `docker run`. |
| `OUTPOST_CONTAINER_CPUS` | `2` | CPU limit for job containers. Passed as `--cpus` to `docker run`. |

## Container Mode

When `OUTPOST_AGENT_IMAGE` is set, each job runs inside an ephemeral Docker container rather than a bare subprocess. The container provides isolation between the agent's execution environment and the host machine.

To enable container mode, build the provided agent image and set the env var:

```bash
docker build -t outpost-agent:latest mcp/remote-worker/
OUTPOST_AGENT_IMAGE=outpost-agent:latest IDEATE_WORKER_API_KEY=your-key outpost-worker
```

**ANTHROPIC_API_KEY**: The worker passes `ANTHROPIC_API_KEY` from its own environment into each container. You must set `ANTHROPIC_API_KEY` in the worker process environment before starting the server:

```bash
export ANTHROPIC_API_KEY=your-anthropic-key
OUTPOST_AGENT_IMAGE=outpost-agent:latest IDEATE_WORKER_API_KEY=your-key outpost-worker
```

If `ANTHROPIC_API_KEY` is not set and container mode is active, the worker will reject job submissions with HTTP 500.

**Security flags applied to each container**:
- `--cap-drop ALL` — no Linux capabilities
- `--security-opt no-new-privileges` — prevents setuid/setgid escalation
- `--user 1000:1000` — runs as non-root uid 1000
- `--pids-limit 512` — prevents fork bombs
- `--rm` — container removed automatically on exit

When container mode is not set (`OUTPOST_AGENT_IMAGE` is empty), the worker behaves exactly as before — spawning `claude` as a direct subprocess.

## API Reference

All endpoints require the header `X-API-Key: <your-key>`.

---

### GET /health

Returns server status and current load. Use this to check whether a worker is reachable and how many jobs are running.

```bash
curl -H "X-API-Key: your-secret-key" http://worker-host:7432/health
```

Response:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "active_jobs": 1,
  "queued_jobs": 0,
  "max_concurrency": 3,
  "max_jobs": 1000
}
```

---

### POST /jobs

Submit a new job. Returns immediately with a `job_id` — does not wait for the job to complete. Poll `GET /jobs/{job_id}` to retrieve results.

```bash
curl -X POST http://worker-host:7432/jobs \
  -H "X-API-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Add a hello world function to main.py",
    "working_dir": "/home/user/myproject",
    "role": "worker",
    "max_turns": 30,
    "timeout": 600,
    "permission_mode": "acceptEdits"
  }'
```

Request body fields:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `prompt` | string | yes | — | Prompt sent to `claude --print`. Maximum 100KB. |
| `working_dir` | string | yes | — | Working directory for the `claude` subprocess. Must exist on the worker machine. |
| `role` | string | no | `"worker"` | Role name as received; resolved by session-spawner before submission. Stored with the job for reference. |
| `max_turns` | integer | no | `30` | Maximum agentic turns before termination. |
| `timeout` | integer | no | `600` | Job timeout in seconds. |
| `permission_mode` | string | no | `"acceptEdits"` | Claude permission mode: `acceptEdits` or `dontAsk`. |
| `allowed_tools` | string[] | no | — | Tool allowlist passed to `claude --allowedTools`. |

> **Note:** The `role` field is resolved by the session-spawner before the job is submitted. The resolved `allowed_tools`, `permission_mode`, `max_turns`, and `system_prompt` are propagated as explicit job parameters to the remote worker.

Response (HTTP 201):

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued"
}
```

Error responses:
- `400` — prompt exceeds 100KB, or `working_dir` does not exist, or `working_dir` is outside `IDEATE_WORKER_BASE_DIR`
- `401` — missing or invalid API key

---

### GET /jobs

List all jobs in the server's in-memory store. Returns a summary for each job.

```bash
curl -H "X-API-Key: your-secret-key" http://worker-host:7432/jobs
```

Response:

```json
[
  {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "completed",
    "role": "worker",
    "created_at": "2026-03-11T14:23:01.123Z",
    "duration_ms": 12500
  },
  {
    "job_id": "661f9511-f3ac-52e5-b827-557766551111",
    "status": "running",
    "role": "worker",
    "created_at": "2026-03-11T14:24:10.000Z"
  }
]
```

`duration_ms` is included only for completed or failed jobs.

---

### GET /jobs/{job_id}

Retrieve the full status and result of a specific job.

```bash
curl -H "X-API-Key: your-secret-key" \
  http://worker-host:7432/jobs/550e8400-e29b-41d4-a716-446655440000
```

Response when queued:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "created_at": "2026-03-11T14:23:01.123Z"
}
```

Response when running:

```json
{
  "job_id": "a1b2c3d4-...",
  "status": "running",
  "started_at": "2026-03-11T14:23:02.000Z"
}
```

Response when completed or failed:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "output": "...",
  "exit_code": 0,
  "git_diff": "diff --git a/main.py ...",
  "duration_ms": 12500,
  "error": null,
  "created_at": "2026-03-11T14:23:01.123Z",
  "started_at": "2026-03-11T14:23:02.000Z",
  "completed_at": "2026-03-11T14:23:14.500Z"
}
```

`git_diff` contains the output of `git diff HEAD` in the job's `working_dir`. It is `null` if the directory is not a git repository or if the diff command fails. `error` is `null` on success and contains a description on failure or timeout.

Error responses:
- `404` — job ID not found

---

### DELETE /jobs/{job_id}

Cancel a queued or running job. Jobs with status `queued` or `running` can be cancelled.

```bash
curl -X DELETE -H "X-API-Key: your-secret-key" \
  http://worker-host:7432/jobs/550e8400-e29b-41d4-a716-446655440000
```

Response: HTTP 204 No Content on success.

Error responses:
- `404` — job ID not found
- `409` — job is in a non-cancellable state (already completed, failed, or cancelled)

---

## Job Lifecycle

Jobs progress through these states:

```
queued → running → completed
                 → failed
                 → cancelled  (via DELETE)
queued → cancelled  (via DELETE)
```

A job transitions to `failed` if the `claude` process exits with a non-zero code or if the timeout is exceeded.

## Notes

- The job store is in-memory. Jobs are lost if the server restarts.
- Worker coroutines are started at server startup based on `IDEATE_WORKER_MAX_CONCURRENCY`. The concurrency limit cannot be changed without restarting the server.
- The `claude` CLI must be authenticated on the worker machine. The worker runs `claude --print` in a subprocess using the machine's existing Claude credentials.