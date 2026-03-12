# outpost-remote-worker

HTTP daemon that runs on a remote machine, accepts Claude Code jobs via REST API, executes them using the local `claude` CLI, and exposes job status and results for polling.

Deploy one instance per machine you want to use as a remote worker. The local session-spawner MCP server submits jobs to configured workers via `spawn_remote_session`, polls for results via `poll_remote_job`, and checks worker health via `list_remote_workers`.

## Prerequisites

- Python 3.10+
- `claude` CLI installed and available on PATH
- `fastapi` and `uvicorn` Python packages

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
| `IDEATE_WORKER_BASE_DIR` | *(unset)* | When set, restricts `working_dir` in job requests to paths within this directory. Symlinks are resolved before comparison. |

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
  "max_concurrency": 3
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
| `role` | string | no | `"worker"` | Advisory role label recorded with the job. |
| `max_turns` | integer | no | `30` | Maximum agentic turns before termination. |
| `timeout` | integer | no | `600` | Job timeout in seconds. |
| `permission_mode` | string | no | `"acceptEdits"` | Claude permission mode: `acceptEdits` or `dontAsk`. |
| `allowed_tools` | string[] | no | — | Tool allowlist passed to `claude --allowedTools`. |

> **Note:** The `role` field is an observability label for remote dispatch. The remote worker daemon does not perform role resolution — tool restrictions, system prompt injection, and permission mode overrides defined in the role are not applied to the remote claude subprocess.

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

Cancel a queued job. Only jobs with status `queued` can be cancelled. Running, completed, or failed jobs cannot be cancelled.

```bash
curl -X DELETE -H "X-API-Key: your-secret-key" \
  http://worker-host:7432/jobs/550e8400-e29b-41d4-a716-446655440000
```

Response: HTTP 204 No Content on success.

Error responses:
- `404` — job ID not found
- `409` — job is not in `queued` status (already running, completed, failed, or cancelled)

---

## Job Lifecycle

Jobs progress through these states:

```
queued → running → completed
                 → failed
queued → cancelled  (via DELETE)
```

A job transitions to `failed` if the `claude` process exits with a non-zero code or if the timeout is exceeded.

## Notes

- The job store is in-memory. Jobs are lost if the server restarts.
- Worker coroutines are started at server startup based on `IDEATE_WORKER_MAX_CONCURRENCY`. The concurrency limit cannot be changed without restarting the server.
- The `claude` CLI must be authenticated on the worker machine. The worker runs `claude --print` in a subprocess using the machine's existing Claude credentials.