"""
Report · aggregate criterion results, render artifacts, sign with HMAC.

Three artifacts are written under ``reports/<ontology_sha256>/``:

  - ``report.json`` — canonical compact JSON of the ``AuditReport``.
  - ``report.md``   — Markdown narrative rendered from the report.
  - ``report.sig``  — hex HMAC-SHA256 over ``HMAC_DOMAIN_TAG + report.json``,
                      keyed by ``AUDITOR_HMAC_KEY``. Omitted when no key is
                      provided; in that case the report status is forced to
                      ``REQUIRES_REVIEW`` regardless of criterion outcomes.

Aggregation rule (see ``docs/CRITERIA.md`` §Aggregation):

  - Any blocking criterion in {FAIL, ERROR}     → FAILED
  - Else any advisory criterion in {FAIL}       → REQUIRES_REVIEW
  - Else                                         → PASSED

``SKIP`` never counts as a failure. ``WARN`` is recorded in the summary but
never blocks a PASSED verdict on its own.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness_auditor import __version__
from harness_auditor._attestation import auditor_binary_sha256
from harness_auditor._environment import platform_string, python_version
from harness_auditor.runner import AGGREGATOR_ROLE
from harness_auditor.schemas.report_schema import (
    AuditReport,
    CertificationStatus,
    CriterionResult,
    CriterionStatus,
    Environment,
)

_EVIDENCE_PREVIEW_ROWS = 5


def aggregate(criteria: list[CriterionResult]) -> CertificationStatus:
    """Compute the top-level verdict from per-criterion outcomes."""
    if any(
        c.status in (CriterionStatus.FAIL, CriterionStatus.ERROR)
        and AGGREGATOR_ROLE.get(c.criterion_id) == "blocking"
        for c in criteria
    ):
        return CertificationStatus.FAILED
    if any(
        c.status == CriterionStatus.FAIL
        and AGGREGATOR_ROLE.get(c.criterion_id) == "advisory"
        for c in criteria
    ):
        return CertificationStatus.REQUIRES_REVIEW
    return CertificationStatus.PASSED


def build_report(
    *,
    ontology_sha256: str,
    domain: str,
    domain_version: str,
    criteria: list[CriterionResult],
    hmac_key_present: bool,
    neo4j_version: str | None = None,
    gds_version: str | None = None,
) -> AuditReport:
    """Build the ``AuditReport``. Forces ``REQUIRES_REVIEW`` if no HMAC key.

    ``neo4j_version`` and ``gds_version`` are runtime probes the caller is
    expected to have run while a session was still open (see
    ``harness_auditor._environment``). They are kept as parameters rather
    than computed inside ``build_report`` so this function stays pure
    Python and can be unit-tested without a live database.

    Provenance fields (``auditor_version``, ``auditor_binary_sha256``) are
    sourced once and propagated through the ``Environment`` block; the
    top-level fields are mirrored from it so the report carries a single
    source of truth that downstream consumers can read either way.
    """
    status = aggregate(criteria)
    if not hmac_key_present:
        status = CertificationStatus.REQUIRES_REVIEW

    counts = _summarise(criteria)
    environment = Environment(
        auditor_version=__version__,
        auditor_binary_sha256=auditor_binary_sha256(),
        python_version=python_version(),
        neo4j_version=neo4j_version,
        gds_version=gds_version,
        platform=platform_string(),
    )
    return AuditReport(
        # Mirror from environment so the two values cannot drift apart
        # under refactor — see the docstring above.
        auditor_version=environment.auditor_version,
        timestamp_utc=datetime.now(UTC),
        ontology_sha256=ontology_sha256,
        auditor_binary_sha256=environment.auditor_binary_sha256,
        previous_report_sha256=None,
        environment=environment,
        domain=domain,
        domain_version=domain_version,
        certification_status=status,
        criteria=criteria,
        total_criteria=len(criteria),
        passed=counts["pass"],
        warned=counts["warn"],
        failed=counts["fail"],
        skipped=counts["skip"],
        total_latency_ms=sum(c.latency_ms for c in criteria),
    )


def _summarise(criteria: list[CriterionResult]) -> dict[str, int]:
    return {
        "pass": sum(1 for c in criteria if c.status == CriterionStatus.PASS),
        "warn": sum(1 for c in criteria if c.status == CriterionStatus.WARN),
        # ERROR is rolled into FAIL for the summary count.
        "fail": sum(
            1 for c in criteria
            if c.status in (CriterionStatus.FAIL, CriterionStatus.ERROR)
        ),
        "skip": sum(1 for c in criteria if c.status == CriterionStatus.SKIP),
    }


#: Domain-separation tag prepended to the canonical JSON bytes before HMAC.
#:
#: Without this tag, a signature produced by `harness-audit` over a report
#: would be indistinguishable in scheme from a signature produced by any
#: other tool that HMAC-SHA256s arbitrary JSON with the same key. The tag
#: cryptographically scopes the signature to "this auditor, this report
#: format, this contract version".
#:
#: Format: ``b"harness-auditor:report:v1\0"``. The trailing NUL prevents any
#: prefix-collision attack across future format versions, the version
#: counter (``v1``) is bumped any time the canonical JSON shape changes in
#: a way that consumers must be aware of.
HMAC_DOMAIN_TAG: bytes = b"harness-auditor:report:v1\0"


def hmac_signature(key: str, canonical_bytes: bytes) -> str:
    """Compute the hex HMAC-SHA256 over ``HMAC_DOMAIN_TAG + canonical_bytes``.

    Centralised so both ``write_artifacts`` (sign) and the verify command
    (re-check) use the same scheme; the domain tag is applied exactly once
    in both paths.
    """
    mac = hmac.new(key.encode("utf-8"), HMAC_DOMAIN_TAG, hashlib.sha256)
    mac.update(canonical_bytes)
    return mac.hexdigest()


def write_artifacts(
    report: AuditReport,
    reports_dir: Path,
    hmac_key: str | None,
) -> Path:
    """Write ``report.json`` (+ ``report.md``, ``report.sig``) and return the dir."""
    out_dir = reports_dir / report.ontology_sha256
    out_dir.mkdir(parents=True, exist_ok=True)

    json_bytes = canonical_json(report)
    (out_dir / "report.json").write_bytes(json_bytes)
    (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    if hmac_key:
        (out_dir / "report.sig").write_text(
            hmac_signature(hmac_key, json_bytes) + "\n", encoding="utf-8"
        )
    return out_dir


def canonical_json(report: AuditReport) -> bytes:
    """Bytes form of the report that HMAC signs. Sort keys, compact separators."""
    return json.dumps(
        report.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def render_markdown(report: AuditReport) -> str:
    """Render the report as a human-readable Markdown narrative."""
    buf = io.StringIO()
    w = buf.write

    w(f"# Audit Report · {report.domain} v{report.domain_version}\n\n")
    w(f"- **Status**: `{report.certification_status.value}`\n")
    w(f"- **Timestamp**: {report.timestamp_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
    w(f"- **Ontology SHA-256**: `{report.ontology_sha256}`\n")
    w(f"- **Auditor**: v{report.auditor_version}\n\n")

    w("## Summary\n\n")
    w("| PASS | WARN | FAIL | SKIP | Total |\n")
    w("|------|------|------|------|-------|\n")
    w(
        f"| {report.passed} | {report.warned} | {report.failed} | "
        f"{report.skipped} | {report.total_criteria} |\n\n"
    )
    w(f"Total query latency: {report.total_latency_ms:.1f} ms.\n\n")

    w("## Criteria\n\n")
    for c in report.criteria:
        w(f"### {c.criterion_id} · {c.name}\n\n")
        w(
            f"**Status**: `{c.status.value}` · "
            f"**Severity**: `{c.severity.value}` · "
            f"**Latency**: {c.latency_ms:.1f} ms\n\n"
        )
        w(f"> {c.message}\n\n")
        if c.error:
            w(f"**Error**: `{c.error}`\n\n")
        if c.evidence_rows:
            _write_evidence_block(w, c.evidence_rows)
    return buf.getvalue()


def _write_evidence_block(
    write: Callable[[str], int], rows: list[dict[str, Any]]
) -> None:
    preview = rows[:_EVIDENCE_PREVIEW_ROWS]
    elided = len(rows) - len(preview)
    write(f"<details><summary>Evidence ({len(rows)} row(s))</summary>\n\n")
    write("```json\n")
    write(json.dumps(preview, indent=2, default=str))
    write("\n```\n\n")
    if elided > 0:
        write(f"_… {elided} more row(s) elided._\n\n")
    write("</details>\n\n")
