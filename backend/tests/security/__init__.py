"""Security tests.

Per Calyxio_VOW_QA_Testing_Reporting_Strategy.pdf §1/§8: "Security —
Auth, authorization, tenant isolation, OWASP — OWASP ZAP + pytest
security tests." This directory is the pytest half only: business-logic
security scenarios — tenant isolation, authorization, approval bypass,
financial guardrails. Must fail closed. OWASP ZAP is a separate dynamic
scanner run against a live deployment, not a pytest suite — it belongs
in its own CI job/config (not yet wired; see backend/tests/README.md),
not in this directory.

Today this covers AdvertiserContextMissingError (app.core.exceptions) —
the one existing fail-closed guard, currently verified indirectly in
tests/unit/tools/test_tools.py. As real authentication (app.tools.auth)
and multi-advertiser persistence land, add: unauthenticated request,
invalid/expired credentials, cross-advertiser access, insufficient
permission, approval bypass attempts. This is also one of the Release
Quality Gate "Mandatory" checks (PDF §11: Tenant Isolation must PASS,
0 tenant-leakage findings) and a >=90% coverage target (PDF §7).

Per Exit Criteria Traceability.xlsx, "Tenant Isolation" spans API +
Integration + Security and "Approval Bypass" spans Security + Workflow
— tag tests here with `@pytest.mark.tenant_isolation` and/or
`@pytest.mark.approval_workflow` (see pyproject.toml) alongside
`@pytest.mark.security`, so the exit criterion can be collected across
directories, not just this one.
"""
