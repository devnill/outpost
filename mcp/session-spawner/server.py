"""
outpost-session-spawner: MCP server that enables recursive Claude Code session invocation.

Exposes a `spawn_session` tool that runs `claude --print` as a subprocess,
allowing Claude to invoke new Claude Code sessions for recursive decomposition
and execution of large projects.

Safety mechanisms:
- Depth tracking via OUTPOST_SPAWN_DEPTH environment variable
- Server-side max_depth enforcement via OUTPOST_MAX_DEPTH environment variable
- Concurrency limiting via asyncio semaphore
- Per-session timeout enforcement
- Output truncation for large responses
- Prompt length validation (100KB limit)
- Optional safe root directory enforcement via OUTPOST_SAFE_ROOT
"""

import asyncio
import datetime
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import aiohttp

from mcp.server import Server
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, TextContent, Tool

logger = logging.getLogger(__name__)

# Path to built-in default roles file
_BUILTIN_ROLES_FILE = Path(__file__).parent.parent / "roles" / "default-roles.json"

# Configuration defaults
DEFAULT_MAX_DEPTH = 3
DEFAULT_CONCURRENCY = 5
DEFAULT_TIMEOUT = 600
DEFAULT_MAX_OUTPUT_BYTES = 50_000
DEFAULT_PERMISSION_MODE = "acceptEdits"
DEFAULT_MAX_TURNS = 30
DEFAULT_OUTPUT_FORMAT = "json"
MAX_PROMPT_BYTES = 100_000

