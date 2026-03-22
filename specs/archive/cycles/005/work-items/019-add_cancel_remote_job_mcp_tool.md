# WI-019: Add cancel_remote_job MCP Tool

## complexity
medium

## scope
['mcp/session-spawner/server.py (modify)', 'mcp/session-spawner/test_server.py (modify)']

## depends
['018']

## blocks
['021', '024']

## criteria
['cancel_remote_job appears in list_tools() response with job_id (required, string) and worker_name (optional, string)', "call_tool('cancel_remote_job', ...) dispatches to _handle_cancel_remote_job", "When worker_name is specified and worker returns 204, result JSON is {job_id, status: 'cancelled', worker_name}", "When worker_name is specified and worker returns 409, result JSON is {error: '<detail>', worker_name}", "When worker_name is specified and worker returns 404, result JSON contains 'error' key", 'When worker_name is omitted, all configured workers are tried in config order; first definitive response is returned', 'When first worker returns 404 but second returns 204, the 204 result is returned', 'When all workers return 404, result JSON contains not-found error', 'When no workers configured, returns standard no-workers error', 'At least 3 new tests: successful cancellation with worker_name; 409 conflict response; multi-worker fan-out', 'All existing tool tests pass']

