# WI-024: Fix token_usage Null in spawn_session Normal-Path Response

## complexity
easy

## scope
['mcp/session-spawner/server.py (modify)', 'mcp/session-spawner/test_server.py (modify)']

## depends
['019']

## blocks
['022']

## criteria
["When output_format is 'text' (token extraction always fails), spawn_session response JSON includes 'token_usage': null", "When output_format is 'json' and token extraction succeeds, spawn_session response JSON includes 'token_usage': {...}", "The timeout path behavior is unchanged (still emits 'token_usage': null)", 'At least 1 new test: normal-path response with failed token extraction includes token_usage key with null value', 'All existing token_usage tests pass']

