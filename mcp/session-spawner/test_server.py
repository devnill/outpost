"""
Tests for the outpost-session-spawner MCP server.

Uses pytest with unittest.mock to verify safety-critical behaviors
without spawning actual claude processes.
"""

import asyncio
import collections
import json
import logging
import os
import subprocess
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the module under test
import session_spawner_server as spawner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_response(result: list) -> dict:
    """Extract the JSON payload from a call_tool response."""
    assert len(result) == 1
    assert result[0].type == "text"
    return json.loads(result[0].text)


def _make_completed_process(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture(autouse=True)
def _reset_globals():
    """Reset module-level globals before each test.

    All globals are reset intentionally:
    - _semaphore: tests like test_concurrency replace it with a smaller semaphore;
      subsequent tests must start with the default.
    - _server_max_depth: tests like test_server_side_max_depth set a lower limit;
      subsequent tests must use DEFAULT_MAX_DEPTH.
    - _session_registry: each test starts with an empty registry to avoid
      cross-test contamination in status table and JSONL logging assertions.
    - _remote_workers: remote dispatch tests configure workers; subsequent tests
      must start with no workers to avoid cross-test contamination.
    - _http_session: cleared so each test gets a fresh mock or lazy-created session.
    """
    spawner._semaphore = asyncio.Semaphore(spawner.DEFAULT_CONCURRENCY)
    spawner._server_max_depth = spawner.DEFAULT_MAX_DEPTH
    spawner._session_registry = collections.deque(maxlen=1000)
    spawner._roles = {}
    spawner._remote_workers = []
    spawner._http_session = None
    yield
    spawner._remote_workers = []
    spawner._http_session = None


@pytest.fixture
def tmp_working_dir(tmp_path):
    """Provide a real temporary directory to use as working_dir."""
    return str(tmp_path)


# ---------------------------------------------------------------------------
# 1. Depth exceeded
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_depth_exceeded(tmp_working_dir):
    """When current depth equals max_depth, the request is rejected."""
    with patch.dict(os.environ, {"OUTPOST_SPAWN_DEPTH": "3"}):
        result = await spawner.call_tool(
            "spawn_session",
            {"prompt": "hello", "working_dir": tmp_working_dir, "max_depth": 3},
        )
    data = _parse_response(result)
    assert data["exit_code"] == 1
    assert "Maximum recursive depth reached" in data["error"]
    assert data["output"] == ""


# ---------------------------------------------------------------------------
# 2. Depth incremented in child env
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_depth_incremented(tmp_working_dir):
    """The child subprocess must receive OUTPOST_SPAWN_DEPTH incremented by 1."""
    captured_env = {}

    def fake_run(*args, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        return _make_completed_process(stdout='{"result": "ok"}')

    with patch.dict(os.environ, {"OUTPOST_SPAWN_DEPTH": "1"}):
        with patch("subprocess.run", side_effect=fake_run):
            await spawner.call_tool(
                "spawn_session",
                {"prompt": "hello", "working_dir": tmp_working_dir, "max_depth": 5},
            )

    assert captured_env["OUTPOST_SPAWN_DEPTH"] == "2"


# ---------------------------------------------------------------------------
# 3. Server-side max_depth enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_server_side_max_depth(tmp_working_dir):
    """OUTPOST_MAX_DEPTH caps the effective max_depth even if caller requests higher."""
    spawner._server_max_depth = 2

    with patch.dict(os.environ, {"OUTPOST_SPAWN_DEPTH": "2"}):
        result = await spawner.call_tool(
            "spawn_session",
            {"prompt": "hello", "working_dir": tmp_working_dir, "max_depth": 10},
        )
    data = _parse_response(result)
    assert data["exit_code"] == 1
    assert "Maximum recursive depth reached" in data["error"]
    # The effective max should be 2 (server limit), not 10 (caller request)
    assert "max=2" in data["error"]


# ---------------------------------------------------------------------------
# 4. Timeout handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeout_handling(tmp_working_dir):
    """TimeoutExpired produces a structured error with timed_out=true and no 'None' string."""
    exc = subprocess.TimeoutExpired(cmd=["claude"], timeout=10)
    exc.stdout = None
    exc.stderr = None

    with patch("subprocess.run", side_effect=exc):
        result = await spawner.call_tool(
            "spawn_session",
            {"prompt": "hello", "working_dir": tmp_working_dir, "timeout": 10},
        )

    data = _parse_response(result)
    assert data["timed_out"] is True
    assert data["exit_code"] == -1
    assert "None" not in data["output"]
    assert "None" not in data.get("error", "")


# ---------------------------------------------------------------------------
# 5. Output truncation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_output_truncation(tmp_working_dir):
    """Output exceeding 50KB is truncated; overflow file is created."""
    big_output = "x" * 60_000  # >50KB

    with patch(
        "subprocess.run",
        return_value=_make_completed_process(stdout=big_output),
    ):
        result = await spawner.call_tool(
            "spawn_session",
            {"prompt": "hello", "working_dir": tmp_working_dir},
        )

    data = _parse_response(result)
    assert data["output_truncated"] is True
    assert "full_output_path" in data
    # The overflow file should exist and contain the full output
    overflow_path = data["full_output_path"]
    with open(overflow_path) as f:
        assert len(f.read()) == 60_000
    # Clean up overflow file
    os.unlink(overflow_path)


# ---------------------------------------------------------------------------
# 6. Prompt length validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prompt_length_validation(tmp_working_dir):
    """Prompts exceeding 100KB are rejected before any subprocess is launched."""
    huge_prompt = "a" * 200_000  # 200KB

    with patch("subprocess.run") as mock_run:
        result = await spawner.call_tool(
            "spawn_session",
            {"prompt": huge_prompt, "working_dir": tmp_working_dir},
        )
        # subprocess.run must NOT have been called
        mock_run.assert_not_called()

    data = _parse_response(result)
    assert data["exit_code"] == 1
    assert "Prompt too large" in data["error"]
    assert "200000" in data["error"]


# ---------------------------------------------------------------------------
# 7. Working directory validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_working_dir_validation():
    """A non-existent working directory is rejected."""
    result = await spawner.call_tool(
        "spawn_session",
        {"prompt": "hello", "working_dir": "/nonexistent/path/that/does/not/exist"},
    )
    data = _parse_response(result)
    assert data["exit_code"] == 1
    assert "does not exist" in data["error"]


# ---------------------------------------------------------------------------
# 8. Safe root validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safe_root_validation(tmp_working_dir, tmp_path):
    """When OUTPOST_SAFE_ROOT is set, directories outside it are rejected."""
    # Create a separate directory that is outside the safe root
    safe_root = str(tmp_path / "safe")
    os.makedirs(safe_root)
    outside_dir = str(tmp_path / "outside")
    os.makedirs(outside_dir)

    with patch.dict(os.environ, {"OUTPOST_SAFE_ROOT": safe_root}):
        result = await spawner.call_tool(
            "spawn_session",
            {"prompt": "hello", "working_dir": outside_dir},
        )

    data = _parse_response(result)
    assert data["exit_code"] == 1
    assert "outside the safe root" in data["error"]


# ---------------------------------------------------------------------------
# 9. Concurrency limiting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrency():
    """The semaphore limits simultaneous executions."""
    spawner._semaphore = asyncio.Semaphore(2)

    max_concurrent = 0
    current_concurrent = 0
    lock = asyncio.Lock()

    original_to_thread = asyncio.to_thread

    async def slow_to_thread(fn, *args, **kwargs):
        nonlocal max_concurrent, current_concurrent
        async with lock:
            current_concurrent += 1
            if current_concurrent > max_concurrent:
                max_concurrent = current_concurrent
        # Simulate work
        await asyncio.sleep(0.05)
        async with lock:
            current_concurrent -= 1
        return _make_completed_process(stdout='{"result": "ok"}')

    tmp_dir = os.path.realpath(os.path.dirname(__file__) or ".")

    with patch("asyncio.to_thread", side_effect=slow_to_thread):
        tasks = [
            spawner.call_tool(
                "spawn_session",
                {"prompt": f"task {i}", "working_dir": tmp_dir},
            )
            for i in range(5)
        ]
        await asyncio.gather(*tasks)

    # The semaphore is set to 2, so at most 2 should run concurrently
    assert max_concurrent <= 2


# ---------------------------------------------------------------------------
# 10. Token budget field
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_token_budget_field(tmp_working_dir):
    """Token usage data from claude JSON output appears in the response."""
    claude_output = json.dumps(
        {
            "result": "done",
            "session_id": "sess-abc123",
            "usage": {
                "input_tokens": 1500,
                "output_tokens": 800,
            },
        }
    )

    with patch(
        "subprocess.run",
        return_value=_make_completed_process(stdout=claude_output),
    ):
        result = await spawner.call_tool(
            "spawn_session",
            {"prompt": "hello", "working_dir": tmp_working_dir},
        )

    data = _parse_response(result)
    assert "token_usage" in data
    assert data["token_usage"]["input_tokens"] == 1500
    assert data["token_usage"]["output_tokens"] == 800
    assert data["session_id"] == "sess-abc123"


@pytest.mark.asyncio
async def test_token_budget_top_level_fields(tmp_working_dir):
    """Token fields at the top level of JSON output are also captured."""
    claude_output = json.dumps(
        {
            "result": "done",
            "input_tokens": 500,
            "output_tokens": 200,
            "total_tokens": 700,
        }
    )

    with patch(
        "subprocess.run",
        return_value=_make_completed_process(stdout=claude_output),
    ):
        result = await spawner.call_tool(
            "spawn_session",
            {"prompt": "hello", "working_dir": tmp_working_dir},
        )

    data = _parse_response(result)
    assert "token_usage" in data
    assert data["token_usage"]["total_tokens"] == 700


@pytest.mark.asyncio
async def test_spawn_session_token_usage_null_when_extraction_fails(tmp_working_dir):
    """Normal-path response includes token_usage: null when output_format is 'text' (token extraction is skipped)."""
    with patch(
        "subprocess.run",
        return_value=_make_completed_process(stdout="plain text output, not JSON"),
    ):
        result = await spawner.call_tool(
            "spawn_session",
            {"prompt": "hello", "working_dir": tmp_working_dir, "output_format": "text"},
        )

    data = _parse_response(result)
    assert "token_usage" in data
    assert data["token_usage"] is None


# ---------------------------------------------------------------------------
# 11. JSONL Logging Tests
# ---------------------------------------------------------------------------

REQUIRED_LOG_FIELDS = {
    "timestamp", "session_id", "depth", "working_dir", "prompt_bytes",
    "team_name", "used_team", "duration_ms", "exit_code", "success",
    "timed_out", "token_usage",
}


@pytest.mark.asyncio
async def test_jsonl_logging_writes_entry(tmp_working_dir):
    """When OUTPOST_LOG_FILE is set, a completed spawn writes exactly one valid JSON line."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        log_path = f.name
    try:
        with patch("subprocess.run", return_value=_make_completed_process(stdout='{"result": "ok"}')):
            with patch.dict(os.environ, {"OUTPOST_LOG_FILE": log_path}):
                await spawner.call_tool("spawn_session", {"prompt": "hello", "working_dir": tmp_working_dir})

        with open(log_path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert REQUIRED_LOG_FIELDS.issubset(entry.keys())
        assert entry["prompt_bytes"] == len("hello".encode("utf-8"))
    finally:
        os.unlink(log_path)


@pytest.mark.asyncio
async def test_jsonl_logging_disabled_when_unset(tmp_working_dir):
    """When OUTPOST_LOG_FILE is not set, no file is created and no exception is raised."""
    env_without_log = {k: v for k, v in os.environ.items() if k != "OUTPOST_LOG_FILE"}
    with patch("subprocess.run", return_value=_make_completed_process(stdout='{"result": "ok"}')):
        with patch.dict(os.environ, env_without_log, clear=True):
            # Should not raise
            result = await spawner.call_tool("spawn_session", {"prompt": "hello", "working_dir": tmp_working_dir})
    data = _parse_response(result)
    assert data["exit_code"] == 0


@pytest.mark.asyncio
async def test_jsonl_logging_appends(tmp_working_dir):
    """Two sequential spawn calls result in a file with exactly two JSON lines."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        log_path = f.name
    try:
        with patch("subprocess.run", return_value=_make_completed_process(stdout='{"result": "ok"}')):
            with patch.dict(os.environ, {"OUTPOST_LOG_FILE": log_path}):
                await spawner.call_tool("spawn_session", {"prompt": "first", "working_dir": tmp_working_dir})
                await spawner.call_tool("spawn_session", {"prompt": "second", "working_dir": tmp_working_dir})

        with open(log_path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        assert len(lines) == 2
        for line in lines:
            entry = json.loads(line)
            assert REQUIRED_LOG_FIELDS.issubset(entry.keys())
    finally:
        os.unlink(log_path)


@pytest.mark.asyncio
async def test_jsonl_no_entry_on_depth_exceeded(tmp_working_dir):
    """A depth-exceeded rejection does not write a log entry."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        log_path = f.name
    try:
        with patch.dict(os.environ, {"OUTPOST_SPAWN_DEPTH": "3", "OUTPOST_LOG_FILE": log_path}):
            result = await spawner.call_tool(
                "spawn_session",
                {"prompt": "hello", "working_dir": tmp_working_dir, "max_depth": 3},
            )

        data = _parse_response(result)
        assert data["exit_code"] == 1

        with open(log_path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        assert len(lines) == 0
    finally:
        os.unlink(log_path)


@pytest.mark.asyncio
async def test_jsonl_timeout_entry(tmp_working_dir):
    """A timed-out call writes an entry with timed_out=True, exit_code=-1, success=False."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        log_path = f.name
    try:
        exc = subprocess.TimeoutExpired(cmd=["claude"], timeout=10)
        exc.stdout = None
        exc.stderr = None

        with patch("subprocess.run", side_effect=exc):
            with patch.dict(os.environ, {"OUTPOST_LOG_FILE": log_path}):
                await spawner.call_tool(
                    "spawn_session",
                    {"prompt": "hello", "working_dir": tmp_working_dir, "timeout": 10},
                )

        with open(log_path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["timed_out"] is True
        assert entry["exit_code"] == -1
        assert entry["success"] is False
        assert entry["prompt_bytes"] == len("hello".encode("utf-8"))  # original prompt, not injected
    finally:
        os.unlink(log_path)


# ---------------------------------------------------------------------------
# 12. Session Registry Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_registry_accumulates(tmp_working_dir):
    """After two spawn calls, _session_registry has exactly two entries."""
    with patch("subprocess.run", return_value=_make_completed_process(stdout='{"result": "ok"}')):
        await spawner.call_tool("spawn_session", {"prompt": "first", "working_dir": tmp_working_dir})
        await spawner.call_tool("spawn_session", {"prompt": "second", "working_dir": tmp_working_dir})

    assert len(spawner._session_registry) == 2


@pytest.mark.asyncio
async def test_session_registry_reset_between_tests(tmp_working_dir):
    """The _reset_globals fixture resets _session_registry to an empty deque(maxlen=1000)."""
    # At the start of each test, _reset_globals has already run, so registry must be empty
    assert len(spawner._session_registry) == 0

    with patch("subprocess.run", return_value=_make_completed_process(stdout='{"result": "ok"}')):
        await spawner.call_tool("spawn_session", {"prompt": "hello", "working_dir": tmp_working_dir})

    assert len(spawner._session_registry) == 1


# ---------------------------------------------------------------------------
# 13. team_name Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_team_name_in_log_entry(tmp_working_dir):
    """When team_name='workers' is passed, log entry has team_name='workers' and used_team=True."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        log_path = f.name
    try:
        with patch("subprocess.run", return_value=_make_completed_process(stdout='{"result": "ok"}')):
            with patch.dict(os.environ, {"OUTPOST_LOG_FILE": log_path}):
                await spawner.call_tool(
                    "spawn_session",
                    {"prompt": "hello", "working_dir": tmp_working_dir, "team_name": "workers"},
                )

        with open(log_path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        entry = json.loads(lines[0])
        assert entry["team_name"] == "workers"
        assert entry["used_team"] is True
    finally:
        os.unlink(log_path)


@pytest.mark.asyncio
async def test_no_team_name_in_log_entry(tmp_working_dir):
    """When team_name is not passed, log entry has team_name=None and used_team=False."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        log_path = f.name
    try:
        with patch("subprocess.run", return_value=_make_completed_process(stdout='{"result": "ok"}')):
            with patch.dict(os.environ, {"OUTPOST_LOG_FILE": log_path}):
                await spawner.call_tool(
                    "spawn_session",
                    {"prompt": "hello", "working_dir": tmp_working_dir},
                )

        with open(log_path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        entry = json.loads(lines[0])
        assert entry["team_name"] is None
        assert entry["used_team"] is False
    finally:
        os.unlink(log_path)


@pytest.mark.asyncio
async def test_team_name_propagated_to_env(tmp_working_dir):
    """When team_name='workers' is passed, child subprocess receives OUTPOST_TEAM_NAME='workers'."""
    captured_env = {}

    def fake_run(cmd, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        return _make_completed_process(stdout='{"result": "ok"}')

    with patch("subprocess.run", side_effect=fake_run):
        await spawner.call_tool(
            "spawn_session",
            {"prompt": "hello", "working_dir": tmp_working_dir, "team_name": "workers"},
        )

    assert captured_env.get("OUTPOST_TEAM_NAME") == "workers"


# ---------------------------------------------------------------------------
# 14. Execution Instructions Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exec_instructions_param_prepended(tmp_working_dir):
    """When exec_instructions='prefer parallel' is passed, subprocess receives injected prompt."""
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _make_completed_process(stdout='{"result": "ok"}')

    env_without_exec = {k: v for k, v in os.environ.items() if k != "OUTPOST_EXEC_INSTRUCTIONS"}
    with patch("subprocess.run", side_effect=fake_run):
        with patch.dict(os.environ, env_without_exec, clear=True):
            await spawner.call_tool(
                "spawn_session",
                {"prompt": "do something", "working_dir": tmp_working_dir, "exec_instructions": "prefer parallel"},
            )

    actual_prompt = captured_cmd[-1]
    assert actual_prompt.startswith(
        "[EXECUTION INSTRUCTIONS]\nprefer parallel\n[END EXECUTION INSTRUCTIONS]\n\n"
    )
    assert "do something" in actual_prompt


@pytest.mark.asyncio
async def test_exec_instructions_env_var_used(tmp_working_dir):
    """When OUTPOST_EXEC_INSTRUCTIONS='use teams' is set and no param provided, prompt is injected."""
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _make_completed_process(stdout='{"result": "ok"}')

    with patch("subprocess.run", side_effect=fake_run):
        with patch.dict(os.environ, {"OUTPOST_EXEC_INSTRUCTIONS": "use teams"}):
            await spawner.call_tool(
                "spawn_session",
                {"prompt": "do something", "working_dir": tmp_working_dir},
            )

    actual_prompt = captured_cmd[-1]
    assert actual_prompt.startswith(
        "[EXECUTION INSTRUCTIONS]\nuse teams\n[END EXECUTION INSTRUCTIONS]\n\n"
    )


@pytest.mark.asyncio
async def test_exec_instructions_param_overrides_env(tmp_working_dir):
    """When both param and env var are set, param value is used."""
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _make_completed_process(stdout='{"result": "ok"}')

    with patch("subprocess.run", side_effect=fake_run):
        with patch.dict(os.environ, {"OUTPOST_EXEC_INSTRUCTIONS": "env value"}):
            await spawner.call_tool(
                "spawn_session",
                {
                    "prompt": "do something",
                    "working_dir": tmp_working_dir,
                    "exec_instructions": "param value",
                },
            )

    actual_prompt = captured_cmd[-1]
    assert "param value" in actual_prompt
    assert "env value" not in actual_prompt


@pytest.mark.asyncio
async def test_exec_instructions_propagated_to_child_env(tmp_working_dir):
    """When instructions are resolved, OUTPOST_EXEC_INSTRUCTIONS is set in child subprocess env."""
    captured_env = {}

    def fake_run(cmd, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        return _make_completed_process(stdout='{"result": "ok"}')

    env_without_exec = {k: v for k, v in os.environ.items() if k != "OUTPOST_EXEC_INSTRUCTIONS"}
    with patch("subprocess.run", side_effect=fake_run):
        with patch.dict(os.environ, env_without_exec, clear=True):
            await spawner.call_tool(
                "spawn_session",
                {"prompt": "hello", "working_dir": tmp_working_dir, "exec_instructions": "prefer parallel"},
            )

    assert captured_env.get("OUTPOST_EXEC_INSTRUCTIONS") == "prefer parallel"


@pytest.mark.asyncio
async def test_no_exec_instructions_prompt_unchanged(tmp_working_dir):
    """When neither param nor env var is set, subprocess receives the original prompt unchanged."""
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _make_completed_process(stdout='{"result": "ok"}')

    env_without_exec = {k: v for k, v in os.environ.items() if k != "OUTPOST_EXEC_INSTRUCTIONS"}
    with patch("subprocess.run", side_effect=fake_run):
        with patch.dict(os.environ, env_without_exec, clear=True):
            await spawner.call_tool(
                "spawn_session",
                {"prompt": "original prompt", "working_dir": tmp_working_dir},
            )

    actual_prompt = captured_cmd[-1]
    assert actual_prompt == "original prompt"


@pytest.mark.asyncio
async def test_prompt_size_validation_uses_original_prompt(tmp_working_dir):
    """A prompt just under 100KB with exec_instructions passes validation (instructions not counted)."""
    # 99,900 bytes prompt — under the 100KB limit
    big_prompt = "a" * 99_900
    # 1000-byte exec_instructions — would push total over limit if counted, but shouldn't be
    exec_instr = "x" * 1000

    with patch("subprocess.run", return_value=_make_completed_process(stdout='{"result": "ok"}')) as mock_run:
        env_without_exec = {k: v for k, v in os.environ.items() if k != "OUTPOST_EXEC_INSTRUCTIONS"}
        with patch.dict(os.environ, env_without_exec, clear=True):
            result = await spawner.call_tool(
                "spawn_session",
                {"prompt": big_prompt, "working_dir": tmp_working_dir, "exec_instructions": exec_instr},
            )
        mock_run.assert_called_once()

    data = _parse_response(result)
    assert data["exit_code"] == 0


# ---------------------------------------------------------------------------
# 15. Status Table Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_table_printed_to_stderr(capsys, tmp_working_dir):
    """After a spawn call, the status table is printed to stderr with expected column headers."""
    with patch("subprocess.run", return_value=_make_completed_process(stdout='{"result": "ok"}')):
        await spawner.call_tool("spawn_session", {"prompt": "hi", "working_dir": tmp_working_dir})

    captured = capsys.readouterr()
    assert "Session ID" in captured.err
    assert "Depth" in captured.err
    assert "Status" in captured.err
    assert "Duration" in captured.err
    assert "Team" in captured.err
    assert "+" in captured.err          # separator row(s) present
    assert "completed" in captured.err  # at least one completed data row


def test_status_table_empty_registry_no_output(capsys):
    """If _session_registry is empty, _print_status_table() prints nothing to stderr."""
    spawner._session_registry = collections.deque(maxlen=1000)
    spawner._print_status_table()
    captured = capsys.readouterr()
    assert captured.err == ""


# ---------------------------------------------------------------------------
# 16. Negative-case env propagation tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_team_name_absent_from_child_env_when_not_provided(tmp_working_dir):
    """When team_name is not passed, OUTPOST_TEAM_NAME is absent from the child subprocess env."""
    captured_env = {}

    def fake_run(cmd, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        return _make_completed_process(stdout='{"result": "ok"}')

    env_without_team = {k: v for k, v in os.environ.items() if k != "OUTPOST_TEAM_NAME"}
    with patch("subprocess.run", side_effect=fake_run):
        with patch.dict(os.environ, env_without_team, clear=True):
            await spawner.call_tool(
                "spawn_session",
                {"prompt": "hello", "working_dir": tmp_working_dir},
            )

    assert "OUTPOST_TEAM_NAME" not in captured_env


@pytest.mark.asyncio
async def test_team_name_not_inherited_from_grandparent_env(tmp_working_dir):
    """Even if OUTPOST_TEAM_NAME is set in os.environ, it is stripped when team_name param is absent."""
    captured_env = {}

    def fake_run(cmd, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        return _make_completed_process(stdout='{"result": "ok"}')

    with patch("subprocess.run", side_effect=fake_run):
        with patch.dict(os.environ, {"OUTPOST_TEAM_NAME": "grandparent-team"}):
            await spawner.call_tool(
                "spawn_session",
                {"prompt": "hello", "working_dir": tmp_working_dir},
                # No team_name param — should strip inherited env var
            )

    assert "OUTPOST_TEAM_NAME" not in captured_env


@pytest.mark.asyncio
async def test_exec_instructions_absent_from_child_env_when_not_provided(tmp_working_dir):
    """When exec_instructions is not passed and env var is unset, OUTPOST_EXEC_INSTRUCTIONS is absent from child env."""
    captured_env = {}

    def fake_run(cmd, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        return _make_completed_process(stdout='{"result": "ok"}')

    env_without_exec = {k: v for k, v in os.environ.items() if k != "OUTPOST_EXEC_INSTRUCTIONS"}
    with patch("subprocess.run", side_effect=fake_run):
        with patch.dict(os.environ, env_without_exec, clear=True):
            await spawner.call_tool(
                "spawn_session",
                {"prompt": "hello", "working_dir": tmp_working_dir},
            )

    assert "OUTPOST_EXEC_INSTRUCTIONS" not in captured_env


# ---------------------------------------------------------------------------
# 17. --allowedTools CLI Syntax Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_allowed_tools_comma_syntax(tmp_working_dir):
    """allowed_tools list is passed to claude as '--allowedTools Read,Edit' (comma-separated)."""
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _make_completed_process(stdout='{"result": "ok"}')

    with patch("subprocess.run", side_effect=fake_run):
        await spawner.call_tool(
            "spawn_session",
            {"prompt": "hello", "working_dir": tmp_working_dir, "allowed_tools": ["Read", "Edit"]},
        )

    assert "--allowedTools" in captured_cmd
    idx = captured_cmd.index("--allowedTools")
    assert captured_cmd[idx + 1] == "Read,Edit"


# ---------------------------------------------------------------------------
# 18. Remote Dispatch Tool Tests
# ---------------------------------------------------------------------------

def _make_mock_response(status: int, json_data: dict) -> MagicMock:
    """Build a mock aiohttp response context manager."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_data)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _configure_workers(workers: list[dict]) -> None:
    """Set spawner._remote_workers directly for tests."""
    spawner._remote_workers = workers


@pytest.mark.asyncio
async def test_spawn_remote_session_submits_job_and_returns_job_id():
    """spawn_remote_session submits to configured worker and returns job_id and worker_name."""
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"}])

    captured_payload = {}

    mock_session = MagicMock()
    # When no worker_name specified, code does GET /health first, then POST /jobs
    mock_session.get = MagicMock(return_value=_make_mock_response(200, {
        "active_jobs": 0, "queued_jobs": 0, "max_concurrency": 4,
    }))

    def capture_post(url, json=None, **kwargs):
        if json is not None:
            captured_payload.update(json)
        return _make_mock_response(201, {"job_id": "job-abc", "status": "queued"})

    mock_session.post = MagicMock(side_effect=capture_post)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "spawn_remote_session",
            {"prompt": "do the thing", "working_dir": "/tmp"},
        )

    data = _parse_response(result)
    assert data["job_id"] == "job-abc"
    assert data["worker_name"] == "worker-1"
    assert mock_session.post.called
    assert captured_payload["prompt"] == "do the thing"


@pytest.mark.asyncio
async def test_spawn_remote_session_no_workers_returns_error_no_http_call():
    """spawn_remote_session with no workers configured returns structured error, no HTTP call made."""
    # _remote_workers is already [] from _reset_globals fixture
    mock_session = MagicMock()

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "spawn_remote_session",
            {"prompt": "do the thing", "working_dir": "/tmp"},
        )

    data = _parse_response(result)
    assert "error" in data
    assert "No remote workers configured" in data["error"]
    mock_session.post.assert_not_called()
    mock_session.get.assert_not_called()


@pytest.mark.asyncio
async def test_poll_remote_job_queued_returns_queued_status():
    """poll_remote_job for a queued job returns status 'queued'."""
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"}])

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(200, {"status": "queued"}))

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "poll_remote_job",
            {"job_id": "job-queued-123", "worker_name": "worker-1"},
        )

    data = _parse_response(result)
    assert data["status"] == "queued"
    assert data["job_id"] == "job-queued-123"


@pytest.mark.asyncio
async def test_poll_remote_job_completed_returns_output_and_git_diff():
    """poll_remote_job for a completed job returns output and git_diff."""
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"}])

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(200, {
        "status": "completed",
        "output": "task done successfully",
        "git_diff": "diff --git a/file.py b/file.py\n+new line",
        "exit_code": 0,
    }))

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "poll_remote_job",
            {"job_id": "job-done-456", "worker_name": "worker-1"},
        )

    data = _parse_response(result)
    assert data["status"] == "completed"
    assert data["output"] == "task done successfully"
    assert data["git_diff"] == "diff --git a/file.py b/file.py\n+new line"


@pytest.mark.asyncio
async def test_list_remote_workers_returns_one_entry_per_worker():
    """list_remote_workers returns one entry per configured worker with health data."""
    _configure_workers([
        {"name": "worker-a", "url": "http://worker-a.example.com", "api_key": "keyA"},
        {"name": "worker-b", "url": "http://worker-b.example.com", "api_key": "keyB"},
    ])

    mock_session = MagicMock()
    mock_session.get = MagicMock(side_effect=[
        _make_mock_response(200, {"active_jobs": 2, "queued_jobs": 1, "max_concurrency": 4, "max_jobs": 500}),
        _make_mock_response(200, {"active_jobs": 2, "queued_jobs": 1, "max_concurrency": 4, "max_jobs": 500}),
    ])

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool("list_remote_workers", {})

    data = _parse_response(result)
    assert isinstance(data, list)
    assert len(data) == 2
    names = {entry["name"] for entry in data}
    assert names == {"worker-a", "worker-b"}
    for entry in data:
        assert entry["status"] == "ok"
        assert entry["active_jobs"] == 2
        assert entry["max_jobs"] == 500


@pytest.mark.asyncio
async def test_list_remote_workers_unreachable_worker_no_raise():
    """list_remote_workers marks an unreachable worker as status 'unreachable', does not raise."""
    _configure_workers([
        {"name": "worker-ok", "url": "http://worker-ok.example.com", "api_key": "keyOk"},
        {"name": "worker-dead", "url": "http://worker-dead.example.com", "api_key": "keyDead"},
    ])

    ok_response = _make_mock_response(200, {"active_jobs": 0, "queued_jobs": 0, "max_concurrency": 4})
    # 503 triggers the "unreachable" branch in _fetch_worker_health
    dead_response = _make_mock_response(503, {})

    call_count = 0

    def side_effect_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if "worker-ok" in url:
            return ok_response
        return dead_response

    mock_session = MagicMock()
    mock_session.get = MagicMock(side_effect=side_effect_get)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        # Should not raise even though one worker is unreachable
        result = await spawner.call_tool("list_remote_workers", {})

    data = _parse_response(result)
    assert isinstance(data, list)
    assert len(data) == 2
    status_by_name = {entry["name"]: entry["status"] for entry in data}
    assert status_by_name["worker-ok"] == "ok"
    assert status_by_name["worker-dead"] == "unreachable"


@pytest.mark.asyncio
async def test_spawn_remote_session_selects_least_loaded_worker():
    """With two workers, the less-loaded one is selected when no worker_name is specified."""
    _configure_workers([
        {"name": "busy-worker", "url": "http://busy.example.com", "api_key": "keyBusy"},
        {"name": "idle-worker", "url": "http://idle.example.com", "api_key": "keyIdle"},
    ])

    busy_health = _make_mock_response(200, {"active_jobs": 5, "queued_jobs": 3, "max_concurrency": 8})
    idle_health = _make_mock_response(200, {"active_jobs": 0, "queued_jobs": 0, "max_concurrency": 8})
    post_response = _make_mock_response(201, {"job_id": "job-selected", "status": "queued"})

    def side_effect_get(url, **kwargs):
        if "busy" in url:
            return busy_health
        return idle_health

    mock_session = MagicMock()
    mock_session.get = MagicMock(side_effect=side_effect_get)
    mock_session.post = MagicMock(return_value=post_response)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "spawn_remote_session",
            {"prompt": "task", "working_dir": "/tmp"},
        )

    data = _parse_response(result)
    assert data["job_id"] == "job-selected"
    assert data["worker_name"] == "idle-worker"

    # Verify POST went to idle worker URL
    post_call_url = mock_session.post.call_args[0][0]
    assert "idle" in post_call_url


@pytest.mark.asyncio
async def test_spawn_remote_session_auth_error_returns_descriptive_error():
    """A 401 response from the remote worker's POST /jobs returns a descriptive error to the tool caller.

    When worker_name is specified explicitly, the code skips health checks and POSTs directly,
    so the 401 comes back from the job submission endpoint and is included in the error message.
    """
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "bad-key"}])

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=_make_mock_response(401, {"detail": "Unauthorized"}))

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "spawn_remote_session",
            {"prompt": "do the thing", "working_dir": "/tmp", "worker_name": "worker-1"},
        )

    data = _parse_response(result)
    assert "error" in data
    assert "401" in data["error"]
    assert "worker_name" in data
    assert data["worker_name"] == "worker-1"


@pytest.mark.asyncio
async def test_list_remote_workers_auth_error_worker():
    """list_remote_workers marks a worker returning 401 as status 'auth_error'."""
    _configure_workers([
        {"name": "worker-good", "url": "http://worker-good.example.com", "api_key": "good-key"},
        {"name": "worker-bad-auth", "url": "http://worker-bad.example.com", "api_key": "wrong-key"},
    ])

    def side_effect_get(url, **kwargs):
        if "worker-good" in url:
            return _make_mock_response(200, {"active_jobs": 0, "queued_jobs": 0, "max_concurrency": 4})
        return _make_mock_response(401, {"detail": "Unauthorized"})

    mock_session = MagicMock()
    mock_session.get = MagicMock(side_effect=side_effect_get)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool("list_remote_workers", {})

    data = _parse_response(result)
    status_by_name = {entry["name"]: entry["status"] for entry in data}
    assert status_by_name["worker-good"] == "ok"
    assert status_by_name["worker-bad-auth"] == "auth_error"


# ---------------------------------------------------------------------------
# 19. Role System Tests
# ---------------------------------------------------------------------------

_TEST_ROLE = {
    "name": "test-role",
    "system_prompt": "You are a test agent.",
    "allowed_tools": ["Read"],
    "max_turns": 10,
    "permission_mode": "acceptEdits",
}


@pytest.mark.asyncio
async def test_role_system_prompt_injected(tmp_working_dir):
    """spawn_session with a known role prepends the role's system_prompt to the prompt."""
    spawner._roles = {"test-role": _TEST_ROLE}
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _make_completed_process(stdout='{"result": "ok"}')

    with patch("subprocess.run", side_effect=fake_run):
        await spawner.call_tool(
            "spawn_session",
            {"prompt": "do the work", "working_dir": tmp_working_dir, "role": "test-role"},
        )

    # The prompt is the element after --cwd <working_dir>; --allowedTools may follow it
    cwd_idx = captured_cmd.index("--cwd")
    actual_prompt = captured_cmd[cwd_idx + 2]
    assert actual_prompt.startswith("[ROLE: test-role]\nYou are a test agent.\n\n")
    assert "do the work" in actual_prompt


@pytest.mark.asyncio
async def test_role_allowed_tools_caller_wins(tmp_working_dir):
    """Caller-provided allowed_tools overrides role-defined allowed_tools."""
    spawner._roles = {"test-role": _TEST_ROLE}
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _make_completed_process(stdout='{"result": "ok"}')

    with patch("subprocess.run", side_effect=fake_run):
        await spawner.call_tool(
            "spawn_session",
            {
                "prompt": "do the work",
                "working_dir": tmp_working_dir,
                "role": "test-role",
                "allowed_tools": ["Write"],
            },
        )

    assert "--allowedTools" in captured_cmd
    idx = captured_cmd.index("--allowedTools")
    assert captured_cmd[idx + 1] == "Write"
    assert "Read" not in captured_cmd[idx + 1]


@pytest.mark.asyncio
async def test_role_allowed_tools_used_when_caller_omits(tmp_working_dir):
    """Role-defined allowed_tools is used when caller does not provide allowed_tools."""
    spawner._roles = {"test-role": _TEST_ROLE}
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _make_completed_process(stdout='{"result": "ok"}')

    with patch("subprocess.run", side_effect=fake_run):
        await spawner.call_tool(
            "spawn_session",
            {"prompt": "do the work", "working_dir": tmp_working_dir, "role": "test-role"},
        )

    assert "--allowedTools" in captured_cmd
    idx = captured_cmd.index("--allowedTools")
    assert captured_cmd[idx + 1] == "Read"


@pytest.mark.asyncio
async def test_no_role_no_system_prompt_injection(tmp_working_dir):
    """spawn_session with role=None behaves identically to a call without a role parameter."""
    spawner._roles = {"test-role": _TEST_ROLE}
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _make_completed_process(stdout='{"result": "ok"}')

    env_without_exec = {k: v for k, v in os.environ.items() if k != "OUTPOST_EXEC_INSTRUCTIONS"}
    with patch("subprocess.run", side_effect=fake_run):
        with patch.dict(os.environ, env_without_exec, clear=True):
            await spawner.call_tool(
                "spawn_session",
                {"prompt": "original prompt", "working_dir": tmp_working_dir, "role": None},
            )

    cwd_idx = captured_cmd.index("--cwd")
    actual_prompt = captured_cmd[cwd_idx + 2]
    assert actual_prompt == "original prompt"
    assert "--allowedTools" not in captured_cmd


@pytest.mark.asyncio
async def test_unknown_role_returns_structured_error(tmp_working_dir):
    """spawn_session with an unknown role name returns a structured error with exit_code=1."""
    spawner._roles = {"test-role": _TEST_ROLE}

    with patch("subprocess.run") as mock_run:
        result = await spawner.call_tool(
            "spawn_session",
            {"prompt": "do the work", "working_dir": tmp_working_dir, "role": "no-such-role"},
        )
        mock_run.assert_not_called()

    data = _parse_response(result)
    assert data["exit_code"] == 1
    assert "no-such-role" in data["error"]


@pytest.mark.asyncio
async def test_role_max_turns_used_when_caller_omits(tmp_working_dir):
    """Role-defined max_turns is used when caller does not provide max_turns."""
    spawner._roles = {"test-role": _TEST_ROLE}
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _make_completed_process(stdout='{"result": "ok"}')

    with patch("subprocess.run", side_effect=fake_run):
        await spawner.call_tool(
            "spawn_session",
            {"prompt": "do the work", "working_dir": tmp_working_dir, "role": "test-role"},
        )

    assert "--max-turns" in captured_cmd
    idx = captured_cmd.index("--max-turns")
    assert captured_cmd[idx + 1] == "10"  # server passes str(max_turns) to subprocess


# ---------------------------------------------------------------------------
# 20. Model Parameter Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_model_param_passed_to_subprocess(tmp_working_dir):
    """spawn_session with model='claude-opus-4-6' passes --model claude-opus-4-6 to subprocess."""
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _make_completed_process(stdout='{"result": "ok"}')

    with patch("subprocess.run", side_effect=fake_run):
        await spawner.call_tool(
            "spawn_session",
            {"prompt": "hello", "working_dir": tmp_working_dir, "model": "claude-opus-4-6"},
        )

    assert "--model" in captured_cmd
    idx = captured_cmd.index("--model")
    assert captured_cmd[idx + 1] == "claude-opus-4-6"


@pytest.mark.asyncio
async def test_model_param_absent_when_not_provided(tmp_working_dir):
    """spawn_session without model parameter does NOT include --model in the subprocess command."""
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _make_completed_process(stdout='{"result": "ok"}')

    with patch("subprocess.run", side_effect=fake_run):
        await spawner.call_tool(
            "spawn_session",
            {"prompt": "hello", "working_dir": tmp_working_dir},
        )

    assert "--model" not in captured_cmd


@pytest.mark.asyncio
async def test_model_param_absent_when_none(tmp_working_dir):
    """spawn_session with model=None does NOT include --model in the subprocess command."""
    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _make_completed_process(stdout='{"result": "ok"}')

    with patch("subprocess.run", side_effect=fake_run):
        await spawner.call_tool(
            "spawn_session",
            {"prompt": "hello", "working_dir": tmp_working_dir, "model": None},
        )

    assert "--model" not in captured_cmd


# ---------------------------------------------------------------------------
# 21. Token Budget JSONL Logging Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_jsonl_token_usage_present_when_json_output_has_usage(tmp_working_dir):
    """JSONL log entry includes token_usage field when claude JSON output contains usage data."""
    claude_output = json.dumps({
        "session_id": "test-session",
        "result": "done",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    })

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        log_path = f.name
    try:
        with patch("subprocess.run", return_value=_make_completed_process(stdout=claude_output)):
            with patch.dict(os.environ, {"OUTPOST_LOG_FILE": log_path}):
                await spawner.call_tool(
                    "spawn_session",
                    {"prompt": "hello", "working_dir": tmp_working_dir},
                )

        with open(log_path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert "token_usage" in entry
        assert entry["token_usage"] is not None
        assert entry["token_usage"]["input_tokens"] == 100
        assert entry["token_usage"]["output_tokens"] == 50
    finally:
        os.unlink(log_path)


@pytest.mark.asyncio
async def test_jsonl_token_usage_null_when_non_json_output(tmp_working_dir):
    """JSONL log entry has token_usage=null when claude output is plain text (non-JSON)."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        log_path = f.name
    try:
        with patch("subprocess.run", return_value=_make_completed_process(stdout="plain text response")):
            with patch.dict(os.environ, {"OUTPOST_LOG_FILE": log_path}):
                await spawner.call_tool(
                    "spawn_session",
                    {"prompt": "hello", "working_dir": tmp_working_dir},
                )

        with open(log_path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert "token_usage" in entry
        assert entry["token_usage"] is None
    finally:
        os.unlink(log_path)


@pytest.mark.asyncio
async def test_jsonl_token_usage_null_on_timeout(tmp_working_dir):
    """JSONL log entry has token_usage=null on the timeout path."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        log_path = f.name
    try:
        exc = subprocess.TimeoutExpired(cmd=["claude"], timeout=10)
        exc.stdout = None
        exc.stderr = None

        with patch("subprocess.run", side_effect=exc):
            with patch.dict(os.environ, {"OUTPOST_LOG_FILE": log_path}):
                await spawner.call_tool(
                    "spawn_session",
                    {"prompt": "hello", "working_dir": tmp_working_dir, "timeout": 10},
                )

        with open(log_path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert "token_usage" in entry
        assert entry["token_usage"] is None
    finally:
        os.unlink(log_path)


@pytest.mark.asyncio
async def test_jsonl_token_usage_schema(tmp_working_dir):
    """token_usage field structure has input_tokens and output_tokens integer keys when not null."""
    claude_output = json.dumps({
        "session_id": "sess-schema",
        "result": "done",
        "usage": {"input_tokens": 200, "output_tokens": 75},
    })

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        log_path = f.name
    try:
        with patch("subprocess.run", return_value=_make_completed_process(stdout=claude_output)):
            with patch.dict(os.environ, {"OUTPOST_LOG_FILE": log_path}):
                await spawner.call_tool(
                    "spawn_session",
                    {"prompt": "hello", "working_dir": tmp_working_dir},
                )

        with open(log_path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        entry = json.loads(lines[0])
        token_usage = entry["token_usage"]
        assert token_usage is not None
        assert "input_tokens" in token_usage
        assert "output_tokens" in token_usage
        assert isinstance(token_usage["input_tokens"], int)
        assert isinstance(token_usage["output_tokens"], int)
        assert token_usage["input_tokens"] == 200
        assert token_usage["output_tokens"] == 75
    finally:
        os.unlink(log_path)

# ==============================================================================
# _load_roles tests
# ==============================================================================

class TestLoadRoles:
    def test_load_roles_from_env_file(self, tmp_path, monkeypatch):
        roles_file = tmp_path / "roles.json"
        roles_file.write_text(json.dumps([
            {"name": "test-role", "description": "A test role", "allowed_tools": ["Read"]},
        ]))
        monkeypatch.setenv("OUTPOST_ROLES_FILE", str(roles_file))
        roles = spawner._load_roles()
        assert "test-role" in roles
        assert roles["test-role"]["allowed_tools"] == ["Read"]

    def test_load_roles_skips_entries_missing_name(self, tmp_path, monkeypatch):
        roles_file = tmp_path / "roles.json"
        roles_file.write_text(json.dumps([
            {"description": "no name field"},
            {"name": "valid-role", "description": "has a name"},
        ]))
        monkeypatch.setenv("OUTPOST_ROLES_FILE", str(roles_file))
        roles = spawner._load_roles()
        assert "valid-role" in roles
        # entries without "name" must not appear
        for key in roles:
            assert key != ""

    def test_user_roles_override_builtin_on_collision(self, tmp_path, monkeypatch):
        roles_file = tmp_path / "roles.json"
        # Override the built-in "worker" role
        roles_file.write_text(json.dumps([
            {"name": "worker", "description": "overridden", "allowed_tools": ["Read"]},
        ]))
        monkeypatch.setenv("OUTPOST_ROLES_FILE", str(roles_file))
        roles = spawner._load_roles()
        assert roles["worker"]["description"] == "overridden"


@pytest.mark.asyncio
async def test_poll_remote_job_completed_includes_timestamp_fields():
    """poll_remote_job for a completed job includes created_at, started_at, completed_at when present."""
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"}])

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(200, {
        "status": "completed",
        "output": "done",
        "exit_code": 0,
        "created_at": "2026-03-16T10:00:00.000Z",
        "started_at": "2026-03-16T10:00:01.000Z",
        "completed_at": "2026-03-16T10:05:00.000Z",
    }))

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "poll_remote_job",
            {"job_id": "job-ts-test", "worker_name": "worker-1"},
        )

    data = _parse_response(result)
    assert data["created_at"] == "2026-03-16T10:00:00.000Z"
    assert data["started_at"] == "2026-03-16T10:00:01.000Z"
    assert data["completed_at"] == "2026-03-16T10:05:00.000Z"


@pytest.mark.asyncio
async def test_poll_remote_job_running_omits_absent_timestamp_fields():
    """poll_remote_job for a running job does not include timestamp fields that are absent in the response."""
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"}])

    mock_session = MagicMock()
    # Running job: remote worker returns started_at but not completed_at
    mock_session.get = MagicMock(return_value=_make_mock_response(200, {
        "status": "running",
        "started_at": "2026-03-16T10:00:01.000Z",
    }))

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "poll_remote_job",
            {"job_id": "job-running-ts", "worker_name": "worker-1"},
        )

    data = _parse_response(result)
    assert data["started_at"] == "2026-03-16T10:00:01.000Z"
    assert "completed_at" not in data


@pytest.mark.asyncio
async def test_poll_remote_job_found_wins_over_auth_error():
    """When one worker returns a found result and another returns 401, the found result is returned."""
    _configure_workers([
        {"name": "worker-auth-fail", "url": "http://auth-fail.example.com", "api_key": "bad-key"},
        {"name": "worker-has-job", "url": "http://has-job.example.com", "api_key": "good-key"},
    ])

    def side_effect_get(url, **kwargs):
        if "auth-fail" in url:
            return _make_mock_response(401, {"detail": "Invalid API key"})
        # worker-has-job has the result
        return _make_mock_response(200, {"status": "completed", "output": "done", "exit_code": 0})

    mock_session = MagicMock()
    mock_session.get = MagicMock(side_effect=side_effect_get)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "poll_remote_job",
            {"job_id": "job-abc"},
        )

    data = _parse_response(result)
    assert "error" not in data, f"Expected found result, got error: {data}"
    assert data["status"] == "completed"
    assert data["output"] == "done"


@pytest.mark.asyncio
async def test_poll_remote_job_all_auth_errors_returns_error():
    """When all workers return 401, an auth error is returned."""
    _configure_workers([
        {"name": "worker-1", "url": "http://worker1.example.com", "api_key": "bad-key-1"},
        {"name": "worker-2", "url": "http://worker2.example.com", "api_key": "bad-key-2"},
    ])

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(401, {"detail": "Invalid API key"}))

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "poll_remote_job",
            {"job_id": "job-xyz"},
        )

    data = _parse_response(result)
    assert "error" in data
    assert "Authentication failed" in data["error"]


# ---------------------------------------------------------------------------
# 24. Remote Session Role Constraints Tests
# ---------------------------------------------------------------------------

_REVIEWER_ROLE = {
    "name": "reviewer",
    "system_prompt": "You are a code reviewer.",
    "allowed_tools": ["Read", "Glob"],
    "max_turns": 5,
    "permission_mode": "default",
    "description": "Read-only code review role",
}


@pytest.mark.asyncio
async def test_spawn_remote_session_role_name_resolves_constraints():
    """spawn_remote_session with a known role name propagates allowed_tools and permission_mode from the role."""
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"}])
    spawner._roles = {"reviewer": _REVIEWER_ROLE}

    captured_payload = {}

    mock_resp = MagicMock()
    mock_resp.status = 201
    mock_resp.json = AsyncMock(return_value={"job_id": "job-role-test", "status": "queued"})
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_resp)
    cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(200, {
        "active_jobs": 0, "queued_jobs": 0, "max_concurrency": 4,
    }))

    def capture_post(url, json=None, **kwargs):
        if json is not None:
            captured_payload.update(json)
        return cm

    mock_session.post = MagicMock(side_effect=capture_post)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "spawn_remote_session",
            {"prompt": "review this code", "working_dir": "/tmp", "role": "reviewer"},
        )

    data = _parse_response(result)
    assert data["job_id"] == "job-role-test"
    assert captured_payload["allowed_tools"] == ["Read", "Glob"]
    assert captured_payload["permission_mode"] == "default"
    assert captured_payload["role"] == "reviewer"


@pytest.mark.asyncio
async def test_spawn_remote_session_unknown_role_returns_error():
    """spawn_remote_session with an unknown role name returns an error without making any HTTP call."""
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"}])
    spawner._roles = {"reviewer": _REVIEWER_ROLE}

    mock_session = MagicMock()

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "spawn_remote_session",
            {"prompt": "do something", "working_dir": "/tmp", "role": "nonexistent"},
        )

    data = _parse_response(result)
    assert "error" in data
    assert "nonexistent" in data["error"]
    mock_session.post.assert_not_called()
    mock_session.get.assert_not_called()


@pytest.mark.asyncio
async def test_spawn_remote_session_inline_role_dict_passes_through():
    """spawn_remote_session with an inline role dict uses the dict's fields directly."""
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"}])

    inline_role = {"name": "custom", "allowed_tools": ["Read"], "permission_mode": "default"}
    captured_payload = {}

    mock_resp = MagicMock()
    mock_resp.status = 201
    mock_resp.json = AsyncMock(return_value={"job_id": "job-inline-role", "status": "queued"})
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_resp)
    cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(200, {
        "active_jobs": 0, "queued_jobs": 0, "max_concurrency": 4,
    }))

    def capture_post(url, json=None, **kwargs):
        if json is not None:
            captured_payload.update(json)
        return cm

    mock_session.post = MagicMock(side_effect=capture_post)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "spawn_remote_session",
            {"prompt": "inline role task", "working_dir": "/tmp", "role": inline_role},
        )

    data = _parse_response(result)
    assert data["job_id"] == "job-inline-role"
    assert captured_payload["allowed_tools"] == ["Read"]
    assert captured_payload["permission_mode"] == "default"
    assert captured_payload["role"] == "custom"