server = Server("outpost-session-spawner", version="0.4.0")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="spawn_session",
            description=(
                "Spawn a new Claude Code session as a subprocess. "
                "Enables recursive self-invocation for decomposition and execution of large projects. "
                "The spawned session runs `claude --print` with the provided prompt and returns its output."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The prompt for the spawned Claude Code session.",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Working directory for the spawned session.",
                    },
                    "max_turns": {
                        "type": "integer",
                        "description": f"Maximum agentic turns before the session terminates. Default: {DEFAULT_MAX_TURNS}.",
                        "default": DEFAULT_MAX_TURNS,
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": f"Maximum recursive spawn depth. Prevents fork bombs. Default: {DEFAULT_MAX_DEPTH}.",
                        "default": DEFAULT_MAX_DEPTH,
                    },
                    "timeout": {
                        "type": "integer",
                        "description": f"Per-session timeout in seconds. Default: {DEFAULT_TIMEOUT}.",
                        "default": DEFAULT_TIMEOUT,
                    },
                    "permission_mode": {
                        "type": "string",
                        "description": f"Permission mode for the spawned session. Default: '{DEFAULT_PERMISSION_MODE}'.",
                        "enum": ["acceptEdits", "dontAsk"],
                        "default": DEFAULT_PERMISSION_MODE,
                    },
                    "allowed_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tool allowlist for the spawned session.",
                    },
                    "output_format": {
                        "type": "string",
                        "description": f"Output format for the spawned session. Default: '{DEFAULT_OUTPUT_FORMAT}'.",
                        "enum": ["json", "text", "stream-json"],
                        "default": DEFAULT_OUTPUT_FORMAT,
                    },
                    "team_name": {
                        "type": "string",
                        "description": "Advisory team name for the spawned session. Logged and propagated via OUTPOST_TEAM_NAME env var.",
                    },
                    "exec_instructions": {
                        "type": "string",
                        "description": (
                            "Execution instructions prepended to the spawned session's prompt. "
                            "Overrides OUTPOST_EXEC_INSTRUCTIONS env var for this call and its children."
                        ),
                    },
                    "role": {
                        "type": "string",
                        "description": (
                            "Optional role name to apply to the spawned session. "
                            "Roles are defined in default-roles.json or the user's roles file. "
                            "Built-in roles: 'worker' (no restrictions), "
                            "'reviewer' (read-only: Read, Grep, Glob), "
                            "'manager' (Read, Grep, Glob, Bash with coordination prompt). "
                            "Role system_prompt is prepended to the prompt. "
                            "Role allowed_tools apply unless caller provides explicit allowed_tools (caller wins). "
                            "Role model, max_turns, and permission_mode apply unless caller provides explicit values (caller wins)."
                        ),
                    },
                    "model": {
                        "type": "string",
                        "description": (
                            "Claude model to use for the spawned session "
                            "(e.g. 'claude-opus-4-6', 'claude-sonnet-4-6'). "
                            "If omitted, the subprocess uses its configured default."
                        ),
                    },
                },
                "required": ["prompt", "working_dir"],
            },
        ),
        Tool(
            name="spawn_remote_session",
            description=(
                "Submit a job to a configured remote worker daemon and return immediately with a job_id. "
                "Non-blocking: does not wait for the job to complete. "
                "Use poll_remote_job to check status and retrieve results. "
                "Remote workers are configured via the OUTPOST_REMOTE_WORKERS environment variable."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The prompt for the remote Claude Code session.",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Working directory for the remote session.",
                    },
                    "worker_name": {
                        "type": "string",
                        "description": (
                            "Name of the target worker (must match a name in OUTPOST_REMOTE_WORKERS). "
                            "If omitted, the least-loaded worker is selected automatically via a live "
                            "GET /health call to each configured worker."
                        ),
                    },
                    "role": {
                        "type": "string",
                        "description": "Optional role name to pass to the remote worker.",
                    },
                    "max_turns": {
                        "type": "integer",
                        "description": f"Maximum agentic turns for the remote session. Default: {DEFAULT_MAX_TURNS}.",
                        "default": DEFAULT_MAX_TURNS,
                    },
                    "timeout": {
                        "type": "integer",
                        "description": f"Per-session timeout in seconds on the remote worker. Default: {DEFAULT_TIMEOUT}.",
                        "default": DEFAULT_TIMEOUT,
                    },
                    "allowed_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tool allowlist for the remote session.",
                    },
                    "permission_mode": {
                        "type": "string",
                        "description": f"Permission mode for the remote session. Default: '{DEFAULT_PERMISSION_MODE}'.",
                        "enum": ["acceptEdits", "dontAsk"],
                        "default": DEFAULT_PERMISSION_MODE,
                    },
                },
                "required": ["prompt", "working_dir"],
            },
        ),
        Tool(
            name="poll_remote_job",
            description=(
                "Poll the status and result of a previously submitted remote job. "
                "Returns status (queued, running, completed, failed, cancelled) and, "
                "when complete, the output, git_diff, exit_code, and duration."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The job ID returned by spawn_remote_session.",
                    },
                    "worker_name": {
                        "type": "string",
                        "description": (
                            "Name of the worker that owns this job. "
                            "Required when multiple workers are configured and the job_id alone "
                            "is insufficient to locate the job. If omitted, all configured workers "
                            "are tried in config order until the job is found."
                        ),
                    },
                },
                "required": ["job_id"],
            },
        ),
        Tool(
            name="list_remote_workers",
            description=(
                "Return the list of configured remote workers with live health data. "
                "Makes a GET /health request to each worker concurrently to determine status "
                "and current load (active_jobs, queued_jobs, max_concurrency). "
                "Worker status values: 'ok', 'unreachable', 'auth_error'."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "spawn_remote_session":
        return await _handle_spawn_remote_session(arguments)
    if name == "poll_remote_job":
        return await _handle_poll_remote_job(arguments)
    if name == "list_remote_workers":
        return await _handle_list_remote_workers(arguments)
    # Fix 6: Unknown tool error — raise MCP protocol error instead of returning TextContent
    if name != "spawn_session":
        raise McpError(ErrorData(code=-32601, message=f"Unknown tool: {name}"))

    prompt = arguments["prompt"]
    working_dir = arguments["working_dir"]
    max_turns = arguments.get("max_turns", DEFAULT_MAX_TURNS)
    caller_max_depth = arguments.get("max_depth", DEFAULT_MAX_DEPTH)
    timeout = arguments.get("timeout", DEFAULT_TIMEOUT)
    permission_mode = arguments.get("permission_mode", DEFAULT_PERMISSION_MODE)
    allowed_tools = arguments.get("allowed_tools")
    output_format = arguments.get("output_format", DEFAULT_OUTPUT_FORMAT)
    team_name = arguments.get("team_name")
    exec_instructions = arguments.get("exec_instructions") or os.environ.get("OUTPOST_EXEC_INSTRUCTIONS", "")
    role_name = arguments.get("role")
    model = arguments.get("model")

    # Role resolution — apply role defaults before caller-explicit values take precedence

    if role_name is not None:
        if role_name not in _roles:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "output": "",
                            "exit_code": 1,
                            "session_id": "",
                            "duration_ms": 0,
                            "error": (
                                f"Unknown role: '{role_name}'. "
                                f"Available roles: {sorted(_roles.keys())}."
                            ),
                        }
                    ),
                )
            ]
        role = _roles[role_name]

        # system_prompt: prepend to the prompt
        role_system_prompt = role.get("system_prompt")
        if role_system_prompt:
            prompt = f"[ROLE: {role_name}]\n{role_system_prompt}\n\n{prompt}"

        # allowed_tools: role default, caller wins if explicitly provided
        if "allowed_tools" not in arguments and role.get("allowed_tools"):
            allowed_tools = role["allowed_tools"]

        # model: role default, caller wins if explicitly provided
        if "model" not in arguments and role.get("model"):
            model = role["model"]

        # max_turns: role default, caller wins if explicitly provided
        if "max_turns" not in arguments and role.get("max_turns") is not None:
            max_turns = role["max_turns"]

        # permission_mode: role default, caller wins if explicitly provided
        if "permission_mode" not in arguments and role.get("permission_mode"):
            permission_mode = role["permission_mode"]

    # Capture original prompt byte length before any injection (role system_prompt or exec_instructions)
    original_prompt_bytes = len(arguments["prompt"].encode("utf-8"))

    # Fix 4: Prompt length validation — reject prompts exceeding 100KB
    # Validation applies to original prompt only; injected instructions do not count toward limit.
    if original_prompt_bytes > MAX_PROMPT_BYTES:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "output": "",
                        "exit_code": 1,
                        "session_id": "",
                        "duration_ms": 0,
                        "error": (
                            f"Prompt too large: {original_prompt_bytes} bytes exceeds "
                            f"the {MAX_PROMPT_BYTES} byte limit. "
                            "Reduce the prompt size before retrying."
                        ),
                    }
                ),
            )
        ]

    # Validate working directory exists
    resolved_working_dir = Path(working_dir).resolve()
    if not resolved_working_dir.is_dir():
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "output": "",
                        "exit_code": 1,
                        "session_id": "",
                        "duration_ms": 0,
                        "error": f"Working directory does not exist: {working_dir}",
                    }
                ),
            )
        ]

    # Fix 5: working_dir safe root — validate against OUTPOST_SAFE_ROOT if set
    safe_root = os.environ.get("OUTPOST_SAFE_ROOT")
    if safe_root:
        safe_root_resolved = Path(safe_root).resolve()
        if not resolved_working_dir.is_relative_to(safe_root_resolved):
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "output": "",
                            "exit_code": 1,
                            "session_id": "",
                            "duration_ms": 0,
                            "error": (
                                f"Working directory {working_dir} is outside the safe root "
                                f"{safe_root}. Set OUTPOST_SAFE_ROOT to allow this directory, "
                                "or use a directory within the safe root."
                            ),
                        }
                    ),
                )
            ]

    # Fix 1: max_depth server-side enforcement — callers can lower but not raise the limit
    max_depth = min(caller_max_depth, _server_max_depth)

    # Check recursive depth
    current_depth = int(os.environ.get("OUTPOST_SPAWN_DEPTH", "0"))
    if current_depth >= max_depth:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "output": "",
                        "exit_code": 1,
                        "session_id": "",
                        "duration_ms": 0,
                        "error": (
                            f"Maximum recursive depth reached: current={current_depth}, "
                            f"max={max_depth}. Refusing to spawn to prevent fork bomb."
                        ),
                    }
                ),
            )
        ]

    # Build effective prompt — prepend execution instructions if present
    effective_prompt = prompt
    if exec_instructions:
        effective_prompt = (
            f"[EXECUTION INSTRUCTIONS]\n{exec_instructions}\n[END EXECUTION INSTRUCTIONS]\n\n{prompt}"
        )

    # Build the command
    cmd = [
        "claude",
        "--print",
        "--output-format",
        output_format,
        "--permission-mode",
        permission_mode,
        "--max-turns",
        str(max_turns),
        "--cwd",
        working_dir,
        effective_prompt,
    ]

    if allowed_tools:
        cmd.extend(["--allowedTools", ",".join(allowed_tools)])

    if model:
        cmd.extend(["--model", model])

    # Build environment with incremented depth.
    # OUTPOST_TEAM_NAME is explicitly removed then conditionally re-set so it does not
    # leak from grandparent sessions when the direct caller omits team_name.
    env = {**os.environ, "OUTPOST_SPAWN_DEPTH": str(current_depth + 1)}
    env.pop("OUTPOST_TEAM_NAME", None)
    if team_name:
        env["OUTPOST_TEAM_NAME"] = team_name
    if exec_instructions:
        env["OUTPOST_EXEC_INSTRUCTIONS"] = exec_instructions

    # Execute with concurrency limiting
    start_time = time.monotonic()
    timed_out = False
    result = None
    partial_stdout = ""
    partial_stderr = ""
    try:
        async with _semaphore:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=working_dir,
            )
    except subprocess.TimeoutExpired as e:
        # Fix 2: TimeoutExpired "None" fix — e.stdout/e.stderr may be None or bytes
        # With text=True, they could be str or None. With capture_output, they are
        # typically None on TimeoutExpired. Handle both bytes and str cases safely.
        timed_out = True
        if isinstance(e.stdout, bytes):
            partial_stdout = e.stdout.decode("utf-8", errors="ignore")
        else:
            partial_stdout = e.stdout or ""
        if isinstance(e.stderr, bytes):
            partial_stderr = e.stderr.decode("utf-8", errors="ignore")
        else:
            partial_stderr = e.stderr or ""

    duration_ms = int((time.monotonic() - start_time) * 1000)

    # Determine outcome fields shared by both paths
    if timed_out:
        outcome_session_id = ""
        outcome_exit_code = -1
        outcome_success = False
        outcome_token_usage = None
    else:
        # Handle output truncation (truncate by bytes, not characters)
        stdout = result.stdout
        output_truncated = False
        overflow_path = None

        stdout_bytes = stdout.encode("utf-8")
        if len(stdout_bytes) > DEFAULT_MAX_OUTPUT_BYTES:
            output_truncated = True
            with tempfile.NamedTemporaryFile(
                mode="w",
                prefix="outpost-session-",
                suffix=".txt",
                dir=working_dir,
                delete=False,
            ) as f:
                f.write(stdout)
                overflow_path = f.name
            stdout = stdout_bytes[:DEFAULT_MAX_OUTPUT_BYTES].decode("utf-8", errors="ignore")

        # Parse session ID and token usage from JSON output if available
        outcome_session_id = ""
        outcome_token_usage = None
        if output_format == "json":
            try:
                parsed = json.loads(result.stdout)
                if isinstance(parsed, dict):
                    outcome_session_id = parsed.get("session_id", "")
                    usage = parsed.get("usage") or parsed.get("token_usage")
                    if isinstance(usage, dict):
                        outcome_token_usage = usage
                    elif (
                        "input_tokens" in parsed and "output_tokens" in parsed
                    ):
                        outcome_token_usage = {
                            k: parsed[k]
                            for k in ("input_tokens", "output_tokens", "total_tokens")
                            if k in parsed
                        }
            except (json.JSONDecodeError, TypeError):
                pass

        outcome_exit_code = result.returncode
        outcome_success = result.returncode == 0

    # Shared post-processing: registry, logging, status table
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "session_id": outcome_session_id,
        "depth": current_depth + 1,
        "working_dir": str(resolved_working_dir),
        "prompt_bytes": original_prompt_bytes,
        "team_name": team_name or None,
        "used_team": bool(team_name),
        "duration_ms": duration_ms,
        "exit_code": outcome_exit_code,
        "success": outcome_success,
        "timed_out": timed_out,
        "token_usage": outcome_token_usage,
    }
    _session_registry.append(entry)
    _log_entry(entry)
    _print_status_table()

    if timed_out:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "output": partial_stdout[:DEFAULT_MAX_OUTPUT_BYTES],
                        "exit_code": -1,
                        "session_id": "",
                        "duration_ms": duration_ms,
                        "error": (
                            f"Session timed out after {timeout}s. "
                            f"Partial stderr: {partial_stderr[:1000]}"
                        ),
                        "timed_out": True,
                        "token_usage": None,
                    }
                ),
            )
        ]

    response = {
        "output": stdout,
        "exit_code": result.returncode,
        "session_id": outcome_session_id,
        "duration_ms": duration_ms,
        "error": result.stderr if result.returncode != 0 else None,
    }

    if outcome_token_usage is not None:
        response["token_usage"] = outcome_token_usage

    if output_truncated:
        response["output_truncated"] = True
        response["full_output_path"] = overflow_path
        response["output"] = (
            f"[Output truncated to {DEFAULT_MAX_OUTPUT_BYTES} bytes. "
            f"Full output saved to: {overflow_path}]\n\n" + stdout
        )

    return [TextContent(type="text", text=json.dumps(response))]


