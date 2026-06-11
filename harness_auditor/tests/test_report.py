"""Aggregation rules, summary counts, and Markdown rendering."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from harness_auditor.report import (
    aggregate,
    build_report,
    canonical_json,
    render_markdown,
    write_artifacts,
)
from harness_auditor.schemas.report_schema import (
    CertificationStatus,
    CriterionResult,
    CriterionStatus,
    Severity,
)

_HEX_SHA = "a" * 64


def _r(
    criterion_id: str,
    status: CriterionStatus,
    severity: Severity = Severity.HIGH,
    rows: list[dict] | None = None,
    latency_ms: float = 1.0,
) -> CriterionResult:
    return CriterionResult(
        criterion_id=criterion_id,
        name=f"Test {criterion_id}",
        status=status,
        severity=severity,
        evidence_query="// stub",
        evidence_rows=rows or [],
        latency_ms=latency_ms,
        message="ok" if status == CriterionStatus.PASS else "fault",
    )


def test_all_pass_aggregates_to_passed() -> None:
    criteria = [
        _r("CC-01", CriterionStatus.PASS),
        _r("CC-02", CriterionStatus.PASS),
        _r("CC-04", CriterionStatus.PASS),
    ]
    assert aggregate(criteria) == CertificationStatus.PASSED


def test_any_blocking_fail_aggregates_to_failed() -> None:
    criteria = [
        _r("CC-01", CriterionStatus.FAIL),
        _r("CC-02", CriterionStatus.PASS),
    ]
    assert aggregate(criteria) == CertificationStatus.FAILED


def test_blocking_error_counts_as_blocking_fail() -> None:
    assert aggregate([_r("CC-04", CriterionStatus.ERROR)]) == CertificationStatus.FAILED


def test_skip_does_not_block_passed() -> None:
    criteria = [
        _r("CC-01", CriterionStatus.PASS),
        _r("CC-04", CriterionStatus.SKIP),
    ]
    assert aggregate(criteria) == CertificationStatus.PASSED


def test_unsigned_report_is_forced_to_requires_review() -> None:
    report = build_report(
        ontology_sha256=_HEX_SHA,
        domain="demo",
        domain_version="1.0.0",
        criteria=[_r("CC-01", CriterionStatus.PASS)],
        hmac_key_present=False,
    )
    assert report.certification_status == CertificationStatus.REQUIRES_REVIEW


def test_signed_report_reflects_real_aggregate() -> None:
    report = build_report(
        ontology_sha256=_HEX_SHA,
        domain="demo",
        domain_version="1.0.0",
        criteria=[_r("CC-01", CriterionStatus.PASS)],
        hmac_key_present=True,
    )
    assert report.certification_status == CertificationStatus.PASSED


def test_summary_counts_error_in_failed_bucket() -> None:
    report = build_report(
        ontology_sha256=_HEX_SHA,
        domain="demo",
        domain_version="1.0.0",
        criteria=[
            _r("CC-01", CriterionStatus.PASS),
            _r("CC-02", CriterionStatus.FAIL),
            _r("CC-04", CriterionStatus.ERROR),
        ],
        hmac_key_present=True,
    )
    assert report.passed == 1
    assert report.failed == 2  # FAIL + ERROR
    assert report.warned == 0
    assert report.skipped == 0
    assert report.total_criteria == 3


def test_canonical_json_is_deterministic() -> None:
    report = build_report(
        ontology_sha256=_HEX_SHA,
        domain="demo",
        domain_version="1.0.0",
        criteria=[_r("CC-01", CriterionStatus.PASS)],
        hmac_key_present=True,
    )
    a = canonical_json(report)
    b = canonical_json(report)
    assert a == b
    # Compact, sorted output: no whitespace between separators.
    assert b": " not in a
    assert b", " not in a


def test_markdown_render_contains_key_sections() -> None:
    report = build_report(
        ontology_sha256=_HEX_SHA,
        domain="demo",
        domain_version="2.3.4",
        criteria=[_r("CC-01", CriterionStatus.FAIL, rows=[{"verb": "x"}])],
        hmac_key_present=True,
    )
    md = render_markdown(report)
    assert "# Audit Report" in md
    assert "demo v2.3.4" in md
    assert "CC-01" in md
    assert "`FAIL`" in md
    assert "Evidence" in md  # evidence block emitted for non-PASS with rows


def test_write_artifacts_signs_when_key_present(tmp_path: Path) -> None:
    report = build_report(
        ontology_sha256=_HEX_SHA,
        domain="demo",
        domain_version="1.0.0",
        criteria=[_r("CC-01", CriterionStatus.PASS)],
        hmac_key_present=True,
    )
    out_dir = write_artifacts(report, tmp_path, hmac_key="testkey")

    assert (out_dir / "report.json").is_file()
    assert (out_dir / "report.md").is_file()
    assert (out_dir / "report.sig").is_file()

    json_bytes = (out_dir / "report.json").read_bytes()
    # Re-compute the signature using the same domain-separated scheme the
    # writer uses; raw HMAC over the JSON bytes is now NOT a valid
    # signature, which is the entire point of A1.
    from harness_auditor.report import HMAC_DOMAIN_TAG
    mac = hmac.new(b"testkey", HMAC_DOMAIN_TAG, hashlib.sha256)
    mac.update(json_bytes)
    expected_sig = mac.hexdigest()
    assert (out_dir / "report.sig").read_text().strip() == expected_sig

    # And the naive (no-tag) HMAC must NOT match: domain separation in action.
    naive_sig = hmac.new(b"testkey", json_bytes, hashlib.sha256).hexdigest()
    assert (out_dir / "report.sig").read_text().strip() != naive_sig

    # JSON round-trips and preserves status.
    payload = json.loads(json_bytes)
    assert payload["certification_status"] == "PASSED"


def test_write_artifacts_omits_sig_when_key_absent(tmp_path: Path) -> None:
    report = build_report(
        ontology_sha256=_HEX_SHA,
        domain="demo",
        domain_version="1.0.0",
        criteria=[_r("CC-01", CriterionStatus.PASS)],
        hmac_key_present=False,
    )
    out_dir = write_artifacts(report, tmp_path, hmac_key=None)

    assert (out_dir / "report.json").is_file()
    assert (out_dir / "report.md").is_file()
    assert not (out_dir / "report.sig").exists()