@pytest.mark.asyncio
async def test_spawn_remote_session_named_role_with_system_prompt_injects_into_prompt():
    """spawn_remote_session with a named role that has system_prompt prepends it to the prompt."""
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"}])
    spawner._roles = {"reviewer": _REVIEWER_ROLE}

    captured_payload = {}

    mock_resp = MagicMock()
    mock_resp.status = 201
    mock_resp.json = AsyncMock(return_value={"job_id": "job-prompt-inject", "status": "queued"})
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_resp)
    cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(200, {
        "active_jobs": 0, "queued_jobs": 0, "max_concurrency": 4,
    }))

    def capture_post(url, json=None, **kwargs):
        if json is not None:
            captured_payload.update(json)
        return cm

    mock_session.post = MagicMock(side_effect=capture_post)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "spawn_remote_session",
            {"prompt": "review this code", "working_dir": "/tmp", "role": "reviewer"},
        )

    data = _parse_response(result)
    assert data["job_id"] == "job-prompt-inject"
    expected_prompt = "[ROLE: reviewer]\nYou are a code reviewer.\n\nreview this code"
    assert captured_payload["prompt"] == expected_prompt


@pytest.mark.asyncio
async def test_spawn_remote_session_role_without_system_prompt_leaves_prompt_unchanged():
    """spawn_remote_session with a role that has no system_prompt sends the prompt unchanged."""
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"}])
    worker_role = {"name": "worker", "description": "General-purpose worker agent."}
    spawner._roles = {"worker": worker_role}

    captured_payload = {}

    mock_resp = MagicMock()
    mock_resp.status = 201
    mock_resp.json = AsyncMock(return_value={"job_id": "job-no-inject", "status": "queued"})
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_resp)
    cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(200, {
        "active_jobs": 0, "queued_jobs": 0, "max_concurrency": 4,
    }))

    def capture_post(url, json=None, **kwargs):
        if json is not None:
            captured_payload.update(json)
        return cm

    mock_session.post = MagicMock(side_effect=capture_post)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "spawn_remote_session",
            {"prompt": "do some work", "working_dir": "/tmp", "role": "worker"},
        )

    data = _parse_response(result)
    assert data["job_id"] == "job-no-inject"
    assert captured_payload["prompt"] == "do some work"


