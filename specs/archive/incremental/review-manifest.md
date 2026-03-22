# Review Manifest — Cycle 003 (Full Review)

Full review — all source files in scope. Reason: cycle 1 always triggers full review.

| id | title | file scope | verdict | findings (C/S/M) | review path |
|----|-------|------------|---------|------------------|-------------|
| 012 | Fix Installation Paths | .claude-plugin/plugin.json, README.md | Pass (with rework) | 0/0/1 | specs/archive/incremental/012-fix-installation-paths.md |
| 013 | Fix poll_remote_job Auth-Error Priority | mcp/session-spawner/server.py | Pass (with rework) | 0/2/1 | specs/archive/incremental/013-fix-poll-remote-job-auth-error-priority.md |
| 014 | Fix poll_remote_job Missing Timestamp Fields | mcp/session-spawner/server.py | Pass (with rework) | 0/0/2 | specs/archive/incremental/014-fix-poll-remote-job-missing-timestamp-fields.md |
| 015 | Apply Role Constraints to Remote Sessions | mcp/session-spawner/server.py, mcp/session-spawner/test_server.py | Pass | 0/0/0 | specs/archive/incremental/015-apply-role-constraints-to-remote-sessions.md |
| 016 | Update Architecture Document | specs/plan/architecture.md | Pass | 0/0/0 | specs/archive/incremental/016-update-architecture-document.md |
| 017 | Implement Running Job Cancellation | mcp/remote-worker/server.py, mcp/remote-worker/test_server.py | Pass | 0/0/0 | specs/archive/incremental/017-implement-running-job-cancellation.md |
| 028 | Fix proc.terminate() race in cancel_job | mcp/remote-worker/server.py, mcp/remote-worker/test_server.py | Pass | 0/0/0 | specs/archive/incremental/028-fix-proc-terminate-race-in-cancel-job.md |
| 029 | Handle FileNotFoundError for missing claude binary | mcp/session-spawner/server.py, mcp/remote-worker/server.py, mcp/session-spawner/test_server.py, mcp/remote-worker/test_server.py | Pass | 0/0/0 | specs/archive/incremental/029-handle-filenotfounderror-for-missing-claude-binary.md |
| 030 | Fix conftest sys.modules key collision between test suites | mcp/session-spawner/conftest.py, mcp/remote-worker/conftest.py, mcp/session-spawner/test_server.py, mcp/remote-worker/test_server.py | Pass | 0/0/0 | specs/archive/incremental/030-fix-conftest-sys-modules-key-collision.md |
| 031 | Add --cwd flag to _run_claude_job and max_jobs to list_remote_workers output | mcp/remote-worker/server.py, mcp/session-spawner/server.py, mcp/remote-worker/test_server.py, mcp/session-spawner/test_server.py | Pass (with rework) | 0/1/1 | specs/archive/incremental/031-add-cwd-flag-and-max-jobs-output.md |
| 032 | Documentation sweep (cycle 7 minor gaps) | README.md, CLAUDE.md, specs/plan/architecture.md | Pass (with rework) | 0/0/3 | specs/archive/incremental/032-documentation-sweep-cycle-7-minor-gaps.md |
| 033 | Fix cancel-while-starting race in _run_claude_job | mcp/remote-worker/server.py, mcp/remote-worker/test_server.py | Pass (with rework) | 0/2/2 | specs/archive/incremental/033-fix-cancel-while-starting-race-in-run-claude-job.md |
