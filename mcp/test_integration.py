"""
Integration tests between session-spawner and remote-worker.

Tests use a real uvicorn server on a random port (no mocking of HTTP transport).
No actual Claude subprocess is spawned — lifespan="off" keeps jobs in "queued" state.
"""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import aiohttp
import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Module imports via importlib (directories are not importable as packages)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent


def _import_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


worker_mod = _import_module("remote_worker", ROOT / "remote-worker" / "server.py")
spawner_mod = _import_module("session_spawner", ROOT / "session-spawner" / "server.py")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def worker_server():
    """Start the remote-worker FastAPI app on a random port using uvicorn."""
    import uvicorn

    # Patch the API key getter so auth works during tests
    worker_mod._get_api_key = lambda: "test-key"

    # Clear job store between tests
    worker_mod.job_store.clear()
    # Drain any leftover queue items
    while not worker_mod.job_queue.empty():
        try:
            worker_mod.job_queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    config = uvicorn.Config(
        worker_mod.app,
        host="127.0.0.1",
        port=0,
        lifespan="off",
        log_level="warning",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    # Wait for the server to bind and be ready
    for _ in range(50):
        await asyncio.sleep(0.1)
        if server.started:
            break

    assert server.started, "uvicorn server did not start in time"

    port = server.servers[0].sockets[0].getsockname()[1]

    # Configure the spawner to point at our test worker
    spawner_mod._remote_workers = [
        {
            "name": "test-worker",
            "url": f"http://127.0.0.1:{port}",
            "api_key": "test-key",
        }
    ]

    # Load roles so the spawner knows about "reviewer"
    spawner_mod._roles = spawner_mod._load_roles()

    yield server, port

    server.should_exit = True
    await task

    # Restore
    spawner_mod._remote_workers = []
    worker_mod._get_api_key = lambda: ""
    worker_mod._max_jobs = 1000  # Reset to default to avoid cross-test pollution


@pytest_asyncio.fixture
async def http_session(worker_server):
    """Provide an aiohttp.ClientSession and inject it into the spawner module."""
    session = aiohttp.ClientSession()
    spawner_mod._http_session = session
    yield session
    await session.close()
    spawner_mod._http_session = None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _working_dir() -> str:
    """Return a directory that is guaranteed to exist (the project root)."""
    return str(ROOT.parent)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_jobs_creates_job_and_returns_job_id(http_session, worker_server):
    """AC1: POST /jobs creates a job and returns a job_id."""
    _server, port = worker_server
    url = f"http://127.0.0.1:{port}/jobs"
    payload = {
        "prompt": "hello world",
        "working_dir": _working_dir(),
    }
    async with http_session.post(
        url,
        json=payload,
        headers={"X-API-Key": "test-key"},
    ) as resp:
        assert resp.status == 201
        body = await resp.json()
        assert "job_id" in body
        assert body["job_id"]  # non-empty
        assert body["status"] == "queued"


@pytest.mark.asyncio
async def test_get_job_newly_submitted_is_queued(http_session, worker_server):
    """AC2: GET /jobs/{id} on a newly-submitted job returns status 'queued'."""
    _server, port = worker_server
    base_url = f"http://127.0.0.1:{port}"

    # Create job
    async with http_session.post(
        f"{base_url}/jobs",
        json={"prompt": "test prompt", "working_dir": _working_dir()},
        headers={"X-API-Key": "test-key"},
    ) as resp:
        assert resp.status == 201
        job_id = (await resp.json())["job_id"]

    # Poll job via MCP handler
    result = await spawner_mod._handle_poll_remote_job({"job_id": job_id})
    data = json.loads(result[0].text)
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_delete_queued_job_cancels_it(http_session, worker_server):
    """AC3: DELETE /jobs/{id} on a queued job cancels it; MCP handlers confirm 'cancelled' status."""
    _server, port = worker_server
    base_url = f"http://127.0.0.1:{port}"

    # Create job
    async with http_session.post(
        f"{base_url}/jobs",
        json={"prompt": "test prompt", "working_dir": _working_dir()},
        headers={"X-API-Key": "test-key"},
    ) as resp:
        assert resp.status == 201
        job_id = (await resp.json())["job_id"]

    # Cancel via MCP handler
    result = await spawner_mod._handle_cancel_remote_job({"job_id": job_id})
    data = json.loads(result[0].text)
    assert data["status"] == "cancelled"

    # Verify poll also returns cancelled
    poll_result = await spawner_mod._handle_poll_remote_job({"job_id": job_id})
    poll_data = json.loads(poll_result[0].text)
    assert poll_data["status"] == "cancelled"


@pytest.mark.asyncio
async def test_reviewer_role_prefixes_prompt(http_session, worker_server):
    """AC4: A job submitted with role='reviewer' stores a prompt prefixed with '[ROLE: reviewer]'."""
    _server, port = worker_server

    # Use session-spawner to dispatch with role='reviewer' and worker_name to skip health checks
    result = await spawner_mod._handle_spawn_remote_session({
        "prompt": "test task",
        "working_dir": _working_dir(),
        "role": "reviewer",
        "worker_name": "test-worker",
    })

    assert result, "Expected non-empty result from _handle_spawn_remote_session"
    result_data = json.loads(result[0].text)
    assert "error" not in result_data, f"Unexpected error: {result_data}"
    job_id = result_data["job_id"]

    # Inspect the stored job directly via worker_mod.job_store
    assert job_id in worker_mod.job_store, f"Job {job_id} not found in job_store"
    record = worker_mod.job_store[job_id]
    assert record.prompt.startswith("[ROLE: reviewer]"), (
        f"Expected prompt to start with '[ROLE: reviewer]', got: {record.prompt[:100]!r}"
    )


@pytest.mark.asyncio
async def test_get_nonexistent_job_returns_404(http_session, worker_server):
    """AC5: GET /jobs/nonexistent-id returns 404."""
    _server, port = worker_server
    async with http_session.get(
        f"http://127.0.0.1:{port}/jobs/nonexistent-id-that-does-not-exist",
        headers={"X-API-Key": "test-key"},
    ) as resp:
        assert resp.status == 404


@pytest.mark.asyncio
async def test_spawn_remote_session_wrong_key_returns_auth_error(worker_server, http_session):
    """WI-046 AC1: Wrong api_key causes _handle_spawn_remote_session to return an auth error."""
    _server, port = worker_server

    # Override spawner to use a wrong api_key for the worker
    spawner_mod._remote_workers = [
        {
            "name": "test-worker",
            "url": f"http://127.0.0.1:{port}",
            "api_key": "wrong-key",
        }
    ]

    # Use worker_name to bypass health-check selection and hit POST /jobs directly with the wrong key
    result = await spawner_mod._handle_spawn_remote_session(
        {"prompt": "hello", "working_dir": _working_dir(), "worker_name": "test-worker"}
    )

    assert result, "Expected non-empty result"
    result_text = result[0].text
    result_data = json.loads(result_text)
    assert "error" in result_data, f"Expected 'error' key in result, got: {result_data}"
    error_str = str(result_data["error"]).lower()
    assert any(
        token in error_str for token in ("auth", "401", "invalid", "key")
    ), f"Expected auth/401/invalid/key in error message, got: {result_data['error']!r}"


@pytest.mark.asyncio
async def test_spawn_remote_session_correct_key_returns_job_id(worker_server, http_session):
    """WI-046 AC2: Correct api_key causes _handle_spawn_remote_session to succeed and return a job_id."""
    result = await spawner_mod._handle_spawn_remote_session(
        {"prompt": "hello", "working_dir": _working_dir(), "worker_name": "test-worker"}
    )

    assert result, "Expected non-empty result"
    result_data = json.loads(result[0].text)
    assert "error" not in result_data, f"Unexpected error: {result_data}"
    assert "job_id" in result_data, f"Expected 'job_id' in result, got: {result_data}"
    assert result_data["job_id"], "job_id should be non-empty"
    assert result_data["status"] == "queued", f"Expected status 'queued', got: {result_data['status']!r}"


@pytest.mark.asyncio
async def test_job_lifecycle_running_to_completed(monkeypatch):
    """WI-042: A job submitted to the queue flows through an active worker coroutine to completion.

    Starts one worker coroutine explicitly (mirroring the lifespan startup path),
    monkeypatches _run_claude_job to use a trivial Python subprocess instead of the
    real `claude` binary, submits a job through put_nowait, and polls until the job
    reaches a terminal state. Verifies output, exit_code, completed_at, duration_ms.
    """
    import uuid

    TRIVIAL_OUTPUT = "integration test output"

    def _fake_run_claude_job(record):
        """Replace the claude CLI with a trivial Python one-liner."""
        import subprocess as sp
        cmd = [
            sys.executable,
            "-c",
            f"import sys; print('{TRIVIAL_OUTPUT}'); sys.exit(0)",
        ]
        proc = sp.Popen(
            cmd,
            stdout=sp.PIPE,
            stderr=sp.PIPE,
            text=True,
            cwd=record.working_dir,
        )
        if record.status == "cancelled":
            proc.kill()
            return None
        record.process = proc
        try:
            stdout, stderr = proc.communicate(timeout=30)
        finally:
            record.process = None
        error = stderr if proc.returncode != 0 else None
        return stdout, proc.returncode, error

    monkeypatch.setattr(worker_mod, "_run_claude_job", _fake_run_claude_job)

    # Reset module state
    worker_mod.job_store.clear()
    worker_mod._max_jobs = 1000
    worker_mod.job_queue = asyncio.Queue(maxsize=worker_mod._max_jobs)

    job_id = str(uuid.uuid4())
    request = worker_mod.JobRequest(
        prompt="hello",
        working_dir=_working_dir(),
    )
    record = worker_mod.JobRecord(job_id, request)

    # Start one worker coroutine explicitly (matches the lifespan startup path)
    worker_task = asyncio.create_task(worker_mod._worker(0))

    try:
        # Submit job through the queue (as submit_job endpoint does)
        worker_mod.job_queue.put_nowait(job_id)
        async with worker_mod.job_store_lock:
            worker_mod.job_store[job_id] = record

        # Poll until the job reaches a terminal state
        async def poll_until_done():
            while True:
                await asyncio.sleep(0.05)
                async with worker_mod.job_store_lock:
                    r = worker_mod.job_store.get(job_id)
                if r and r.status in ("completed", "failed"):
                    return r

        try:
            final = await asyncio.wait_for(poll_until_done(), timeout=15.0)
        except asyncio.TimeoutError:
            pytest.fail("Job did not reach a terminal state within timeout")
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    assert final.status in ("completed", "failed"), (
        f"Expected terminal status, got: {final.status!r}"
    )
    assert final.output is not None, "output should be non-None"
    assert TRIVIAL_OUTPUT in final.output, (
        f"Expected {TRIVIAL_OUTPUT!r} in output, got: {final.output!r}"
    )
    assert final.exit_code is not None, "exit_code should be non-None"
    assert final.exit_code == 0, f"Expected exit_code 0, got {final.exit_code}"
    assert final.completed_at is not None, "completed_at should be non-None"
    assert final.duration_ms is not None, "duration_ms should be non-None"
    assert final.status == "completed"


@pytest.mark.asyncio
async def test_container_mode_uses_docker_command_in_worker(monkeypatch):
    """When OUTPOST_AGENT_IMAGE is set, the worker builds a docker run command."""
    import uuid
    from unittest.mock import MagicMock

    # Activate container mode
    monkeypatch.setattr(worker_mod, "_agent_image", "outpost-agent:test")

    # Track the command passed to Popen
    captured_cmd = []

    def fake_popen(cmd, **kwargs):
        captured_cmd.extend(cmd)
        # Return a mock process that simulates successful completion
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = ('{"result": "ok"}', "")
        return mock_proc

    monkeypatch.setattr(worker_mod.subprocess, "Popen", fake_popen)

    # Reset module state (same pattern as lifecycle test)
    worker_mod.job_store.clear()
    worker_mod._max_jobs = 1000
    worker_mod.job_queue = asyncio.Queue(maxsize=worker_mod._max_jobs)

    job_id = str(uuid.uuid4())
    request = worker_mod.JobRequest(
        prompt="test container mode",
        working_dir=_working_dir(),
    )
    record = worker_mod.JobRecord(job_id, request)

    # Start one worker coroutine explicitly
    worker_task = asyncio.create_task(worker_mod._worker(0))

    try:
        worker_mod.job_queue.put_nowait(job_id)
        async with worker_mod.job_store_lock:
            worker_mod.job_store[job_id] = record

        # Poll until terminal state
        async def poll_until_done():
            while True:
                await asyncio.sleep(0.05)
                async with worker_mod.job_store_lock:
                    r = worker_mod.job_store.get(job_id)
                if r and r.status in ("completed", "failed"):
                    return r

        try:
            final = await asyncio.wait_for(poll_until_done(), timeout=10.0)
        except asyncio.TimeoutError:
            pytest.fail("Container mode job did not reach a terminal state within timeout")
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    # Verify container mode was activated: command starts with "docker"
    assert captured_cmd, "Popen was never called — worker did not process the job"
    assert captured_cmd[0] == "docker", (
        f"Expected command to start with 'docker' in container mode, got: {captured_cmd[0]!r}"
    )
    assert "run" in captured_cmd, "Expected 'run' in docker command"

    # Verify job reached completed state (mock returncode=0 always produces "completed")
    assert final.status == "completed", (
        f"Expected 'completed' (mock returncode=0), got: {final.status!r}"
    )
