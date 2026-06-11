"""Tests for ``_attestation.auditor_binary_sha256``.

The attestation hash is a load-bearing field of the audit report: if it
turns out to be non-deterministic or trivially forgeable, the signed audit
trail loses its meaning. These tests guard the core invariants without
hard-coding the literal value (which would have to change every time we
touch a source file).
"""

from __future__ import annotations

import re

from harness_auditor._attestation import auditor_binary_sha256
from harness_auditor.report import build_report
from harness_auditor.schemas.report_schema import CriterionResult, CriterionStatus, Severity


def _result() -> CriterionResult:
    return CriterionResult(
        criterion_id="CC-01",
        name="dummy",
        status=CriterionStatus.PASS,
        severity=Severity.LOW,
        evidence_query="// stub",
        evidence_rows=[],
        latency_ms=1.0,
        message="ok",
    )


def test_hash_shape() -> None:
    digest = auditor_binary_sha256()
    assert re.fullmatch(r"[a-f0-9]{64}", digest), digest


def test_hash_is_deterministic_within_a_process() -> None:
    assert auditor_binary_sha256() == auditor_binary_sha256()


def test_hash_is_cached_per_process() -> None:
    """B2: ``@functools.cache`` reuses the first computation.

    The same function object backs every call; ``.cache_info()`` exposes
    hit counters, which lets us assert that the second invocation does not
    walk the package tree again. Important because the auditor invokes
    this on every ``build_report`` — a CI matrix producing dozens of
    reports per process would otherwise re-hash the package each time.
    """
    auditor_binary_sha256.cache_clear()
    auditor_binary_sha256()
    auditor_binary_sha256()
    info = auditor_binary_sha256.cache_info()
    assert info.hits >= 1, info
    assert info.misses == 1, info


def test_hash_matches_frozen_baseline(repo_root) -> None:  # type: ignore[no-untyped-def]
    """C2: a release-time baseline that consumers can pin to.

    The hash is recomputed fresh on every import; if the package files
    change, the test fails. The release ritual is documented in
    ``CONTRIBUTING.md``: refresh ``tests/fixtures/_attestation_expected.txt``
    before tagging, and publish the new hash in ``CHANGELOG.md`` so
    third-party verifiers can pin the value out-of-band of the release
    artifact itself.

    Why this matters: a malicious edit to ``_attestation.py`` that returns
    a hard-coded "official" hash would otherwise go undetected; with this
    test, the malicious change either fails CI (which is the point) or
    has to be paired with a malicious edit to the frozen fixture (which is
    obvious in code review).
    """
    expected = (repo_root / "tests" / "fixtures" / "_attestation_expected.txt").read_text().strip()
    auditor_binary_sha256.cache_clear()
    actual = auditor_binary_sha256()
    assert actual == expected, (
        f"binary attestation drifted.\n"
        f"  expected (frozen): {expected}\n"
        f"  current actual   : {actual}\n"
        f"  If the change is intentional (release ritual or refactor), "
        f"refresh tests/fixtures/_attestation_expected.txt and bump "
        f"CHANGELOG.md."
    )


def test_report_carries_the_attestation() -> None:
    report = build_report(
        ontology_sha256="0" * 64,
        domain="demo",
        domain_version="1.0.0",
        criteria=[_result()],
        hmac_key_present=True,
    )
    assert report.auditor_binary_sha256 == auditor_binary_sha256()
    assert report.auditor_binary_sha256 is not None
    assert re.fullmatch(r"[a-f0-9]{64}", report.auditor_binary_sha256)
