"""
Root conftest.py for the Outpost project.

Pins the installed 'mcp' package in sys.modules before pytest collection
begins. This prevents pytest's importlib mode from creating a namespace
package for the local mcp/ directory that would shadow the MCP SDK.
"""
import importlib
import sys

# Eagerly import the installed mcp package so it's cached in sys.modules
# before pytest collection can register mcp/ as a namespace package.
import mcp  # noqa: F401
import mcp.server  # noqa: F401