@pytest.mark.asyncio
async def test_spawn_remote_session_inline_role_dict_with_system_prompt_injects_into_prompt():
    """spawn_remote_session with inline role dict that has system_prompt prepends it to the prompt."""
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"}])

    inline_role = {"name": "custom", "system_prompt": "You are a custom agent."}
    captured_payload = {}

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(200, {
        "active_jobs": 0, "queued_jobs": 0, "max_concurrency": 4,
    }))

    def capture_post(url, json=None, **kwargs):
        if json is not None:
            captured_payload.update(json)
        return _make_mock_response(201, {"job_id": "job-inline-prompt", "status": "queued"})

    mock_session.post = MagicMock(side_effect=capture_post)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "spawn_remote_session",
            {"prompt": "the task", "working_dir": "/tmp", "role": inline_role},
        )

    data = _parse_response(result)
    assert data["job_id"] == "job-inline-prompt"
    assert captured_payload["prompt"] == "[ROLE: custom]\nYou are a custom agent.\n\nthe task"


# ---------------------------------------------------------------------------
# 25. cancel_remote_job Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_remote_job_success_with_worker_name():
    """cancel_remote_job with worker_name returns cancelled status when worker returns 204."""
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"}])

    mock_session = MagicMock()
    mock_session.delete = MagicMock(return_value=_make_mock_response(204, {}))

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "cancel_remote_job",
            {"job_id": "job-cancel-123", "worker_name": "worker-1"},
        )

    data = _parse_response(result)
    assert data["job_id"] == "job-cancel-123"
    assert data["status"] == "cancelled"
    assert data["worker_name"] == "worker-1"
    assert "error" not in data


