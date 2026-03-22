# WI-021: Integration Tests Between session-spawner and remote-worker

## complexity
hard

## scope
['mcp/test_integration.py (create)']

## depends
['018', '019']

## blocks
[]

## criteria
['Integration test file exists at mcp/test_integration.py', 'Tests run under pytest without requiring the claude CLI binary', 'Test 1: spawn_remote_session submits a job to in-process worker, returns response containing job_id string', 'Test 2: poll_remote_job retrieves job status from in-process worker, returns response containing status field', "Test 3: cancel_remote_job cancels a queued job via in-process worker, returns response with status 'cancelled'", 'Test 4: role with system_prompt — prompt received by worker contains the [ROLE: ...] prefix', 'Test 5: poll for non-existent job_id returns error response', 'All 5 tests pass under pytest']

