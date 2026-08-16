"""Unit tests for the pure functions inside app/agent.

Unit rather than component per tests/unit/__init__.py: these cover individual
parsing helpers with no graph, no MCP client and no LLM - just text in, values
out. Node orchestration and branching live in tests/component/agent instead,
which the strategy doc classifies as "Service / Component".
"""