@pytest.mark.asyncio
async def test_cancel_remote_job_409_conflict_response():
    """cancel_remote_job returns error with detail when worker returns 409."""
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"}])

    mock_session = MagicMock()
    mock_session.delete = MagicMock(
        return_value=_make_mock_response(409, {"detail": "Job already completed"})
    )

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "cancel_remote_job",
            {"job_id": "job-done-456", "worker_name": "worker-1"},
        )

    data = _parse_response(result)
    assert "error" in data
    assert data["error"] == "Job already completed"
    assert data["worker_name"] == "worker-1"


@pytest.mark.asyncio
async def test_cancel_remote_job_404_with_worker_name():
    """cancel_remote_job returns error when worker returns 404."""
    _configure_workers([{"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"}])

    mock_session = MagicMock()
    mock_session.delete = MagicMock(return_value=_make_mock_response(404, {}))

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "cancel_remote_job",
            {"job_id": "job-missing-789", "worker_name": "worker-1"},
        )

    data = _parse_response(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_cancel_remote_job_multi_worker_first_404_second_204():
    """cancel_remote_job fan-out: first worker returns 404, second returns 204; 204 result is returned."""
    _configure_workers([
        {"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"},
        {"name": "worker-2", "url": "http://worker2.example.com", "api_key": "key2"},
    ])

    def side_effect_delete(url, **kwargs):
        if "worker1" in url:
            return _make_mock_response(404, {})
        return _make_mock_response(204, {})

    mock_session = MagicMock()
    mock_session.delete = MagicMock(side_effect=side_effect_delete)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "cancel_remote_job",
            {"job_id": "job-fan-out-abc"},
        )

    data = _parse_response(result)
    assert data["status"] == "cancelled"
    assert data["job_id"] == "job-fan-out-abc"
    assert data["worker_name"] == "worker-2"
    assert "error" not in data


