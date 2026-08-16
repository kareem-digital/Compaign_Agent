"""Unit tests for app/knowledge — the grounded registry and, later, RAG.

Unit rather than component per tests/unit/__init__.py's rule: the registry's
transport boundary is an MCPClient, and MockMCPClient mocks it out entirely.
Nothing here needs a running graph, a database or real HTTP.
"""
