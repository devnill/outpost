# WI-018: Propagate Role system_prompt for Remote Sessions

## complexity
easy

## scope
['mcp/session-spawner/server.py (modify)', 'mcp/session-spawner/test_server.py (modify)']

## depends
[]

## blocks
['019']

## criteria
['When spawn_remote_session is called with a named role that has a system_prompt, the prompt field in the HTTP POST body is prefixed with [ROLE: {name}]\\n{system_prompt}\\n\\n{original_prompt}', 'When the role has no system_prompt (e.g. worker role), the prompt is sent unchanged', "When role is an inline dict with system_prompt, it is injected using 'custom' as the role name", 'When role is an inline dict without system_prompt, the prompt is sent unchanged', 'When no role is specified, the prompt is sent unchanged', 'Caller-explicit allowed_tools and permission_mode still override role defaults (existing behavior preserved)', 'At least 2 new tests: named role with system_prompt injects correctly; role without system_prompt leaves prompt unchanged', 'All existing spawn_remote_session tests pass']