def _no_workers_error(tool_name: str) -> list[TextContent]:
    """Return a structured error when no remote workers are configured."""
    return [
        TextContent(
            type="text",
            text=json.dumps(
                {
                    "error": (
                        f"No remote workers configured. "
                        f"Set OUTPOST_REMOTE_WORKERS to a JSON array of "
                        f'[{{"name": string, "url": string, "api_key": string}}] to use {tool_name}.'
                    )
                }
            ),
        )
    ]


def _get_http_session() -> aiohttp.ClientSession:
    """Return the shared aiohttp ClientSession, creating one lazily if main() was not called."""
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session


async def _fetch_worker_health(worker: dict) -> dict:
    """Fetch GET /health for a single worker. Returns health dict with added 'name' and 'status' fields."""
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with _get_http_session().get(
            f"{worker['url'].rstrip('/')}/health",
            headers={"X-API-Key": worker.get("api_key", "")},
            timeout=timeout,
        ) as resp:
            if resp.status == 401 or resp.status == 403:
                return {
                    "name": worker["name"],
                    "url": worker["url"],
                    "status": "auth_error",
                    "active_jobs": None,
                    "queued_jobs": None,
                    "max_concurrency": None,
                }
            if resp.status != 200:
                return {
                    "name": worker["name"],
                    "url": worker["url"],
                    "status": "unreachable",
                    "active_jobs": None,
                    "queued_jobs": None,
                    "max_concurrency": None,
                }
            data = await resp.json()
            return {
                "name": worker["name"],
                "url": worker["url"],
                "status": "ok",
                "active_jobs": data.get("active_jobs", 0),
                "queued_jobs": data.get("queued_jobs", 0),
                "max_concurrency": data.get("max_concurrency"),
            }
    except Exception as exc:
        logger.debug("Health check failed for worker '%s': %s", worker["name"], exc)
        return {
            "name": worker["name"],
            "url": worker["url"],
            "status": "unreachable",
            "active_jobs": None,
            "queued_jobs": None,
            "max_concurrency": None,
        }


