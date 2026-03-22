# WI-022: Startup Configuration Validation

## complexity
easy

## scope
['mcp/remote-worker/server.py (modify)', 'mcp/session-spawner/server.py (modify)']

## depends
['020', '024']

## blocks
[]

## criteria
["Remote-worker: when IDEATE_WORKER_API_KEY is not set at startup, a WARNING-level log message is emitted during lifespan containing 'IDEATE_WORKER_API_KEY'", 'Remote-worker: when IDEATE_WORKER_API_KEY is set, no api-key warning is emitted', 'Session-spawner: when a worker entry in OUTPOST_REMOTE_WORKERS has empty or missing api_key, a WARNING-level log message is emitted during main() containing the worker name', 'Session-spawner: when all workers have non-empty api_key values, no api_key warning is emitted', 'Neither server exits or fails at startup due to missing configuration', 'At least 1 test for remote-worker: no API key at startup emits WARNING log', 'At least 1 test for session-spawner: worker with empty api_key emits WARNING log containing worker name']

