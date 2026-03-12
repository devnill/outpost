"""
Tests for the outpost-remote-worker FastAPI service.

Uses httpx.AsyncClient with FastAPI's ASGITransport for in-process testing.
All subprocess.run calls are mocked to avoid real claude invocations.
"""

import asyncio
import datetime
import os
import subprocess
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

import server as worker

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
    worker.job_queue = asyncio.Queue()
    worker._max_concurrency = worker.DEFAULT_MAX_CONCURRENCY
    yield
    worker.job_store.clear()
    worker.job_queue = asyncio.Queue()


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

    def side_effect(cmd, **kwargs):
        if cmd[0] == "git":
            return _make_git_diff_process(diff=git_diff_text)
        return _make_completed_process(stdout="task done", returncode=0)

    with patch("subprocess.run", side_effect=side_effect):
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
    """GET /health returns status, version, active_jobs, queued_jobs, max_concurrency."""
    resp = await client.get("/health", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "active_jobs" in data
    assert "queued_jobs" in data
    assert "max_concurrency" in data


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
        # Call the actual function with the mock in place (subprocess.run is patched)
        if asyncio.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        return fn(*args, **kwargs)

    def fake_subprocess(cmd, **kwargs):
        if cmd[0] == "git":
            return _make_git_diff_process()
        return _make_completed_process()

    async with AsyncClient(
        transport=ASGITransport(app=worker.app), base_url="http://test"
    ) as ac:
        headers = {"X-API-Key": TEST_API_KEY}

        with patch("subprocess.run", side_effect=fake_subprocess):
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
# 11. subprocess.run is mocked — verify expected claude CLI args
# ---------------------------------------------------------------------------


async def test_subprocess_mocked_claude_args(client, auth_headers, tmp_working_dir):
    """
    Verify subprocess.run is invoked with expected claude CLI arguments.
    No real claude process is launched.
    """
    captured_cmds = []

    def record_calls(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        if cmd[0] == "git":
            return _make_git_diff_process()
        return _make_completed_process(stdout="mocked output")

    with patch("subprocess.run", side_effect=record_calls):
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


async def test_failed_job_returned_in_get(client, auth_headers, tmp_working_dir):
    """A job that exits with non-zero code has status 'failed' with error field set."""

    def side_effect(cmd, **kwargs):
        if cmd[0] == "git":
            return _make_git_diff_process()
        return _make_completed_process(
            stdout="partial output", stderr="error details", returncode=1
        )

    with patch("subprocess.run", side_effect=side_effect):
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

    def side_effect(cmd, **kwargs):
        if cmd[0] == "git":
            return subprocess.CompletedProcess(
                args=list(cmd), returncode=128, stdout="", stderr="not a git repo"
            )
        return _make_completed_process()

    with patch("subprocess.run", side_effect=side_effect):
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

    def side_effect(cmd, **kwargs):
        if cmd[0] == "git":
            return _make_git_diff_process()
        return _make_completed_process()

    with patch("subprocess.run", side_effect=side_effect):
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

    def record_calls(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        if cmd[0] == "git":
            return _make_git_diff_process()
        return _make_completed_process()

    with patch("subprocess.run", side_effect=record_calls):
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


async def test_cancel_running_job_returns_409(client, auth_headers, tmp_working_dir):
    """DELETE /jobs/{job_id} for a running job returns 409."""
    resp = await client.post(
        "/jobs",
        json={"prompt": "running", "working_dir": tmp_working_dir},
        headers=auth_headers,
    )
    job_id = resp.json()["job_id"]

    async with worker.job_store_lock:
        worker.job_store[job_id].status = "running"

    resp = await client.delete(f"/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 409


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