async def _handle_list_remote_workers(_arguments: dict) -> list[TextContent]:
    if not _remote_workers:
        return _no_workers_error("list_remote_workers")

    results = await asyncio.gather(*[_fetch_worker_health(w) for w in _remote_workers])
    return [TextContent(type="text", text=json.dumps(list(results)))]


async def _handle_spawn_remote_session(arguments: dict) -> list[TextContent]:
    if not _remote_workers:
        return _no_workers_error("spawn_remote_session")

    worker_name = arguments.get("worker_name")
    selected_worker: dict | None = None

    if worker_name:
        # Find by name
        for w in _remote_workers:
            if w["name"] == worker_name:
                selected_worker = w
                break
        if selected_worker is None:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": (
                                f"Unknown worker name: '{worker_name}'. "
                                f"Configured workers: {[w['name'] for w in _remote_workers]}."
                            )
                        }
                    ),
                )
            ]
    else:
        # Select least-loaded worker via concurrent health checks
        health_results = await asyncio.gather(*[_fetch_worker_health(w) for w in _remote_workers])
        best: dict | None = None
        best_load: int | None = None
        for h in health_results:
            if h["status"] != "ok":
                continue
            load = (h["active_jobs"] or 0) + (h["queued_jobs"] or 0)
            if best_load is None or load < best_load:
                best_load = load
                best = h
        if best is None:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": "All configured remote workers are unreachable or returning auth errors."}),
                )
            ]
        # Match back to worker config entry (to get api_key)
        for w in _remote_workers:
            if w["name"] == best["name"]:
                selected_worker = w
                break

    if selected_worker is None:
        return [
            TextContent(
                type="text",
                text=json.dumps({"error": "Failed to select a remote worker."}),
            )
        ]

    # Build job payload
    payload: dict = {
        "prompt": arguments["prompt"],
        "working_dir": arguments["working_dir"],
        "max_turns": arguments.get("max_turns", DEFAULT_MAX_TURNS),
        "timeout": arguments.get("timeout", DEFAULT_TIMEOUT),
        "permission_mode": arguments.get("permission_mode", DEFAULT_PERMISSION_MODE),
    }
    if "role" in arguments and arguments["role"] is not None:
        payload["role"] = arguments["role"]
    if "allowed_tools" in arguments and arguments["allowed_tools"] is not None:
        payload["allowed_tools"] = arguments["allowed_tools"]

    conn_timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with _get_http_session().post(
            f"{selected_worker['url'].rstrip('/')}/jobs",
            json=payload,
            headers={"X-API-Key": selected_worker.get("api_key", "")},
            timeout=conn_timeout,
        ) as resp:
            body = await resp.json()
            if resp.status not in (200, 201, 202):
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "error": f"Remote worker returned HTTP {resp.status}: {body}",
                                "worker_name": selected_worker["name"],
                            }
                        ),
                    )
                ]
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "job_id": body.get("job_id", ""),
                            "worker_name": selected_worker["name"],
                            "status": body.get("status", "queued"),
                        }
                    ),
                )
            ]
    except Exception as exc:
        logger.debug("Failed to submit job to worker '%s': %s", selected_worker["name"], exc)
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": f"Failed to submit job to worker '{selected_worker['name']}': connection error",
                        "worker_name": selected_worker["name"],
                    }
                ),
            )
        ]