@pytest.mark.asyncio
async def test_cancel_remote_job_all_workers_404_returns_not_found():
    """cancel_remote_job returns not-found error when all workers return 404."""
    _configure_workers([
        {"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"},
        {"name": "worker-2", "url": "http://worker2.example.com", "api_key": "key2"},
    ])

    mock_session = MagicMock()
    mock_session.delete = MagicMock(return_value=_make_mock_response(404, {}))

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "cancel_remote_job",
            {"job_id": "job-nowhere"},
        )

    data = _parse_response(result)
    assert "error" in data
    assert "not found" in data["error"].lower()


@pytest.mark.asyncio
async def test_cancel_remote_job_no_workers_returns_error():
    """cancel_remote_job with no configured workers returns standard no-workers error."""
    _configure_workers([])

    with patch.object(spawner, '_get_http_session', return_value=MagicMock()):
        result = await spawner.call_tool(
            "cancel_remote_job",
            {"job_id": "job-abc"},
        )

    data = _parse_response(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_cancel_remote_job_exception_on_first_worker_success_on_second():
    """cancel_remote_job fan-out: exception on worker-1 is skipped; worker-2 returns 204 and is used."""
    _configure_workers([
        {"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"},
        {"name": "worker-2", "url": "http://worker2.example.com", "api_key": "key2"},
    ])

    def side_effect_delete(url, **kwargs):
        if "worker1" in url:
            raise Exception("simulated connection error")
        return _make_mock_response(204, {})

    mock_session = MagicMock()
    mock_session.delete = MagicMock(side_effect=side_effect_delete)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "cancel_remote_job",
            {"job_id": "job-exc-fanout"},
        )

    data = _parse_response(result)
    assert data["status"] == "cancelled"
    assert data["job_id"] == "job-exc-fanout"
    assert data["worker_name"] == "worker-2"
    assert "error" not in data


