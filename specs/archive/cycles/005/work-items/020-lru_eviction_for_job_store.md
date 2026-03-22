# WI-020: LRU Eviction for Job Store

## complexity
medium

## scope
['mcp/remote-worker/server.py (modify)', 'mcp/remote-worker/test_server.py (modify)']

## depends
[]

## blocks
['022']

## criteria
['IDEATE_WORKER_MAX_JOBS env var is read at startup; invalid or missing values default to 1000', 'When a job reaches terminal state and len(job_store) > max_jobs, the oldest terminal job is evicted', 'Oldest is determined by completed_at, or created_at if completed_at is None', 'Running and queued jobs are never evicted regardless of store size', "A GET request for an evicted job's ID returns 404", 'GET /health response includes max_jobs integer field showing configured limit', 'At least 2 new tests: eviction occurs when store at capacity after job completes; running/queued jobs not evicted when store exceeds max', 'All existing remote-worker tests pass']

