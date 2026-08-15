"""Compliance tests.

IMPORTANT — per Exit Criteria Traceability.xlsx ("Test Traceability
Matrix" sheet), the four release-critical exit criteria this folder
exists for are NOT single-layer concerns: they explicitly span multiple
layers.
    Financial Guardrails  -> Unit + API + Workflow + Security
    Approval Workflow     -> Unit + API + Workflow + Security
    Idempotency            -> API + Workflow + Resilience
    Tenant Isolation        -> API + Integration + Security

So the mechanics of each (a budget-boundary check, an approval-required
endpoint response, a replay-safe media-buy creation, a cross-tenant 403)
should be tested *in their natural layer* (tests/unit, tests/api,
tests/workflow, tests/security, tests/integration, tests/resilience) —
each such test should carry BOTH its layer marker and the matching
cross-cutting marker (`financial_guardrails`, `approval_workflow`,
`idempotency`, or `tenant_isolation` — see pyproject.toml), so
`pytest -m financial_guardrails` (etc.) collects the complete
cross-cutting suite for a release-gate check regardless of directory.

This directory (`tests/compliance`) is for the holistic/integrative
assertions that don't belong to one layer alone — e.g. "given a
rejected or expired approval, walk the full path and assert the Amazon
execution adapter was never called" — rather than a duplicate home for
every financial/approval/idempotency test. Assert the adapter/mock was
provably not invoked, not just that a 4xx came back.

Empty until spending-authority controls, approval persistence, and an
audit trail exist in the codebase — none of budget limits, approval
thresholds, or audit persistence are implemented yet (see
requirements.md Requirements 7-8 and VOW_Strategy_Schema_v2.md Step 7).
Once they land, the approval-boundary example from the strategy doc is
the template: budget GBP 1,000/4,999 -> no approval required, exactly
GBP 5,000 -> verify the policy boundary itself, GBP 5,001 -> approval
required, GBP 100,000 -> spending-authority violation. Coverage target
for this logic once it exists: >=95% (strategy PDF §7).
"""
