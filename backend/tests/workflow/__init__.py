"""Workflow tests — complete business workflows, API-driven, no browser.

Per Calyxio_VOW_QA_Testing_Reporting_Strategy.pdf §1/§4: "Workflow —
Complete business workflows — pytest + Allure." This is the backend's
counterpart to frontend/tests/e2e (Playwright/UI E2E) — same end-to-end
scope, but driven through the API/agent layer directly rather than a
browser, with Allure recording step status, duration, request/response
evidence, trace ID, expected vs. actual result, and persisted state per
step.

The reference scenario is the Golden Path (PDF §4), 21 steps:
    create test identity -> submit planning prompt -> brief completeness
    -> generate strategies -> forecast -> repair -> plan selection ->
    human approval -> discover seller capabilities -> discover products
    -> sync account -> sync creative -> create media buy -> financial
    controls -> Amazon campaign creation -> retry/idempotency ->
    retrieve campaign -> update campaign -> delivery reporting ->
    delivery intelligence -> optimisation.

Plus the negative-workflow table (PDF §5): invalid auth, cross-tenant
access, suspended account, invalid product, wrong pricing option,
missing/rejected creative, budget exceeds authority, approval rejected,
Amazon timeout/429, duplicate request, DB/audit failure (fail closed),
restart-during-submitted-task recovery, webhook failure, invalid status
transition, LLM-hallucinated ID.

Empty today: none of accounts, approvals, media buys, creatives, audit,
or financial controls exist in this codebase yet (see requirements.md
and docs/VOW_Strategy_Schema_v2.md) — there is no workflow to drive end
to end. Build this layer once those pieces land, not before.
"""
