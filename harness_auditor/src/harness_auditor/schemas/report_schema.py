"""
Pydantic models for the signed audit report.

The report mirrors the structure of the AgentSave audit verdict (paper §6) so
that any downstream tool already wired to consume RAGF verdicts can also consume
auditor reports without translation. Three nested artifacts are produced:

- ``report.json`` — full structured verdict, machine-consumable.
- ``report.md``   — human-readable narrative rendered from the JSON.
- ``report.sig``  — HMAC-SHA256 over the canonical JSON, hex-encoded.

The signature reuses the audit chain HMAC pattern: each report contains the
SHA-256 of the input ontology, the SHA-256 of the auditor binary
(self-attestation), and a chained reference to the previous report (when
provided), forming an append-only ledger of certifications.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydField

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CertificationStatus(StrEnum):
    """Top-level verdict produced by the auditor.

    The semantics are fail-closed: ``REQUIRES_REVIEW`` and ``FAILED`` both block
    deployment in a CI gate context. Only ``PASSED`` permits promotion.
    """

    PASSED = "PASSED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    FAILED = "FAILED"


class CriterionStatus(StrEnum):
    """Per-criterion outcome."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"  # Criterion not applicable (e.g. CC-07 with no previous version)
    ERROR = "ERROR"  # Query execution failed; treated as FAIL by the aggregator


class Severity(StrEnum):
    """Severity of a criterion failure."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class CriterionResult(BaseModel):
    """Result of evaluating a single certification criterion."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: str = PydField(
        pattern=r"^CC-[A-Z0-9][A-Z0-9_-]*$",
        description=(
            "Stable identifier. Built-in CCs use `CC-NN` (two digits). "
            "User-registered CCs may use any uppercase alphanumeric suffix "
            "(e.g. `CC-X1`, `CC-FOO`). Collisions with built-ins are "
            "rejected at registration time."
        ),
    )
    name: str
    status: CriterionStatus
    severity: Severity
    evidence_query: str = PydField(description="The Cypher query that was executed")
    evidence_rows: list[dict[str, Any]] = PydField(
        default_factory=list,
        description="Rows returned by the evidence query (may be empty on PASS)",
    )
    latency_ms: float = PydField(ge=0)
    message: str = PydField(description="Human-readable summary of the finding")
    error: str | None = None


class Environment(BaseModel):
    """Reproducibility snapshot of the stack that produced the verdict.

    Mirrors ``auditor_version`` and ``auditor_binary_sha256`` from the
    top-level report so any consumer can read a single self-contained
    ``environment`` block to know exactly which auditor binary, Python
    runtime, Neo4j kernel, and GDS plugin combination produced a given
    verdict. ``neo4j_version`` and ``gds_version`` are ``None`` when the
    probe failed or GDS is not installed.
    """

    model_config = ConfigDict(extra="forbid")

    auditor_version: str
    auditor_binary_sha256: str = PydField(pattern=r"^[a-f0-9]{64}$")
    python_version: str = PydField(
        pattern=r"^\d+\.\d+\.\d+$",
        description="Running interpreter version (MAJOR.MINOR.MICRO).",
    )
    neo4j_version: str | None = PydField(
        default=None,
        description="Neo4j kernel version reported by `dbms.components()`.",
    )
    gds_version: str | None = PydField(
        default=None,
        description="Graph Data Science plugin version, None when GDS absent.",
    )
    platform: str = PydField(
        description="Short `system-machine` descriptor, e.g. `darwin-arm64`.",
    )


class AuditReport(BaseModel):
    """Top-level signed report."""

    model_config = ConfigDict(extra="forbid")

    # Identity & provenance
    auditor_version: str
    timestamp_utc: datetime
    ontology_sha256: str = PydField(pattern=r"^[a-f0-9]{64}$")
    auditor_binary_sha256: str | None = PydField(
        default=None,
        description="SHA-256 of the auditor binary at audit time (self-attestation).",
    )
    previous_report_sha256: str | None = PydField(
        default=None,
        description="Chains to the previous report, if any, for append-only auditing.",
    )
    environment: Environment

    # Subject
    domain: str
    domain_version: str

    # Verdict
    certification_status: CertificationStatus
    criteria: list[CriterionResult]

    # Summary
    total_criteria: int = PydField(ge=0)
    passed: int = PydField(ge=0)
    warned: int = PydField(ge=0)
    failed: int = PydField(ge=0)
    skipped: int = PydField(ge=0)
    total_latency_ms: float = PydField(ge=0)
