"""
Tests for the outpost-remote-worker FastAPI service.

Uses httpx.AsyncClient with FastAPI's ASGITransport for in-process testing.
All subprocess.Popen calls are mocked to avoid real claude invocations.
"""

import asyncio
import datetime
import logging
import os
import subprocess
from unittest.mock import MagicMock, call, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

import remote_worker_server as worker

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_API_KEY = "test-secret-key-for-tests"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_completed_process(
    stdout: str = '{"result": "ok"}',
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _make_git_diff_process(diff: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["git", "diff", "HEAD"], returncode=0, stdout=diff, stderr=""
    )


class MockPopen:
    """Mock subprocess.Popen for testing."""

    def __init__(self, args, stdout=None, stderr=None, text=False, cwd=None, **kwargs):
        self.args = args
        self._stdout_data = ""
        self._stderr_data = ""
        self._returncode = 0
        self._text = text

        # Determine what to return based on command
        if args[0] == "claude":
            self._stdout_data = '{"result": "ok"}'
            self._stderr_data = ""
            self._returncode = 0
        elif args[0] == "git":
            self._stdout_data = ""
            self._stderr_data = ""
            self._returncode = 0

    def communicate(self, timeout=None):
        """Return (stdout, stderr) tuple."""
        return (self._stdout_data, self._stderr_data)

    @property
    def returncode(self):
        return self._returncode

    def terminate(self):
        pass

    def kill(self):
        pass

    def wait(self):
        return self._returncode


def _make_mock_popen(stdout: str = '{"result": "ok"}', stderr: str = "", returncode: int = 0):
    """Create a MockPopen class with specific return values."""
    class CustomMockPopen(MockPopen):
        def __init__(self, args, stdout=None, stderr=None, text=False, cwd=None, **kwargs):
            super().__init__(args, stdout=stdout, stderr=stderr, text=text, cwd=cwd, **kwargs)
            self._stdout_data = stdout if args[0] == "claude" else ""
            self._stderr_data = stderr if args[0] == "claude" else ""
            self._returncode = returncode if args[0] == "claude" else 0

    return CustomMockPopen


async def _execute_job(job_id: str):
    """
    Transition a queued job to running and delegate execution to worker._process_job.
    Used in tests to synchronously run a queued job without starting the
    infinite _worker coroutine.
    """
    async with worker.job_store_lock:
        record = worker.job_store.get(job_id)
        if not record or record.status != "queued":
            return
        record.status = "running"
        record.started_at = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    await worker._process_job(record)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _reset_globals():
    """Reset module-level state before each test to prevent cross-test contamination."""
    worker.job_store.clear()
    worker._max_jobs = 1000
    worker._max_concurrency = worker.DEFAULT_MAX_CONCURRENCY
    worker.job_queue = asyncio.Queue(maxsize=worker._max_jobs)
    worker._agent_image = ""
    worker._container_runtime = ""
    worker._container_memory = "4g"
    worker._container_cpus = "2"
    yield
    worker.job_store.clear()
    worker._max_jobs = 1000
    worker.job_queue = asyncio.Queue(maxsize=worker._max_jobs)
    worker._agent_image = ""
    worker._container_runtime = ""
    worker._container_memory = "4g"
    worker._container_cpus = "2"


@pytest.fixture
def api_key_env():
    """Set the API key environment variable for the duration of the test."""
    with patch.dict(os.environ, {"IDEATE_WORKER_API_KEY": TEST_API_KEY}):
        yield TEST_API_KEY


@pytest.fixture
def auth_headers():
    """Return headers dict with valid X-API-Key."""
    return {"X-API-Key": TEST_API_KEY}


@pytest_asyncio.fixture
async def client(api_key_env):
    """AsyncClient wrapping the FastAPI app (no lifespan — workers not started)."""
    async with AsyncClient(
        transport=ASGITransport(app=worker.app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def tmp_working_dir(tmp_path):
    """A real temporary directory to satisfy working_dir validation."""
    return str(tmp_path)


# ---------------------------------------------------------------------------
# 1. POST /jobs — valid request returns 201 with job_id
# ---------------------------------------------------------------------------


async def test_create_job_valid(client, auth_headers, tmp_working_dir):
    """Valid POST /jobs returns 201 with a job_id and queued status."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "hello", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert data["job_id"] in worker.job_store


# ---------------------------------------------------------------------------
# 2. POST /jobs — missing/wrong API key returns 401
# ---------------------------------------------------------------------------


async def test_create_job_missing_api_key(client, tmp_working_dir):
    """POST /jobs without X-API-Key returns 401."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "hello", "working_dir": tmp_working_dir},
    )
    assert resp.status_code == 401


async def test_create_job_wrong_api_key(client, tmp_working_dir):
    """POST /jobs with wrong X-API-Key returns 401."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "hello", "working_dir": tmp_working_dir},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401


async def test_health_missing_api_key(client):
    """GET /health without X-API-Key also returns 401 (auth applies to all routes)."""
    resp = await client.get("/health")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. POST /jobs — prompt > 100KB returns 400, no job queued
# ---------------------------------------------------------------------------


async def test_create_job_prompt_too_large(client, auth_headers, tmp_working_dir):
    """Prompt exceeding 100KB returns 400 without creating a job."""
    big_prompt = "a" * 100_001
    initial_store_size = len(worker.job_store)

    resp = await client.post(
        "/jobs",
        json={"prompt": big_prompt, "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert len(worker.job_store) == initial_store_size


async def test_create_job_prompt_exactly_at_limit(client, auth_headers, tmp_working_dir):
    """Prompt of exactly 100,000 bytes is accepted."""
    prompt_at_limit = "a" * 100_000
    resp = await client.post(
        "/jobs",
        json={"prompt": prompt_at_limit, "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# 3b. POST /jobs — queue full returns 429
# ---------------------------------------------------------------------------


async def test_create_job_queue_full_returns_429(client, auth_headers, tmp_working_dir):
    """POST /jobs returns 429 when the job queue is full."""
    # Replace the queue with a zero-capacity queue and fill it
    worker.job_queue = asyncio.Queue(maxsize=1)
    worker.job_queue.put_nowait("fake-job-id")  # fill it to capacity

    resp = await client.post(
        "/jobs",
        json={"prompt": "hello", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    assert resp.status_code == 429
    data = resp.json()
    assert "full" in data["detail"]
    # Rollback: job_store must be empty (the orphan entry was removed)
    assert len(worker.job_store) == 0


# ---------------------------------------------------------------------------
# 4. GET /jobs/{job_id} — unknown job_id returns 404
# ---------------------------------------------------------------------------


async def test_get_job_not_found(client, auth_headers):
    """GET /jobs/{job_id} for a non-existent job returns 404."""
    resp = await client.get("/jobs/nonexistent-id", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. GET /jobs/{job_id} — completed job returns output, exit_code, duration_ms, git_diff
# ---------------------------------------------------------------------------


async def test_get_completed_job(client, auth_headers, tmp_working_dir):
    """GET /jobs/{job_id} for a completed job returns output, exit_code, duration_ms, git_diff."""
    git_diff_text = "diff --git a/foo.py b/foo.py\n"

    def mock_popen_factory(cmd, stdout=None, stderr=None, text=False, cwd=None, **kwargs):
        mock = MockPopen(cmd, stdout=stdout, stderr=stderr, text=text, cwd=cwd, **kwargs)
        if cmd[0] == "git":
            mock._stdout_data = git_diff_text
            mock._returncode = 0
        elif cmd[0] == "claude":
            mock._stdout_data = "task done"
            mock._stderr_data = ""
            mock._returncode = 0
        return mock

    with patch("subprocess.Popen", side_effect=mock_popen_factory):
        resp = await client.post(
            "/jobs",
            json={"prompt": "do work", "working_dir": tmp_working_dir},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        job_id = resp.json()["job_id"]
        await _execute_job(job_id)

    resp = await client.get(f"/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["output"] == "task done"
    assert data["exit_code"] == 0
    assert data["duration_ms"] is not None
    assert isinstance(data["duration_ms"], int)
    assert "git_diff" in data


# ---------------------------------------------------------------------------
# 6. GET /jobs — returns array; newly submitted job appears in list
# ---------------------------------------------------------------------------


async def test_list_jobs_empty(client, auth_headers):
    """GET /jobs returns empty array when no jobs exist."""
    resp = await client.get("/jobs", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_jobs_contains_new_job(client, auth_headers, tmp_working_dir):
    """Newly submitted job appears in GET /jobs list."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "list me", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    job_id = resp.json()["job_id"]

    resp = await client.get("/jobs", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = [j["job_id"] for j in data]
    assert job_id in ids


# ---------------------------------------------------------------------------
# 7. DELETE /jobs/{job_id} — queued job returns 204; subsequent GET shows "cancelled"
# ---------------------------------------------------------------------------


async def test_cancel_queued_job(client, auth_headers, tmp_working_dir):
    """DELETE /jobs/{job_id} for a queued job returns 204 and marks it cancelled."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "cancel me", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    job_id = resp.json()["job_id"]

    resp = await client.delete(f"/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 204

    resp = await client.get(f"/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# 8. DELETE /jobs/{job_id} — completed job returns 409
# ---------------------------------------------------------------------------


async def test_cancel_completed_job_returns_409(client, auth_headers, tmp_working_dir):
    """DELETE /jobs/{job_id} for a completed job returns 409."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "already done", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    job_id = resp.json()["job_id"]

    async with worker.job_store_lock:
        record = worker.job_store[job_id]
        record.status = "completed"
        record.exit_code = 0
        record.output = "done"
        record.duration_ms = 100

    resp = await client.delete(f"/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 409


async def test_cancel_failed_job_returns_409(client, auth_headers, tmp_working_dir):
    """DELETE /jobs/{job_id} for a failed job returns 409."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "will fail", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    job_id = resp.json()["job_id"]

    async with worker.job_store_lock:
        record = worker.job_store[job_id]
        record.status = "failed"
        record.exit_code = 1

    resp = await client.delete(f"/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 409


async def test_cancel_nonexistent_job_returns_404(client, auth_headers):
    """DELETE /jobs/{job_id} for a non-existent job returns 404."""
    resp = await client.delete("/jobs/does-not-exist", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 9. GET /health — returns expected fields including active_jobs and queued_jobs
# ---------------------------------------------------------------------------


async def test_health_returns_expected_fields(client, auth_headers):
    """GET /health returns status, version, active_jobs, queued_jobs, max_concurrency, max_jobs."""
    resp = await client.get("/health", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "active_jobs" in data
    assert "queued_jobs" in data
    assert "max_concurrency" in data
    assert "max_jobs" in data
    assert isinstance(data["max_jobs"], int)


async def test_health_counts_queued_jobs(client, auth_headers, tmp_working_dir):
    """Health endpoint shows correct queued_jobs count after submitting jobs."""
    for i in range(2):
        await client.post(
            "/jobs",
            json={"prompt": f"job {i}", "working_dir": tmp_working_dir},
            headers=auth_headers,
        )

    resp = await client.get("/health", headers=auth_headers)
    data = resp.json()
    assert data["queued_jobs"] == 2
    assert data["active_jobs"] == 0


async def test_health_counts_active_jobs(client, auth_headers, tmp_working_dir):
    """Health endpoint shows active_jobs count for running jobs."""
    for i in range(2):
        resp = await client.post(
            "/jobs",
            json={"prompt": f"running job {i}", "working_dir": tmp_working_dir},
            headers=auth_headers,
        )
        job_id = resp.json()["job_id"]
        async with worker.job_store_lock:
            worker.job_store[job_id].status = "running"

    resp = await client.get("/health", headers=auth_headers)
    data = resp.json()
    assert data["active_jobs"] == 2


# ---------------------------------------------------------------------------
# 10. Concurrency: submitting more jobs than max_concurrency queues excess
# ---------------------------------------------------------------------------


async def test_concurrency_excess_jobs_queued(api_key_env, tmp_working_dir):
    """
    Submitting more jobs than max_concurrency results in excess jobs queued.
    The health endpoint shows the correct active_jobs count while workers are blocked.
    """
    max_concurrency = 2
    total_jobs = 4
    worker._max_concurrency = max_concurrency

    block_event = asyncio.Event()

    async def slow_to_thread(fn, *args, **kwargs):
        await block_event.wait()
        # Call the actual function with the mock in place (subprocess.Popen is patched)
        if asyncio.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        return fn(*args, **kwargs)

    def fake_popen(cmd, stdout=None, stderr=None, text=False, cwd=None, **kwargs):
        mock = MockPopen(cmd, stdout=stdout, stderr=stderr, text=text, cwd=cwd, **kwargs)
        if cmd[0] == "git":
            mock._stdout_data = ""
            mock._returncode = 0
        elif cmd[0] == "claude":
            mock._stdout_data = '{"result": "ok"}'
            mock._returncode = 0
        return mock

    async with AsyncClient(
        transport=ASGITransport(app=worker.app), base_url="http://test"
    ) as ac:
        headers = {"X-API-Key": TEST_API_KEY}

        with patch("subprocess.Popen", side_effect=fake_popen):
            with patch("asyncio.to_thread", side_effect=slow_to_thread):
                # Start worker coroutines
                worker_tasks = [
                    asyncio.create_task(worker._worker(i)) for i in range(max_concurrency)
                ]

                # Submit total_jobs jobs
                job_ids = []
                for i in range(total_jobs):
                    resp = await ac.post(
                        "/jobs",
                        json={"prompt": f"job {i}", "working_dir": tmp_working_dir},
                        headers=headers,
                    )
                    assert resp.status_code == 201
                    job_ids.append(resp.json()["job_id"])

                # Poll health endpoint until active_jobs reaches max_concurrency
                loop = asyncio.get_running_loop()
                deadline = loop.time() + 3.0
                while loop.time() < deadline:
                    await asyncio.sleep(0.05)
                    resp = await ac.get("/health", headers=headers)
                    if resp.json().get("active_jobs", 0) >= max_concurrency:
                        break

                # Check health: active should equal max_concurrency, rest queued
                resp = await ac.get("/health", headers=headers)
                data = resp.json()
                assert data["active_jobs"] == max_concurrency
                assert data["queued_jobs"] == total_jobs - max_concurrency

                # Unblock workers
                block_event.set()

                # Cancel worker tasks cleanly
                for t in worker_tasks:
                    t.cancel()
                await asyncio.gather(*worker_tasks, return_exceptions=True)
                await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# 11. subprocess.Popen is mocked — verify expected claude CLI args
# ---------------------------------------------------------------------------


async def test_subprocess_mocked_claude_args(client, auth_headers, tmp_working_dir):
    """
    Verify subprocess.Popen is invoked with expected claude CLI arguments.
    No real claude process is launched.
    """
    captured_cmds = []

    def record_calls(cmd, stdout=None, stderr=None, text=False, cwd=None, **kwargs):
        captured_cmds.append(list(cmd))
        mock = MockPopen(cmd, stdout=stdout, stderr=stderr, text=text, cwd=cwd, **kwargs)
        if cmd[0] == "git":
            mock._stdout_data = ""
            mock._returncode = 0
        elif cmd[0] == "claude":
            mock._stdout_data = "mocked output"
            mock._returncode = 0
        return mock

    with patch("subprocess.Popen", side_effect=record_calls):
        resp = await client.post(
            "/jobs",
            json={"prompt": "test prompt", "working_dir": tmp_working_dir},
            headers=auth_headers,
        )
        job_id = resp.json()["job_id"]
        await _execute_job(job_id)

    claude_calls = [c for c in captured_cmds if c[0] == "claude"]
    assert len(claude_calls) == 1
    cmd = claude_calls[0]
    assert "claude" in cmd
    assert "--print" in cmd
    assert "test prompt" in cmd
    assert "--cwd" in cmd
    cwd_index = cmd.index("--cwd")
    assert cmd[cwd_index + 1] == tmp_working_dir
    max_turns_index = cmd.index("--max-turns")
    assert cwd_index > max_turns_index + 1  # --cwd comes after --max-turns <value>


# ---------------------------------------------------------------------------
# 12. Additional edge cases
# ---------------------------------------------------------------------------


async def test_create_job_invalid_working_dir(client, auth_headers):
    """POST /jobs with a non-existent working_dir returns 400."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "hello", "working_dir": "/nonexistent/path/xyz"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_create_job_base_dir_constraint_rejected(auth_headers, tmp_path):
    """POST /jobs with working_dir outside IDEATE_WORKER_BASE_DIR returns 400."""
    base_dir = str(tmp_path / "allowed")
    os.makedirs(base_dir)
    outside_dir = str(tmp_path / "outside")
    os.makedirs(outside_dir)

    with patch.dict(
        os.environ,
        {"IDEATE_WORKER_API_KEY": TEST_API_KEY, "IDEATE_WORKER_BASE_DIR": base_dir},
    ):
        async with AsyncClient(
            transport=ASGITransport(app=worker.app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                "/jobs",
                json={"prompt": "hello", "working_dir": outside_dir},
                headers=auth_headers,
            )
    assert resp.status_code == 400


async def test_create_job_within_base_dir_accepted(auth_headers, tmp_path):
    """POST /jobs with working_dir inside IDEATE_WORKER_BASE_DIR succeeds."""
    base_dir = str(tmp_path / "allowed")
    allowed_subdir = str(tmp_path / "allowed" / "project")
    os.makedirs(allowed_subdir)

    with patch.dict(
        os.environ,
        {"IDEATE_WORKER_API_KEY": TEST_API_KEY, "IDEATE_WORKER_BASE_DIR": base_dir},
    ):
        async with AsyncClient(
            transport=ASGITransport(app=worker.app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                "/jobs",
                json={"prompt": "hello", "working_dir": allowed_subdir},
                headers=auth_headers,
            )
    assert resp.status_code == 201


async def test_create_job_container_mode_missing_api_key_returns_500(
    monkeypatch, auth_headers, tmp_path
):
    """POST /jobs returns 500 when container mode is active but ANTHROPIC_API_KEY is not set."""
    working_dir = str(tmp_path)
    monkeypatch.setattr(worker, "_agent_image", "outpost-agent:latest")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("IDEATE_WORKER_API_KEY", TEST_API_KEY)
    async with AsyncClient(
        transport=ASGITransport(app=worker.app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/jobs",
            json={"prompt": "hello", "working_dir": working_dir},
            headers=auth_headers,
        )
    assert resp.status_code == 500
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


async def test_failed_job_returned_in_get(client, auth_headers, tmp_working_dir):
    """A job that exits with non-zero code has status 'failed' with error field set."""

    def mock_popen_factory(cmd, stdout=None, stderr=None, text=False, cwd=None, **kwargs):
        mock = MockPopen(cmd, stdout=stdout, stderr=stderr, text=text, cwd=cwd, **kwargs)
        if cmd[0] == "git":
            mock._stdout_data = ""
            mock._returncode = 0
        elif cmd[0] == "claude":
            mock._stdout_data = "partial output"
            mock._stderr_data = "error details"
            mock._returncode = 1
        return mock

    with patch("subprocess.Popen", side_effect=mock_popen_factory):
        resp = await client.post(
            "/jobs",
            json={"prompt": "fail this", "working_dir": tmp_working_dir},
            headers=auth_headers,
        )
        job_id = resp.json()["job_id"]
        await _execute_job(job_id)

    resp = await client.get(f"/jobs/{job_id}", headers=auth_headers)
    data = resp.json()
    assert data["status"] == "failed"
    assert data["exit_code"] == 1
    assert data["error"] == "error details"


async def test_git_diff_null_when_not_git_repo(client, auth_headers, tmp_working_dir):
    """git_diff is None when the working_dir is not a git repository."""

    def mock_popen_factory(cmd, stdout=None, stderr=None, text=False, cwd=None, **kwargs):
        mock = MockPopen(cmd, stdout=stdout, stderr=stderr, text=text, cwd=cwd, **kwargs)
        if cmd[0] == "git":
            mock._stdout_data = ""
            mock._stderr_data = "not a git repo"
            mock._returncode = 128
        elif cmd[0] == "claude":
            mock._stdout_data = '{"result": "ok"}'
            mock._returncode = 0
        return mock

    with patch("subprocess.Popen", side_effect=mock_popen_factory):
        resp = await client.post(
            "/jobs",
            json={"prompt": "no git", "working_dir": tmp_working_dir},
            headers=auth_headers,
        )
        job_id = resp.json()["job_id"]
        await _execute_job(job_id)

    resp = await client.get(f"/jobs/{job_id}", headers=auth_headers)
    data = resp.json()
    assert data["status"] == "completed"
    assert data["git_diff"] is None


async def test_job_with_allowed_tools_stored(client, auth_headers, tmp_working_dir):
    """allowed_tools is correctly persisted in the job record."""
    resp = await client.post(
        "/jobs",
        json={
            "prompt": "use tools",
            "working_dir": tmp_working_dir,
            "allowed_tools": ["Read", "Glob"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]
    record = worker.job_store[job_id]
    assert record.allowed_tools == ["Read", "Glob"]


async def test_list_jobs_shows_duration_for_completed(client, auth_headers, tmp_working_dir):
    """GET /jobs includes duration_ms for completed jobs."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "timed job", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    job_id = resp.json()["job_id"]

    def mock_popen_factory(cmd, stdout=None, stderr=None, text=False, cwd=None, **kwargs):
        mock = MockPopen(cmd, stdout=stdout, stderr=stderr, text=text, cwd=cwd, **kwargs)
        if cmd[0] == "git":
            mock._stdout_data = ""
            mock._returncode = 0
        elif cmd[0] == "claude":
            mock._stdout_data = '{"result": "ok"}'
            mock._returncode = 0
        return mock

    with patch("subprocess.Popen", side_effect=mock_popen_factory):
        await _execute_job(job_id)

    resp = await client.get("/jobs", headers=auth_headers)
    jobs = resp.json()
    matched = [j for j in jobs if j["job_id"] == job_id]
    assert len(matched) == 1
    assert "duration_ms" in matched[0]
    assert matched[0]["duration_ms"] is not None


async def test_no_api_key_configured_returns_401(tmp_working_dir):
    """When IDEATE_WORKER_API_KEY is not set, all requests return 401."""
    env_without_key = {k: v for k, v in os.environ.items() if k != "IDEATE_WORKER_API_KEY"}
    with patch.dict(os.environ, env_without_key, clear=True):
        async with AsyncClient(
            transport=ASGITransport(app=worker.app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/health", headers={"X-API-Key": "anything"})
    assert resp.status_code == 401


async def test_get_queued_job_returns_status(client, auth_headers, tmp_working_dir):
    """GET /jobs/{job_id} for a queued job returns job_id, status=queued, created_at."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "waiting", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    job_id = resp.json()["job_id"]

    resp = await client.get(f"/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["job_id"] == job_id
    assert "created_at" in data


async def test_allowed_tools_passed_to_claude_cli(client, auth_headers, tmp_working_dir):
    """allowed_tools list is forwarded to the claude CLI via --allowedTools."""
    captured_cmds = []

    def record_calls(cmd, stdout=None, stderr=None, text=False, cwd=None, **kwargs):
        captured_cmds.append(list(cmd))
        mock = MockPopen(cmd, stdout=stdout, stderr=stderr, text=text, cwd=cwd, **kwargs)
        if cmd[0] == "git":
            mock._stdout_data = ""
            mock._returncode = 0
        elif cmd[0] == "claude":
            mock._stdout_data = '{"result": "ok"}'
            mock._returncode = 0
        return mock

    with patch("subprocess.Popen", side_effect=record_calls):
        resp = await client.post(
            "/jobs",
            json={
                "prompt": "use tools",
                "working_dir": tmp_working_dir,
                "allowed_tools": ["Read", "Edit"],
            },
            headers=auth_headers,
        )
        job_id = resp.json()["job_id"]
        await _execute_job(job_id)

    claude_calls = [c for c in captured_cmds if c[0] == "claude"]
    assert len(claude_calls) == 1
    cmd = claude_calls[0]
    assert "--allowedTools" in cmd
    idx = cmd.index("--allowedTools")
    assert cmd[idx + 1] == "Read,Edit"


# ---------------------------------------------------------------------------
# 16. DELETE /jobs/{job_id} — running job returns 409
# ---------------------------------------------------------------------------


async def test_cancel_running_job_returns_204_and_sets_cancelled(client, auth_headers, tmp_working_dir):
    """DELETE /jobs/{job_id} for a running job returns 204 and sets status to cancelled."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "running", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    job_id = resp.json()["job_id"]

    # Create a mock process that simulates a running job
    mock_proc = subprocess.Popen(
        ["sleep", "10"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    async with worker.job_store_lock:
        worker.job_store[job_id].status = "running"
        worker.job_store[job_id].process = mock_proc

    resp = await client.delete(f"/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Verify the job is marked as cancelled
    resp = await client.get(f"/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"
    assert data["completed_at"] is not None

    # Clean up the mock process
    try:
        mock_proc.kill()
        mock_proc.wait()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 17. Prompt byte validation uses UTF-8 byte length, not character count
# ---------------------------------------------------------------------------


async def test_create_job_multibyte_utf8_prompt_at_limit(client, auth_headers, tmp_working_dir):
    """Prompt with multi-byte UTF-8 chars is validated against byte length, not char count."""
    # '€' is 3 bytes in UTF-8; 33,333 × 3 = 99,999 bytes — just under the 100,000-byte limit
    prompt = "€" * 33_333
    assert len(prompt.encode("utf-8")) == 99_999
    resp = await client.post(
        "/jobs",
        json={"prompt": prompt, "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    assert resp.status_code == 201


async def test_create_job_multibyte_utf8_prompt_over_limit(client, auth_headers, tmp_working_dir):
    """Prompt with multi-byte UTF-8 chars that exceeds 100,000 bytes returns 400."""
    # 33,334 × 3 = 100,002 bytes — just over the limit
    prompt = "€" * 33_334
    assert len(prompt.encode("utf-8")) == 100_002
    resp = await client.post(
        "/jobs",
        json={"prompt": prompt, "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 18. LRU eviction
# ---------------------------------------------------------------------------


async def test_eviction_occurs_when_store_at_capacity(client, auth_headers, tmp_working_dir):
    """
    When the job store is at capacity and a job reaches terminal state, the oldest
    terminal job is evicted so the store size stays at or below _max_jobs.
    """
    worker._max_jobs = 2

    def mock_popen_factory(cmd, stdout=None, stderr=None, text=False, cwd=None, **kwargs):
        mock = MockPopen(cmd, stdout=stdout, stderr=stderr, text=text, cwd=cwd, **kwargs)
        if cmd[0] == "git":
            mock._returncode = 0
        elif cmd[0] == "claude":
            mock._stdout_data = '{"result": "ok"}'
            mock._returncode = 0
        return mock

    # Submit and complete 3 jobs sequentially; after the 3rd completes, the oldest
    # should be evicted since max_jobs=2.
    job_ids = []
    with patch("subprocess.Popen", side_effect=mock_popen_factory):
        for i in range(3):
            resp = await client.post(
                "/jobs",
                json={"prompt": f"job {i}", "working_dir": tmp_working_dir},
                headers=auth_headers,
            )
            assert resp.status_code == 201
            job_id = resp.json()["job_id"]
            job_ids.append(job_id)
            await _execute_job(job_id)

    # Store must not exceed max_jobs
    assert len(worker.job_store) <= worker._max_jobs

    # The oldest completed job (job_ids[0]) should have been evicted
    resp = await client.get(f"/jobs/{job_ids[0]}", headers=auth_headers)
    assert resp.status_code == 404

    # The two most recent jobs should still be present
    for job_id in job_ids[1:]:
        resp = await client.get(f"/jobs/{job_id}", headers=auth_headers)
        assert resp.status_code == 200


async def test_running_and_queued_jobs_not_evicted_when_store_exceeds_max(
    client, auth_headers, tmp_working_dir
):
    """
    Running and queued jobs are never evicted regardless of store size exceeding max_jobs.
    """
    worker._max_jobs = 1

    # Add a completed job (acts as the eviction candidate)
    resp = await client.post(
        "/jobs",
        json={"prompt": "completed job", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    completed_id = resp.json()["job_id"]
    async with worker.job_store_lock:
        r = worker.job_store[completed_id]
        r.status = "completed"
        r.completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")

    # Add a queued job — store is now 2 which exceeds max_jobs=1
    resp = await client.post(
        "/jobs",
        json={"prompt": "queued job", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    queued_id = resp.json()["job_id"]

    # Manually trigger eviction (simulating what would happen on a subsequent terminal transition)
    async with worker.job_store_lock:
        worker._evict_terminal_jobs_locked()

    # Queued job must still exist
    resp = await client.get(f"/jobs/{queued_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"

    # The completed job should have been evicted (it was the terminal one)
    resp = await client.get(f"/jobs/{completed_id}", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 19. IDEATE_WORKER_MAX_JOBS env var is read at startup via lifespan
# ---------------------------------------------------------------------------


async def test_lifespan_sets_max_jobs_from_env(api_key_env):
    """Lifespan reads IDEATE_WORKER_MAX_JOBS and sets _max_jobs accordingly."""
    with patch.dict(os.environ, {"IDEATE_WORKER_MAX_JOBS": "50"}):
        async with worker.lifespan(worker.app):
            assert worker._max_jobs == 50


# ---------------------------------------------------------------------------
# 20. GET /jobs — timestamp fields in list response
# ---------------------------------------------------------------------------


async def test_list_jobs_completed_has_started_at_and_completed_at(
    client, auth_headers, tmp_working_dir
):
    """GET /jobs includes started_at and completed_at for completed jobs."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "timestamps test", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    job_id = resp.json()["job_id"]

    def mock_popen_factory(cmd, stdout=None, stderr=None, text=False, cwd=None, **kwargs):
        mock = MockPopen(cmd, stdout=stdout, stderr=stderr, text=text, cwd=cwd, **kwargs)
        if cmd[0] == "git":
            mock._returncode = 0
        elif cmd[0] == "claude":
            mock._stdout_data = '{"result": "ok"}'
            mock._returncode = 0
        return mock

    with patch("subprocess.Popen", side_effect=mock_popen_factory):
        await _execute_job(job_id)

    resp = await client.get("/jobs", headers=auth_headers)
    jobs = resp.json()
    matched = [j for j in jobs if j["job_id"] == job_id]
    assert len(matched) == 1
    entry = matched[0]
    assert entry["status"] == "completed"
    assert "started_at" in entry, "completed job must have started_at in list response"
    assert entry["started_at"] is not None
    assert "completed_at" in entry, "completed job must have completed_at in list response"
    assert entry["completed_at"] is not None


async def test_list_jobs_running_has_started_at_but_no_completed_at(
    client, auth_headers, tmp_working_dir
):
    """GET /jobs includes started_at for running jobs but omits completed_at."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "running timestamps", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    job_id = resp.json()["job_id"]

    # Manually transition to running state with a known started_at
    async with worker.job_store_lock:
        record = worker.job_store[job_id]
        record.status = "running"
        record.started_at = "2026-01-01T00:00:00.000Z"

    resp = await client.get("/jobs", headers=auth_headers)
    jobs = resp.json()
    matched = [j for j in jobs if j["job_id"] == job_id]
    assert len(matched) == 1
    entry = matched[0]
    assert entry["status"] == "running"
    assert "started_at" in entry, "running job must have started_at in list response"
    assert entry["started_at"] == "2026-01-01T00:00:00.000Z"
    assert "completed_at" not in entry, "running job must not have completed_at in list response"


async def test_lifespan_max_jobs_invalid_value_falls_back_to_default(api_key_env):
    """Lifespan falls back to 1000 when IDEATE_WORKER_MAX_JOBS is not a valid integer."""
    with patch.dict(os.environ, {"IDEATE_WORKER_MAX_JOBS": "bad"}):
        async with worker.lifespan(worker.app):
            assert worker._max_jobs == 1000


# ---------------------------------------------------------------------------
# 21. Startup warns when IDEATE_WORKER_API_KEY is not set
# ---------------------------------------------------------------------------


async def test_startup_warns_when_no_api_key(caplog, tmp_working_dir):
    """Lifespan emits a WARNING containing 'IDEATE_WORKER_API_KEY' and '401' when no API key is set."""
    with patch.dict(os.environ, {}, clear=False):
        # Ensure the key is absent
        os.environ.pop("IDEATE_WORKER_API_KEY", None)
        with caplog.at_level(logging.WARNING, logger="outpost-remote-worker"):
            async with worker.lifespan(worker.app):
                pass
    assert "IDEATE_WORKER_API_KEY" in caplog.text


# ---------------------------------------------------------------------------
# 21. Cancel-while-starting race: cancel arrives after Popen but before process assigned
# ---------------------------------------------------------------------------


def test_cancel_while_starting_kills_process_and_returns_none(tmp_working_dir):
    """
    If record.status is 'cancelled' when _run_claude_job checks after Popen returns,
    the new process must be killed and the function must return None without overwriting
    the cancelled status.
    """
    from unittest.mock import MagicMock, patch as mock_patch

    request = worker.JobRequest(prompt="race", working_dir=tmp_working_dir)
    record = worker.JobRecord("test-race-job", request)
    # Simulate: cancel arrived while status was 'running' but before process was assigned
    record.status = "cancelled"

    mock_proc = MagicMock()

    with mock_patch("subprocess.Popen", return_value=mock_proc):
        result = worker._run_claude_job(record)

    mock_proc.kill.assert_called_once()
    assert result is None
    assert record.status == "cancelled"
    # completed_at is set by _process_job (not _run_claude_job) so it is None here
    assert record.completed_at is None


# ---------------------------------------------------------------------------
# 22. cancel_job race: process exits before terminate() is called
# ---------------------------------------------------------------------------


async def test_cancel_running_job_process_already_exited_returns_204(
    client, auth_headers, tmp_working_dir
):
    """
    DELETE /jobs/{id} returns 204 (not 500) when the process exits naturally
    between lock release and proc.terminate() — simulated by setting
    terminate.side_effect = ProcessLookupError on the mock.
    """
    from unittest.mock import MagicMock

    resp = await client.post(
        "/jobs",
        json={"prompt": "race condition", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    # Build a mock process whose terminate() raises ProcessLookupError to
    # simulate the subprocess having already exited.
    mock_popen = MagicMock()
    mock_popen.terminate.side_effect = ProcessLookupError
    mock_popen.wait.return_value = 0

    async with worker.job_store_lock:
        worker.job_store[job_id].status = "running"
        worker.job_store[job_id].process = mock_popen

    resp = await client.delete(f"/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Job must be marked cancelled despite the ProcessLookupError
    resp = await client.get(f"/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# WI-029. FileNotFoundError — missing claude binary
# ---------------------------------------------------------------------------


async def test_run_claude_job_file_not_found_marks_job_failed(client, auth_headers, tmp_working_dir):
    """FileNotFoundError from subprocess.Popen marks the job as failed with an actionable error message."""
    with patch("subprocess.Popen", side_effect=FileNotFoundError("No such file or directory: 'claude'")):
        resp = await client.post(
            "/jobs",
            json={"prompt": "hello", "working_dir": tmp_working_dir},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        job_id = resp.json()["job_id"]
        await _execute_job(job_id)

    resp = await client.get(f"/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["exit_code"] == 1
    assert "error" in data
    assert data["error"] is not None
    assert "claude" in data["error"]
    assert "PATH" in data["error"]
    # No raw Python traceback or exception class name
    assert "FileNotFoundError" not in data["error"]
    assert "Traceback" not in data["error"]
    assert data["completed_at"] is not None


def test_capture_git_diff_timeout_kills_process_and_returns_none(tmp_path):
    """_capture_git_diff kills and reaps the subprocess on TimeoutExpired, then returns None."""
    mock_proc = MagicMock()
    # First communicate() call raises TimeoutExpired; second (after kill) returns normally.
    mock_proc.communicate.side_effect = [
        subprocess.TimeoutExpired(cmd=["git", "diff", "HEAD"], timeout=30),
        ("", ""),
    ]

    with patch("subprocess.Popen", return_value=mock_proc):
        result = worker._capture_git_diff(str(tmp_path))

    assert result is None
    # Verify kill-before-communicate ordering and call counts
    assert mock_proc.mock_calls == [
        call.communicate(timeout=30),
        call.kill(),
        call.communicate(),
    ]


# ---------------------------------------------------------------------------
# WI-044. Cancel path tests: CF2, CF3, CF5
# ---------------------------------------------------------------------------


async def test_cf2_worker_skips_cancelled_queued_job(tmp_working_dir):
    """
    CF2: Worker skips a job that was cancelled while still in the queue.

    When a job record has status='cancelled' at the time the worker dequeues it,
    _process_job must NOT be called and the record must retain status='cancelled'.
    """
    with patch.dict(os.environ, {"IDEATE_WORKER_API_KEY": TEST_API_KEY}):
        request = worker.JobRequest(prompt="cancel-while-queued", working_dir=tmp_working_dir)
        job_id = "cf2-test-job-id"
        record = worker.JobRecord(job_id, request)
        record.status = "cancelled"

        worker.job_store[job_id] = record
        worker.job_queue.put_nowait(job_id)

        with patch.object(worker, "_process_job") as mock_process_job:
            task = asyncio.create_task(worker._worker(0))
            await asyncio.sleep(0.05)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        mock_process_job.assert_not_called()
        assert worker.job_store[job_id].status == "cancelled"


async def test_cf3_process_job_cancel_while_starting_sentinel(tmp_working_dir):
    """
    CF3: _process_job handles the cancel-while-starting sentinel (None from _run_claude_job).

    When _run_claude_job returns None (cancel-while-starting), _process_job must
    set duration_ms but must NOT set completed_at, must NOT change status away from
    'cancelled', and must NOT set exit_code.
    """
    request = worker.JobRequest(prompt="cancel-while-starting", working_dir=tmp_working_dir)
    job_id = "cf3-test-job-id"
    record = worker.JobRecord(job_id, request)
    record.status = "cancelled"

    worker.job_store[job_id] = record

    with patch.object(worker, "_run_claude_job", return_value=None):
        await worker._process_job(record)

    assert record.duration_ms is not None
    assert record.status == "cancelled"
    assert record.completed_at is None
    assert record.exit_code is None


async def test_cf5_cancel_running_job_kill_after_terminate_timeout(client, auth_headers, tmp_working_dir):
    """
    CF5: cancel_job calls proc.kill() after proc.wait() exceeds 2s timeout.

    When terminate() succeeds but wait() does not return within 2s,
    the cancel_job endpoint must call proc.kill() and still return 204.
    """
    resp = await client.post(
        "/jobs",
        json={"prompt": "long running", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    mock_proc = MagicMock()
    mock_proc.terminate.return_value = None
    mock_proc.wait.return_value = 0

    async with worker.job_store_lock:
        worker.job_store[job_id].status = "running"
        worker.job_store[job_id].process = mock_proc

    with patch.object(worker.asyncio, "wait_for", side_effect=asyncio.TimeoutError):
        resp = await client.delete(f"/jobs/{job_id}", headers=auth_headers)

    assert resp.status_code == 204
    mock_proc.terminate.assert_called_once()
    mock_proc.kill.assert_called_once()


# ---------------------------------------------------------------------------
# WI-049. Containerized job execution
# ---------------------------------------------------------------------------


def _make_job_record(tmp_working_dir, permission_mode="acceptEdits"):
    """Create a JobRecord directly for use in synchronous _run_claude_job tests."""
    request = worker.JobRequest(
        prompt="test prompt",
        working_dir=tmp_working_dir,
        permission_mode=permission_mode,
    )
    return worker.JobRecord("test-job-id", request)


def _make_mock_proc(returncode=0, stdout='{"result": "ok"}', stderr=""):
    """Create a mock subprocess.Popen return value."""
    mock_proc = MagicMock()
    mock_proc.returncode = returncode
    mock_proc.communicate.return_value = (stdout, stderr)
    return mock_proc


def test_container_mode_uses_docker_run(tmp_path, monkeypatch):
    """
    When _agent_image is set, the command passed to subprocess.Popen starts with
    'docker' and includes 'run' (not 'claude' as the first element).
    """
    monkeypatch.setattr(worker, "_agent_image", "outpost-agent:latest")
    record = _make_job_record(str(tmp_path))

    mock_proc = _make_mock_proc()
    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        worker._run_claude_job(record)

    cmd = mock_popen.call_args[0][0]
    assert cmd[0] == "docker", f"Expected 'docker' as first element, got {cmd[0]!r}"
    assert "run" in cmd, "'run' must be in the command list"
    assert cmd[0] != "claude", "Must not use 'claude' as first element in container mode"


def test_container_mode_includes_security_opts(tmp_path, monkeypatch):
    """
    Container invocation includes '--cap-drop', 'ALL', '--security-opt', and
    'no-new-privileges' in the command list.
    """
    monkeypatch.setattr(worker, "_agent_image", "outpost-agent:latest")
    record = _make_job_record(str(tmp_path))

    mock_proc = _make_mock_proc()
    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        worker._run_claude_job(record)

    cmd = mock_popen.call_args[0][0]
    assert "--cap-drop" in cmd, "'--cap-drop' must be in the command"
    cap_drop_index = cmd.index("--cap-drop")
    assert cmd[cap_drop_index + 1] == "ALL", f"Expected 'ALL' after '--cap-drop', got {cmd[cap_drop_index + 1]!r}"
    assert "--security-opt" in cmd, "'--security-opt' must be in the command"
    security_opt_index = cmd.index("--security-opt")
    assert cmd[security_opt_index + 1] == "no-new-privileges", (
        f"Expected 'no-new-privileges' after '--security-opt', got {cmd[security_opt_index + 1]!r}"
    )


def test_container_mode_includes_bind_mount(tmp_path, monkeypatch):
    """
    Container invocation includes '-v {working_dir}:/workspace' as a bind mount argument.
    """
    monkeypatch.setattr(worker, "_agent_image", "outpost-agent:latest")
    working_dir = str(tmp_path)
    record = _make_job_record(working_dir)

    mock_proc = _make_mock_proc()
    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        worker._run_claude_job(record)

    cmd = mock_popen.call_args[0][0]
    assert "-v" in cmd, "'-v' must be in the command for bind mount"
    v_index = cmd.index("-v")
    expected_mount = f"{working_dir}:/workspace"
    assert cmd[v_index + 1] == expected_mount, (
        f"Expected bind mount '{expected_mount}', got '{cmd[v_index + 1]}'"
    )


def test_container_mode_uses_dangerously_skip_permissions(tmp_path, monkeypatch):
    """
    Container invocation uses '--permission-mode dangerouslySkipPermissions' regardless
    of the value in record.permission_mode.
    """
    monkeypatch.setattr(worker, "_agent_image", "outpost-agent:latest")
    # Set a different permission_mode on the record to verify it is overridden
    record = _make_job_record(str(tmp_path), permission_mode="acceptEdits")

    mock_proc = _make_mock_proc()
    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        worker._run_claude_job(record)

    cmd = mock_popen.call_args[0][0]
    assert "--permission-mode" in cmd, "'--permission-mode' must be in the command"
    pm_index = cmd.index("--permission-mode")
    assert cmd[pm_index + 1] == "dangerouslySkipPermissions", (
        f"Expected 'dangerouslySkipPermissions', got {cmd[pm_index + 1]!r}"
    )


def test_no_container_mode_uses_claude(tmp_path, monkeypatch):
    """
    When _agent_image is NOT set, the command passed to subprocess.Popen starts
    with 'claude' (backward compatibility).
    """
    monkeypatch.setattr(worker, "_agent_image", "")
    record = _make_job_record(str(tmp_path))

    mock_proc = _make_mock_proc()
    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        worker._run_claude_job(record)

    cmd = mock_popen.call_args[0][0]
    assert cmd[0] == "claude", f"Expected 'claude' as first element, got {cmd[0]!r}"


def test_container_mode_custom_runtime(tmp_path, monkeypatch):
    """
    When OUTPOST_CONTAINER_RUNTIME is set to 'runsc', the container invocation
    includes '--runtime' and 'runsc' in the command list.
    """
    monkeypatch.setattr(worker, "_agent_image", "outpost-agent:latest")
    monkeypatch.setattr(worker, "_container_runtime", "runsc")
    record = _make_job_record(str(tmp_path))

    mock_proc = _make_mock_proc()
    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        worker._run_claude_job(record)

    cmd = mock_popen.call_args[0][0]
    assert "--runtime" in cmd, "'--runtime' must be in the command when runtime is set"
    runtime_index = cmd.index("--runtime")
    assert cmd[runtime_index + 1] == "runsc", (
        f"Expected 'runsc' as runtime value, got {cmd[runtime_index + 1]!r}"
    )


# ---------------------------------------------------------------------------
# WI-054. Cancel path: docker stop called when container_name is set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_running_container_job_calls_docker_stop(monkeypatch, tmp_path):
    """cancel_job issues docker stop when container_name is set on a running job."""
    import uuid

    job_id = str(uuid.uuid4())
    container_name = f"job-{job_id}"

    # Create a running job with container_name set
    req = worker.JobRequest(prompt="test", working_dir=str(tmp_path))
    record = worker.JobRecord(job_id, req)
    record.status = "running"
    record.container_name = container_name

    # Mock process: terminate() and wait() must not raise
    mock_proc = MagicMock()
    mock_proc.wait.return_value = None  # called via asyncio.to_thread(proc.wait)
    record.process = mock_proc

    async with worker.job_store_lock:
        worker.job_store[job_id] = record

    # Capture subprocess.run calls (called via asyncio.to_thread in cancel_job)
    docker_stop_calls = []

    def fake_subprocess_run(cmd, **kwargs):
        docker_stop_calls.append(list(cmd))
        return MagicMock(returncode=0)

    monkeypatch.setattr(worker.subprocess, "run", fake_subprocess_run)

    try:
        with patch.dict(os.environ, {"IDEATE_WORKER_API_KEY": TEST_API_KEY}):
            async with AsyncClient(
                transport=ASGITransport(app=worker.app), base_url="http://test"
            ) as ac:
                response = await ac.delete(
                    f"/jobs/{job_id}",
                    headers={"X-API-Key": TEST_API_KEY},
                )
        assert response.status_code == 204

        # Verify docker stop was called with the correct container name
        assert docker_stop_calls == [["docker", "stop", container_name]], (
            f"Expected docker stop {container_name!r} call, got: {docker_stop_calls}"
        )
    finally:
        async with worker.job_store_lock:
            worker.job_store.pop(job_id, None)