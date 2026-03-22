# WI-027: Minor Code Hygiene

## complexity
easy

## scope
['mcp/remote-worker/__init__.py (create)', 'mcp/session-spawner/__init__.py (create)', 'mcp/remote-worker/server.py (modify)', 'mcp/test_integration.py (modify)']

## depends
[]

## blocks
[]

## criteria
['pytest mcp/ from the project root discovers all test files without import errors', 'mcp/remote-worker/server.py _evict_terminal_jobs_locked function has a comment stating it must be called while holding job_store_lock', 'mcp/test_integration.py worker_server fixture resets worker_mod._max_jobs to 1000 during teardown', 'All existing tests pass after __init__.py addition']

