# WI-025: Fix Integration Tests to Exercise MCP Tool Layer

## complexity
easy

## scope
['mcp/test_integration.py (modify)']

## depends
[]

## blocks
[]

## criteria
['test_get_job_newly_submitted_is_queued calls spawner_mod._handle_poll_remote_job instead of http_session.get', 'test_delete_queued_job_cancels_it calls spawner_mod._handle_cancel_remote_job instead of http_session.delete', 'Both tests assert on the parsed MCP response structure (not raw HTTP status codes)', 'All 5 integration tests still pass']

