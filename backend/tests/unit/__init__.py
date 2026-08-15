"""Unit tests.

Per Calyxio_VOW_QA_Testing_Reporting_Strategy.pdf §1: "Unit — Individual
Python/domain functions — pytest." Pure logic and adapter classes whose
own transport boundary is mocked out (e.g. httpx.AsyncClient in
tests/unit/tools/test_tools.py) — not service/node orchestration, which
is tests/component instead (LangGraph nodes are explicitly a "Component"
test per the strategy doc, not "Unit").

Example unit-level business logic once it exists (PDF §2): budget
validation, currency validation, product validation, pricing validation,
account status, permissions, approval-threshold boundaries (e.g. GBP
4,999 vs 5,000 vs 5,001), financial exposure, state transitions, error
mapping, audience-ID validation, brief completeness.

If a test needs a live database, real HTTP, or a running LangGraph
checkpointer backend, it belongs in tests/integration instead.
"""
