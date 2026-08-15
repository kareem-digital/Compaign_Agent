"""Performance tests.

Per Calyxio_VOW_QA_Testing_Reporting_Strategy.pdf §1/§8/§12: tool is
Locust or k6 — NOT pytest. Files here are Locust locustfiles
(`locust.HttpUser` subclasses, e.g. `locustfile.py`) or k6 scripts
(`.js`), not `test_*.py` — keep that naming so pytest's default
collection doesn't pick them up as (empty) test modules.

Measure concurrency, response time, throughput, latency, token-
generation speed where applicable, CPU/memory, and SLA compliance;
track p50/p95/p99, throughput, and error rate (PDF §8, and the
Release Quality Gate "Performance" rows in §11: p95 and error rate
within SLA). e.g. VOW API pagination under large result sets, chat
endpoint latency, checkpointer read/write cost under concurrent
sessions. Should not run on every PR; gate behind a scheduled/nightly
CI job, not the default `pytest` invocation.
"""
