"""Contract tests.

The schema/lifecycle-conformance slice of the PDF's "API / Protocol"
layer (§1) — same primary tools (pytest + HTTP/protocol client;
jsonschema for schema validation), kept in its own directory because it
validates protocol shape rather than endpoint behaviour: ADCP
task-lifecycle fields (single authoritative `status`, `message`,
`context_id` preserved across calls, `task_id` for submitted work — no
legacy `task_status`/`response_status` fields — per the ADCP rules in
CLAUDE_QA_INSTRUCTIONS.md), and VOW platform API request/response shapes
our adapters depend on (e.g. the paginated `{count, next, previous,
results}` envelope BaseVOWTool._get_paginated relies on).

Empty until the ADCP surface (MCP/A2A tool handlers) and
adcp-client-python integration exist — currently the repo only calls
VOW's own REST API via BaseVOWTool, not Amazon Ads or ADCP directly.
"""