@pytest.mark.asyncio
async def test_cancel_remote_job_exception_on_first_worker_404_on_second():
    """cancel_remote_job fan-out: connection error on worker-1, 404 on worker-2.

    The result should indicate 'not found' (job confirmed absent on worker-2),
    NOT 'connection error' — a connection error is not definitive and must not
    mask the 404 confirmation from the reachable worker.
    """
    _configure_workers([
        {"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"},
        {"name": "worker-2", "url": "http://worker2.example.com", "api_key": "key2"},
    ])

    def side_effect_delete(url, **kwargs):
        if "worker1" in url:
            raise Exception("simulated connection error")
        return _make_mock_response(404, {})

    mock_session = MagicMock()
    mock_session.delete = MagicMock(side_effect=side_effect_delete)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "cancel_remote_job",
            {"job_id": "job-exc-404-fanout"},
        )

    data = _parse_response(result)
    assert "error" in data
    # Must be a "not found" style message — connection error must NOT cause early return
    assert "not found" in data["error"].lower()
    # Must mention both workers in the error (full picture)
    assert "worker-1" in data["error"] or "worker-2" in data["error"]


@pytest.mark.asyncio
async def test_cancel_remote_job_auth_error_on_first_worker_success_on_second():
    """cancel_remote_job fan-out: 401 on worker-1 is skipped; worker-2 returns 204 and is used."""
    _configure_workers([
        {"name": "worker-1", "url": "http://worker1.example.com", "api_key": "bad-key"},
        {"name": "worker-2", "url": "http://worker2.example.com", "api_key": "key2"},
    ])

    def side_effect_delete(url, **kwargs):
        if "worker1" in url:
            return _make_mock_response(401, {})
        return _make_mock_response(204, {})

    mock_session = MagicMock()
    mock_session.delete = MagicMock(side_effect=side_effect_delete)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "cancel_remote_job",
            {"job_id": "job-auth-fanout"},
        )

    data = _parse_response(result)
    assert data["status"] == "cancelled"
    assert data["job_id"] == "job-auth-fanout"
    assert data["worker_name"] == "worker-2"


