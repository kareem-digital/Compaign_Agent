"""Unit tests for `app/api` logic that is not the HTTP transport.

Per tests/unit/__init__.py: pure functions, no route, no TestClient. The route
itself is tests/api's business - `build_validation_details` is a plain state-to-DTO
mapping and belongs here, where a case can be built from a dict instead of a graph
run.
"""