async def _handle_poll_remote_job(arguments: dict) -> list[TextContent]:
    if not _remote_workers:
        return _no_workers_error("poll_remote_job")

    job_id = arguments["job_id"]
    worker_name = arguments.get("worker_name")

    # Build list of workers to query
    if worker_name:
        workers_to_try = [w for w in _remote_workers if w["name"] == worker_name]
        if not workers_to_try:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": (
                                f"Unknown worker name: '{worker_name}'. "
                                f"Configured workers: {[w['name'] for w in _remote_workers]}."
                            )
                        }
                    ),
                )
            ]
    else:
        workers_to_try = list(_remote_workers)

    conn_timeout = aiohttp.ClientTimeout(total=30)

    async def _poll_one(w: dict) -> dict:
        """Poll a single worker. Returns a result dict with a _status key: 'found', 'not_found', 'auth_error', 'error'."""
        try:
            async with _get_http_session().get(
                f"{w['url'].rstrip('/')}/jobs/{job_id}",
                headers={"X-API-Key": w.get("api_key", "")},
                timeout=conn_timeout,
            ) as resp:
                if resp.status in (401, 403):
                    return {"_status": "auth_error", "_worker": w["name"], "_code": resp.status}
                if resp.status == 404:
                    return {"_status": "not_found", "_worker": w["name"]}
                body = await resp.json()
                if resp.status != 200:
                    return {"_status": "error", "_worker": w["name"], "_msg": f"HTTP {resp.status}: {body}"}
                result: dict = {"_status": "found", "job_id": job_id, "status": body.get("status", "unknown")}
                for field in ("output", "git_diff", "exit_code", "duration_ms", "error"):
                    if field in body:
                        result[field] = body[field]
                return result
        except Exception as exc:
            logger.debug("Failed to poll worker '%s' for job '%s': %s", w["name"], job_id, exc)
            return {"_status": "error", "_worker": w["name"], "_msg": f"connection error: {exc}"}

    poll_results = await asyncio.gather(*[_poll_one(w) for w in workers_to_try])

    # First pass: return auth errors immediately (definitive)
    for r in poll_results:
        if r.get("_status") == "auth_error":
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": f"Authentication failed for worker '{r['_worker']}' (HTTP {r['_code']}). Check api_key configuration.",
                            "worker_name": r["_worker"],
                        }
                    ),
                )
            ]

    # Second pass: return first found result
    for r in poll_results:
        if r.get("_status") == "found":
            return [TextContent(type="text", text=json.dumps({k: v for k, v in r.items() if not k.startswith("_")}))]

    # Collect error messages for the final fallback
    errors = [r.get("_msg", "not found") for r in poll_results if r.get("_status") == "error"]
    last_error = "; ".join(errors) if errors else f"Job '{job_id}' not found on any configured worker."
    return [
        TextContent(
            type="text",
            text=json.dumps({"error": last_error}),
        )
    ]


