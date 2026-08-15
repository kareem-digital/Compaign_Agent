"""Resilience tests.

Per Calyxio_VOW_QA_Testing_Reporting_Strategy.pdf §1/§8: "Resilience —
Retries, restart recovery, dependency failure — pytest + fault
injection." Scenarios from the strategy doc: Amazon timeout, database
unavailable, Redis unavailable, network timeout, worker crash,
application restart, webhook failure, duplicate messages, delayed
Amazon response. Critical assertion, repeated verbatim from the doc
because it's release-blocking: failure/retry must never accidentally
create duplicate spend.

Some of this already exists as unit-level coverage in
tests/unit/tools/test_tools.py (retry-on-500, retry-on-timeout,
give-up-after-max-retries); promote a scenario here once it needs a
real dependency (e.g. an actual restart of the checkpointer, or a
toxiproxy-style fault injection) rather than a mocked httpx client.
"""