@pytest.mark.asyncio
async def test_cancel_remote_job_fan_out_is_concurrent():
    """cancel_remote_job fan-out: cancel requests are issued concurrently via asyncio.gather.

    Proves concurrency using an asyncio.Event cross-wait: worker-1's mock sets an event
    and awaits worker-2's event before returning; worker-2 does the same. Under asyncio.gather
    both coroutines run simultaneously, set their events, and unblock each other. Under a
    sequential for-loop worker-1 would block forever waiting for worker-2's event, causing
    asyncio.wait_for to raise TimeoutError and the test to fail.
    """
    _configure_workers([
        {"name": "worker-1", "url": "http://worker1.example.com", "api_key": "key1"},
        {"name": "worker-2", "url": "http://worker2.example.com", "api_key": "key2"},
    ])

    w1_started = asyncio.Event()
    w2_started = asyncio.Event()

    async def worker1_enter():
        w1_started.set()
        await asyncio.wait_for(w2_started.wait(), timeout=2.0)
        mock_resp = MagicMock()
        mock_resp.status = 404
        mock_resp.json = AsyncMock(return_value={})
        return mock_resp

    async def worker2_enter():
        w2_started.set()
        await asyncio.wait_for(w1_started.wait(), timeout=2.0)
        mock_resp = MagicMock()
        mock_resp.status = 204
        mock_resp.json = AsyncMock(return_value={})
        return mock_resp

    cm1 = MagicMock()
    cm1.__aenter__ = AsyncMock(side_effect=worker1_enter)
    cm1.__aexit__ = AsyncMock(return_value=False)

    cm2 = MagicMock()
    cm2.__aenter__ = AsyncMock(side_effect=worker2_enter)
    cm2.__aexit__ = AsyncMock(return_value=False)

    def side_effect_delete(url, **kwargs):
        return cm1 if "worker1" in url else cm2

    mock_session = MagicMock()
    mock_session.delete = MagicMock(side_effect=side_effect_delete)

    with patch.object(spawner, '_get_http_session', return_value=mock_session):
        result = await spawner.call_tool(
            "cancel_remote_job",
            {"job_id": "job-concurrent-test"},
        )

    # The successful 204 result from worker-2 should be returned
    data = _parse_response(result)
    assert data["status"] == "cancelled"
    assert data["job_id"] == "job-concurrent-test"
    assert data["worker_name"] == "worker-2"


