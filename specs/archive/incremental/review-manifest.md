# Review Manifest — Cycle 001 (New brrr Session — Full Review)

Full review — all source files in scope. Reason: cycle 1 always triggers full review.

| id | title | file scope | verdict | findings (C/S/M) | review path |
|----|-------|------------|---------|------------------|-------------|
| 043 | Fix list_jobs missing timestamp fields and submit_job store ordering (NG2, NG4) | mcp/remote-worker/server.py, mcp/remote-worker/test_server.py | Pass (with rework) | 0/0/2 | specs/archive/incremental/043-fix-list-jobs-timestamps-submit-job-ordering.md |
| 044 | Add remote-worker cancel path tests (CF2, CF3, CF5) | mcp/remote-worker/test_server.py | Pass | 0/0/1 | specs/archive/incremental/044-remote-worker-cancel-path-tests.md |
| 045 | Add session-spawner tests for NC1, NC2, and CF7 | mcp/session-spawner/test_server.py | Pass (with rework) | 0/0/1 | specs/archive/incremental/045-session-spawner-tests-nc1-nc2-cf7.md |
| 046 | Add auth coverage to integration test flows (NG3) | mcp/test_integration.py | Pass (with rework) | 0/0/1 | specs/archive/incremental/046-integration-test-auth-coverage.md |