def _load_roles() -> dict[str, dict]:
    """Load roles from built-in defaults, then merge with user-provided roles file.

    Lookup order:
    1. Built-in default-roles.json (always loaded as base)
    2. OUTPOST_ROLES_FILE env var path (if set)
    3. ~/.outpost/roles.json (if exists and OUTPOST_ROLES_FILE not set)

    User file wins on name collision.
    """
    roles: dict[str, dict] = {}

    # Load built-in defaults
    if _BUILTIN_ROLES_FILE.is_file():
        try:
            with open(_BUILTIN_ROLES_FILE, encoding="utf-8") as f:
                builtin_list = json.load(f)
            for idx, r in enumerate(builtin_list):
                if not isinstance(r, dict) or "name" not in r:
                    logger.warning("Built-in role at index %d is missing required field 'name', skipping", idx)
                    continue
                roles[r["name"]] = r
            logger.info("Loaded %d built-in roles from %s", len(roles), _BUILTIN_ROLES_FILE)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load built-in roles from %s: %s", _BUILTIN_ROLES_FILE, exc)

    # Determine user roles file path
    user_roles_path_str = os.environ.get("OUTPOST_ROLES_FILE", "")
    if user_roles_path_str:
        user_roles_path = Path(user_roles_path_str)
    else:
        user_roles_path = Path.home() / ".outpost" / "roles.json"

    if user_roles_path.is_file():
        try:
            with open(user_roles_path, encoding="utf-8") as f:
                user_list = json.load(f)
            added = 0
            for idx, r in enumerate(user_list):
                if not isinstance(r, dict) or "name" not in r:
                    logger.warning("User role at index %d in %s is missing required field 'name', skipping", idx, user_roles_path)
                    continue
                roles[r["name"]] = r
                added += 1
            logger.info("Loaded %d user roles from %s (merged, user wins on collision)", added, user_roles_path)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load user roles from %s: %s", user_roles_path, exc)

    return roles


