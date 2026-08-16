"""Unit tests for `app/core`: logging, correlation context and spans.

Per tests/unit/__init__.py: pure functions, no route, no TestClient. These
modules are cross-cutting - everything else imports them - so they are tested
directly rather than through whatever happens to exercise them.
"""
