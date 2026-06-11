"""Tests for the ``harness-audit verify`` subcommand.

The command is exercised via Typer's ``CliRunner`` so we cover the full
exit-code contract (0 on valid signature, 1 on mismatch, 2 on missing
inputs) and the user-facing diagnostics.

All tests use ``monkeypatch.setenv("AUDITOR_HMAC_KEY", ...)`` to inject
the key — the CLI deliberately does NOT accept the key on the command
line because it would leak via ``ps(1)`` and shell history.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_auditor._attestation import auditor_binary_sha256
from harness_auditor.cli import app
from harness_auditor.report import build_report, hmac_signature, write_artifacts
from harness_auditor.schemas.report_schema import (
    CriterionResult,
    CriterionStatus,
    Severity,
)

KEY = "test-key-not-for-production"


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


def _write_signed_report(tmp_path: Path, key: str = KEY) -> Path:
    report = build_report(
        ontology_sha256="0" * 64,
        domain="demo",
        domain_version="1.0.0",
        criteria=[_result()],
        hmac_key_present=True,
    )
    return write_artifacts(report, tmp_path, hmac_key=key)


def _write_unsigned_report(tmp_path: Path) -> Path:
    report = build_report(
        ontology_sha256="0" * 64,
        domain="demo",
        domain_version="1.0.0",
        criteria=[_result()],
        hmac_key_present=False,
    )
    return write_artifacts(report, tmp_path, hmac_key=None)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def with_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Inject AUDITOR_HMAC_KEY into the env and return its value."""
    monkeypatch.setenv("AUDITOR_HMAC_KEY", KEY)
    return KEY


def test_verify_accepts_valid_signature(
    runner: CliRunner, tmp_path: Path, with_key: str
) -> None:
    report_dir = _write_signed_report(tmp_path)
    result = runner.invoke(app, ["verify", str(report_dir)])
    assert result.exit_code == 0, result.stdout
    assert "OK" in result.stdout
    assert "valid for" in result.stdout


def test_verify_rejects_wrong_key(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_dir = _write_signed_report(tmp_path)
    monkeypatch.setenv("AUDITOR_HMAC_KEY", "wrong-key")
    result = runner.invoke(app, ["verify", str(report_dir)])
    assert result.exit_code == 1, result.stdout
    assert "signature mismatch" in result.stdout.lower()


def test_verify_rejects_tampered_json(
    runner: CliRunner, tmp_path: Path, with_key: str
) -> None:
    report_dir = _write_signed_report(tmp_path)
    json_path = report_dir / "report.json"
    payload = json.loads(json_path.read_bytes())
    # Surgical tamper: flip the domain name.
    payload["domain"] = "compromised"
    json_path.write_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )

    result = runner.invoke(app, ["verify", str(report_dir)])
    assert result.exit_code == 1, result.stdout
    assert "signature mismatch" in result.stdout.lower()


def test_verify_errors_when_unsigned(
    runner: CliRunner, tmp_path: Path, with_key: str
) -> None:
    report_dir = _write_unsigned_report(tmp_path)
    result = runner.invoke(app, ["verify", str(report_dir)])
    assert result.exit_code == 2, result.stdout
    assert "report.sig not found" in result.stdout
    # Hint mentions the unsigned-by-policy interpretation.
    assert "REQUIRES_REVIEW" in result.stdout or "unsigned" in result.stdout.lower()


def test_verify_errors_when_key_missing(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_dir = _write_signed_report(tmp_path)
    monkeypatch.delenv("AUDITOR_HMAC_KEY", raising=False)
    result = runner.invoke(app, ["verify", str(report_dir)])
    assert result.exit_code == 2, result.stdout
    # Diagnostic names the env var and explains why no CLI flag exists.
    assert "AUDITOR_HMAC_KEY" in result.stdout
    assert "ps(1)" in result.stdout or "shell history" in result.stdout


def test_verify_errors_when_dir_missing(
    runner: CliRunner, tmp_path: Path, with_key: str
) -> None:
    missing = tmp_path / "does_not_exist"
    result = runner.invoke(app, ["verify", str(missing)])
    assert result.exit_code == 2, result.stdout
    assert "report directory not found" in result.stdout


def test_verify_errors_when_report_json_missing(
    runner: CliRunner, tmp_path: Path, with_key: str
) -> None:
    report_dir = _write_signed_report(tmp_path)
    (report_dir / "report.json").unlink()
    result = runner.invoke(app, ["verify", str(report_dir)])
    assert result.exit_code == 2, result.stdout
    assert "report.json not found" in result.stdout


def test_verify_warns_on_binary_drift(
    runner: CliRunner, tmp_path: Path, with_key: str
) -> None:
    """When auditor_binary_sha256 in report != current install, warn."""
    report_dir = _write_signed_report(tmp_path)
    # Patch the report payload to claim a different binary hash, then re-sign
    # so the HMAC stays valid (the drift check is independent of signature).
    json_path = report_dir / "report.json"
    sig_path = report_dir / "report.sig"
    payload = json.loads(json_path.read_bytes())
    payload["auditor_binary_sha256"] = "f" * 64  # bogus but well-formed
    new_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    json_path.write_bytes(new_bytes)
    # Re-sign with the same domain-separated scheme the auditor uses, so the
    # HMAC matches the tampered payload and we reach the drift branch.
    sig_path.write_text(hmac_signature(KEY, new_bytes) + "\n", encoding="utf-8")

    result = runner.invoke(app, ["verify", str(report_dir)])
    assert result.exit_code == 0, result.stdout  # signature is valid
    assert "different auditor binary" in result.stdout.lower() or "DIFFERENT" in result.stdout
    assert "f" * 64 in result.stdout
    assert auditor_binary_sha256() in result.stdout