async def main():
    # Fix 3: Semaphore creation moved into main() to ensure it runs within
    # an active event loop, avoiding Python <3.10 compatibility issues.
    global _semaphore, _server_max_depth, _roles, _remote_workers, _http_session

    try:
        concurrency_limit = int(
            os.environ.get("OUTPOST_MAX_CONCURRENCY", str(DEFAULT_CONCURRENCY))
        )
    except ValueError:
        concurrency_limit = DEFAULT_CONCURRENCY
    _semaphore = asyncio.Semaphore(concurrency_limit)

    # Fix 1: Read server-side max_depth from environment at startup
    try:
        _server_max_depth = int(
            os.environ.get("OUTPOST_MAX_DEPTH", str(DEFAULT_MAX_DEPTH))
        )
    except ValueError:
        _server_max_depth = DEFAULT_MAX_DEPTH

    # Load roles at startup
    _roles = _load_roles()

    # Parse OUTPOST_REMOTE_WORKERS at startup
    remote_workers_raw = os.environ.get("OUTPOST_REMOTE_WORKERS", "")
    if remote_workers_raw.strip():
        try:
            parsed_workers = json.loads(remote_workers_raw)
            if not isinstance(parsed_workers, list):
                raise ValueError("OUTPOST_REMOTE_WORKERS must be a JSON array")
            valid_workers = []
            for idx, w in enumerate(parsed_workers):
                if not isinstance(w, dict) or "name" not in w or "url" not in w:
                    logger.warning(
                        "OUTPOST_REMOTE_WORKERS entry at index %d is missing required field(s) 'name'/'url', skipping", idx
                    )
                    continue
                valid_workers.append(w)
            _remote_workers = valid_workers
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "Failed to parse OUTPOST_REMOTE_WORKERS: %s. Remote dispatch tools will return errors.", exc
            )
            _remote_workers = []
    else:
        _remote_workers = []

    # Create shared aiohttp.ClientSession for remote HTTP calls
    _http_session = aiohttp.ClientSession()

    logger.info(
        "Starting outpost-session-spawner: max_depth=%d, concurrency=%d, roles=%s, remote_workers=%s",
        _server_max_depth,
        concurrency_limit,
        sorted(_roles.keys()),
        [w.get("name") for w in _remote_workers],
    )

    from mcp.server.stdio import stdio_server

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await _http_session.close()


