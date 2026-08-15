"""Shared, non-fixture-scoped test data (sample payloads, JSON blobs).

Prefer a real pytest fixture in conftest.py or a factory in
tests/factories for anything that needs construction logic; reserve
this package for static reference data (e.g. a recorded VOW /deals/
response) imported by multiple test layers.
"""
