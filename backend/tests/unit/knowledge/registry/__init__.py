"""Tests for the grounded registry.

Split by the stage of the pipeline each one guards:

    test_models.py     normalization and the models - every naming conflict
                       between VOW, the mock and a trader's brief
    test_drift.py      ingest-time gating: integrity, diff, compatibility,
                       versioning
    test_ingestion.py  fetch, map and cache against MockMCPClient
    test_validate.py   the stepwise validators the graph will call

The contract-level checks (VowTools versus the mock's tool surface, enum values
versus the schema doc) live in tests/contract, because they validate an agreement
between two modules rather than one module's behaviour.
"""