# Module-level defaults for globals set in main() — ensures the names exist
# even if someone imports the module without running main().
_semaphore: asyncio.Semaphore = asyncio.Semaphore(DEFAULT_CONCURRENCY)
_server_max_depth: int = DEFAULT_MAX_DEPTH
_session_registry: list[dict] = []
_roles: dict[str, dict] = {}
_remote_workers: list[dict] = []
_http_session: aiohttp.ClientSession = None  # type: ignore[assignment]  # initialized in main()


def _log_entry(entry: dict) -> None:
    log_file = os.environ.get("OUTPOST_LOG_FILE", "")
    if not log_file:
        return
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.warning("Failed to write JSONL log entry to %s: %s", log_file, exc)


def _print_status_table() -> None:
    try:
        if not _session_registry:
            return

        # Determine status string for each entry
        def _status(entry: dict) -> str:
            if entry.get("success"):
                return "completed"
            if entry.get("timed_out"):
                return "timed_out"
            return "failed"

        # Determine team string for each entry
        def _team(entry: dict) -> str:
            t = entry.get("team_name")
            if not t:
                return "-"
            return t

        # Determine session_id display (truncate to 12 chars)
        def _session_id(entry: dict) -> str:
            sid = entry.get("session_id") or ""
            return sid[:12]

        # Determine duration string
        def _duration(entry: dict) -> str:
            ms = entry.get("duration_ms", 0)
            return f"{ms / 1000:.1f}s"

        # Minimum column widths
        col_widths = {
            "#": 4,
            "Session ID": 12,
            "Depth": 5,
            "Status": 9,
            "Duration": 8,
            "Team": 15,
        }

        # Expand widths based on actual content
        rows = []
        for i, entry in enumerate(_session_registry, start=1):
            row = {
                "#": str(i),
                "Session ID": _session_id(entry),
                "Depth": str(entry.get("depth", "")),
                "Status": _status(entry),
                "Duration": _duration(entry),
                "Team": _team(entry),
            }
            rows.append(row)
            for col in col_widths:
                col_widths[col] = max(col_widths[col], len(row[col]))

        # Also ensure header fits
        for col in col_widths:
            col_widths[col] = max(col_widths[col], len(col))

        columns = ["#", "Session ID", "Depth", "Status", "Duration", "Team"]

        def _separator() -> str:
            parts = ["-" * (col_widths[col] + 2) for col in columns]
            return "+" + "+".join(parts) + "+"

        def _row_line(values: dict) -> str:
            cells = []
            for col in columns:
                val = values[col]
                w = col_widths[col]
                # Right-align numeric columns, left-align others
                if col in ("#", "Depth"):
                    cells.append(f" {val:>{w}} ")
                elif col == "Duration":
                    cells.append(f" {val:>{w}} ")
                else:
                    cells.append(f" {val:<{w}} ")
            return "|" + "|".join(cells) + "|"

        sep = _separator()
        header_values = {col: col for col in columns}

        print(sep, file=sys.stderr)
        print(_row_line(header_values), file=sys.stderr)
        print(sep, file=sys.stderr)
        for row in rows:
            print(_row_line(row), file=sys.stderr)
        print(sep, file=sys.stderr)
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
