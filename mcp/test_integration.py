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
