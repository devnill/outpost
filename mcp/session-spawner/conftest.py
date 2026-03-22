"""
Conftest for session-spawner tests.

Loads session-spawner/server.py as sys.modules['session_spawner_server'] so that
`import session_spawner_server as spawner` in test_server.py resolves to the correct module
when pytest is invoked from the project root with --import-mode=importlib.
"""
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).parent
_SERVER_PATH = _HERE / "server.py"

if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

spec = importlib.util.spec_from_file_location("session_spawner_server", _SERVER_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules["session_spawner_server"] = mod
spec.loader.exec_module(mod)