# ---------------------------------------------------------------------------
# Startup validation: missing api_key warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_startup_warns_when_worker_has_no_api_key(caplog):
    """_warn_missing_worker_keys emits a WARNING containing the worker name when api_key is absent."""
    import logging as _logging
    workers = [{"name": "my-worker", "url": "http://example.com"}]
    with caplog.at_level(_logging.WARNING, logger=spawner.logger.name):
        spawner._warn_missing_worker_keys(workers, spawner.logger)
    assert "my-worker" in caplog.text


@pytest.mark.asyncio
async def test_startup_warns_via_main_when_worker_has_no_api_key(caplog):
    """main() emits a WARNING via _warn_missing_worker_keys for a worker missing api_key."""
    from contextlib import asynccontextmanager
    import logging as _logging

    @asynccontextmanager
    async def _fake_stdio_server():
        # Yield dummy streams then return immediately so main() exits cleanly.
        yield (AsyncMock(), AsyncMock())

    mock_http_session = MagicMock()
    mock_http_session.close = AsyncMock()

    workers_json = json.dumps([{"name": "no-key-worker", "url": "http://example.com"}])

    with patch.dict(os.environ, {"OUTPOST_REMOTE_WORKERS": workers_json}):
        with patch("mcp.server.stdio.stdio_server", _fake_stdio_server):
            with patch("aiohttp.ClientSession", return_value=mock_http_session):
                with patch.object(spawner.server, "run", new_callable=AsyncMock):
                    with caplog.at_level(_logging.WARNING, logger=spawner.logger.name):
                        await spawner.main()

    assert "no-key-worker" in caplog.text


# ---------------------------------------------------------------------------
# WI-029. FileNotFoundError — missing claude binary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_session_file_not_found_returns_structured_error(tmp_working_dir):
    """FileNotFoundError from subprocess.run returns a structured error with exit_code=1, not a traceback."""
    with patch("subprocess.run", side_effect=FileNotFoundError("No such file or directory: 'claude'")):
        result = await spawner.call_tool(
            "spawn_session",
            {"prompt": "hello", "working_dir": tmp_working_dir},
        )

    assert len(result) == 1
    assert result[0].type == "text"
    data = json.loads(result[0].text)
    assert data["exit_code"] == 1
    assert "error" in data
    assert "claude" in data["error"]
    assert "PATH" in data["error"]
    # No raw Python traceback or exception class name
    assert "FileNotFoundError" not in data["error"]
    assert "Traceback" not in data["error"]


# ---------------------------------------------------------------------------
# NC1: spawn_remote_session — all workers unreachable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nc1_spawn_remote_session_all_workers_unreachable():
    """NC1: When all workers return non-'ok' health status, spawn_remote_session returns an error.

    With no worker_name specified, the server performs health checks and selects
    the least-loaded reachable worker. If all health checks return a non-'ok'
    status (e.g. 'unreachable'), no worker can be selected, and the response
    must contain an error field mentioning 'unreachable' or 'auth'.
    """
    spawner._remote_workers = [{"name": "w1", "url": "http://bad.example.com", "api_key": "k"}]

    async def mock_fetch_health(worker: dict) -> dict:
        return {
            "name": worker["name"],
            "url": worker["url"],
            "status": "unreachable",
            "active_jobs": None,
            "queued_jobs": None,
            "max_concurrency": None,
        }

    with patch.object(spawner, "_fetch_worker_health", side_effect=mock_fetch_health):
        result = await spawner._handle_spawn_remote_session(
            {"prompt": "do work", "working_dir": "/tmp"}
        )

    data = _parse_response(result)
    assert "error" in data
    error_text = data["error"].lower()
    assert "unreachable" in error_text or "auth" in error_text


# ---------------------------------------------------------------------------
# NC2: cancel_remote_job — mixed error + not_found results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nc2_cancel_remote_job_mixed_error_and_not_found():
    """NC2: cancel_remote_job with worker A returning connection error and worker B returning 404.

    The response must contain an error that describes both the not-found confirmation
    and the connection error, giving the caller the full picture.
    """
    spawner._remote_workers = [
        {"name": "worker-a", "url": "http://worker-a.example.com", "api_key": "key-a"},
        {"name": "worker-b", "url": "http://worker-b.example.com", "api_key": "key-b"},
    ]

    def side_effect_delete(url, **kwargs):
        if "worker-a" in url:
            # Raise an exception to produce _status='error' / connection error
            raise Exception("Connection refused")
        # worker-b: 404 not found
        return _make_mock_response(404, {})

    mock_session = MagicMock()
    mock_session.delete = MagicMock(side_effect=side_effect_delete)

    with patch.object(spawner, "_get_http_session", return_value=mock_session):
        result = await spawner._handle_cancel_remote_job({"job_id": "job-mixed-nc2"})

    data = _parse_response(result)
    assert "error" in data
    error_text = data["error"]
    # Must mention the not-found worker(s)
    assert "not found" in error_text.lower()
    # Must include connection error details
    assert "Connection refused" in error_text


# ---------------------------------------------------------------------------
# CF7: list_tools inputSchema required fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cf7_list_tools_input_schema_required_fields():
    """CF7: Each tool's inputSchema contains a 'required' key with the correct required fields.

    Verifies that:
    - spawn_session requires ['prompt', 'working_dir']
    - spawn_remote_session requires ['prompt', 'working_dir']
    - poll_remote_job requires ['job_id']
    - cancel_remote_job requires ['job_id']
    """
    tools = await spawner.list_tools()
    schema_by_name = {t.name: t.inputSchema for t in tools}

    assert "spawn_session" in schema_by_name
    assert "required" in schema_by_name["spawn_session"]
    assert set(schema_by_name["spawn_session"]["required"]) == {"prompt", "working_dir"}

    assert "spawn_remote_session" in schema_by_name
    assert "required" in schema_by_name["spawn_remote_session"]
    assert set(schema_by_name["spawn_remote_session"]["required"]) == {"prompt", "working_dir"}

    assert "poll_remote_job" in schema_by_name
    assert "required" in schema_by_name["poll_remote_job"]
    assert set(schema_by_name["poll_remote_job"]["required"]) == {"job_id"}

    assert "cancel_remote_job" in schema_by_name
    assert "required" in schema_by_name["cancel_remote_job"]
    assert set(schema_by_name["cancel_remote_job"]["required"]) == {"job_id"}
