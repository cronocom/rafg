"""Tests for the Ed25519 attestation bundle (the v0.2 differentiator).

The bundle is the artefact a regulated environment hands to a verifier
out-of-band. Tests cover:

  * Building a bundle from a previous signed report.
  * The full round-trip: build → verify → OK.
  * Tampering with the report, the manifest, or the signature must
    cause ``verify_bundle`` to refuse.
  * Pinning a different public key must refuse.
  * Pinning a different binary hash must refuse.

The ``cryptography`` library is required and is part of the ``[bundle]``
extra; skip the whole module if it is not installed so the core suite
still runs in minimal environments.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

cryptography = pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from harness_auditor.bundle import (  # noqa: E402
    BUNDLE_FORMAT,
    BundleError,
    BundleInputs,
    build_bundle,
    verify_bundle,
)
from harness_auditor.report import build_report, write_artifacts  # noqa: E402
from harness_auditor.schemas.report_schema import (  # noqa: E402
    CriterionResult,
    CriterionStatus,
    Severity,
)

HMAC_KEY = "bundle-test-hmac"


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


def _stage_report(tmp_path: Path) -> Path:
    report = build_report(
        ontology_sha256="a" * 64,
        domain="demo",
        domain_version="1.0.0",
        criteria=[_result()],
        hmac_key_present=True,
    )
    return write_artifacts(report, tmp_path / "reports", hmac_key=HMAC_KEY)


def _stage_inputs(tmp_path: Path) -> BundleInputs:
    report_dir = _stage_report(tmp_path)
    ontology = tmp_path / "ontology.yaml"
    ontology.write_text("schema_version: '1.0'\n", encoding="utf-8")
    return BundleInputs(report_dir=report_dir, ontology=ontology)


def _signing_key_hex() -> str:
    return Ed25519PrivateKey.generate().private_bytes_raw().hex()


# ---------------------------------------------------------------------------
# Build + happy-path verify
# ---------------------------------------------------------------------------


def test_round_trip_build_and_verify(tmp_path: Path) -> None:
    """The canonical use case: build a bundle, hand it to a verifier."""
    inputs = _stage_inputs(tmp_path)
    seed_hex = _signing_key_hex()
    out = build_bundle(inputs, tmp_path / "bundles", ed25519_private_key_hex=seed_hex)
    assert out.bundle_dir.is_dir()
    assert (out.bundle_dir / "manifest.json").is_file()
    assert (out.bundle_dir / "manifest.sig.ed25519").is_file()
    assert (out.bundle_dir / "pubkey.ed25519").is_file()
    assert (out.bundle_dir / "report.json").is_file()
    assert (out.bundle_dir / "inputs" / "ontology.yaml").is_file()
    assert (out.bundle_dir / "replay" / "replay.sh").is_file()

    verify_outcome = verify_bundle(out.bundle_dir)
    assert verify_outcome.certification_status in {"PASSED", "REQUIRES_REVIEW", "FAILED"}
    assert len(verify_outcome.pubkey_hex) == 64


def test_manifest_declares_bundle_format(tmp_path: Path) -> None:
    """Manifest format is versioned so future-skewed verifiers can refuse."""
    inputs = _stage_inputs(tmp_path)
    out = build_bundle(inputs, tmp_path / "bundles", ed25519_private_key_hex=_signing_key_hex())
    manifest = json.loads((out.bundle_dir / "manifest.json").read_bytes())
    assert manifest["format"] == BUNDLE_FORMAT
    assert manifest["signature_algorithm"] == "Ed25519"
    assert "files" in manifest
    assert "report.json" in manifest["files"]


def test_replay_script_is_executable(tmp_path: Path) -> None:
    inputs = _stage_inputs(tmp_path)
    out = build_bundle(inputs, tmp_path / "bundles", ed25519_private_key_hex=_signing_key_hex())
    replay = out.bundle_dir / "replay" / "replay.sh"
    mode = replay.stat().st_mode & 0o777
    assert mode & 0o100, f"replay.sh must be user-executable; got mode {mode:o}"


# ---------------------------------------------------------------------------
# Tamper detection
# ---------------------------------------------------------------------------


def test_verify_rejects_tampered_report(tmp_path: Path) -> None:
    inputs = _stage_inputs(tmp_path)
    out = build_bundle(inputs, tmp_path / "bundles", ed25519_private_key_hex=_signing_key_hex())
    # Modify the bundled report.json; the manifest still declares the old hash.
    payload = json.loads((out.bundle_dir / "report.json").read_bytes())
    payload["domain"] = "compromised"
    (out.bundle_dir / "report.json").write_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    with pytest.raises(BundleError, match="hash mismatch"):
        verify_bundle(out.bundle_dir)


def test_verify_rejects_tampered_manifest(tmp_path: Path) -> None:
    """Changing the manifest invalidates the signature."""
    inputs = _stage_inputs(tmp_path)
    out = build_bundle(inputs, tmp_path / "bundles", ed25519_private_key_hex=_signing_key_hex())
    manifest_path = out.bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["certification_status"] = "PASSED_FAKED"
    manifest_path.write_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    with pytest.raises(BundleError, match="signature does not verify"):
        verify_bundle(out.bundle_dir)


def test_verify_rejects_pubkey_replacement(tmp_path: Path) -> None:
    """Swapping the bundled pubkey breaks the manifest sanity check."""
    inputs = _stage_inputs(tmp_path)
    out = build_bundle(inputs, tmp_path / "bundles", ed25519_private_key_hex=_signing_key_hex())
    attacker_pub = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
    (out.bundle_dir / "pubkey.ed25519").write_text(attacker_pub, encoding="utf-8")
    with pytest.raises(BundleError, match="does not match the public key"):
        verify_bundle(out.bundle_dir)


# ---------------------------------------------------------------------------
# Pinning (the differentiator for regulated environments)
# ---------------------------------------------------------------------------


def test_verify_accepts_correct_pinned_pubkey(tmp_path: Path) -> None:
    inputs = _stage_inputs(tmp_path)
    seed_hex = _signing_key_hex()
    out = build_bundle(inputs, tmp_path / "bundles", ed25519_private_key_hex=seed_hex)
    pubkey_hex = (out.bundle_dir / "pubkey.ed25519").read_text().strip()
    # The verifier had this pubkey out-of-band → bundle is trusted.
    outcome = verify_bundle(out.bundle_dir, pinned_pubkey_hex=pubkey_hex)
    assert outcome.pubkey_hex == pubkey_hex


def test_verify_rejects_wrong_pinned_pubkey(tmp_path: Path) -> None:
    inputs = _stage_inputs(tmp_path)
    out = build_bundle(inputs, tmp_path / "bundles", ed25519_private_key_hex=_signing_key_hex())
    other_pubkey = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
    with pytest.raises(BundleError, match="pinned key"):
        verify_bundle(out.bundle_dir, pinned_pubkey_hex=other_pubkey)


def test_verify_rejects_wrong_pinned_binary_hash(tmp_path: Path) -> None:
    inputs = _stage_inputs(tmp_path)
    out = build_bundle(inputs, tmp_path / "bundles", ed25519_private_key_hex=_signing_key_hex())
    with pytest.raises(BundleError, match="auditor_binary_sha256 mismatch"):
        verify_bundle(out.bundle_dir, pinned_binary_sha256="f" * 64)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_ephemeral_keypair_is_distinct_per_build(tmp_path: Path) -> None:
    """Two bundles built without AUDITOR_ED25519_KEY get distinct keys."""
    inputs1 = _stage_inputs(tmp_path / "a")
    inputs2 = _stage_inputs(tmp_path / "b")
    out1 = build_bundle(inputs1, tmp_path / "bundles1", ed25519_private_key_hex=None)
    out2 = build_bundle(inputs2, tmp_path / "bundles2", ed25519_private_key_hex=None)
    pub1 = (out1.bundle_dir / "pubkey.ed25519").read_text().strip()
    pub2 = (out2.bundle_dir / "pubkey.ed25519").read_text().strip()
    assert pub1 != pub2


def test_unsupported_bundle_format_is_rejected(tmp_path: Path) -> None:
    """A future-skewed format must be rejected, not silently re-interpreted."""
    inputs = _stage_inputs(tmp_path)
    out = build_bundle(inputs, tmp_path / "bundles", ed25519_private_key_hex=_signing_key_hex())
    manifest_path = out.bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["format"] = "ragf-audit-bundle/v99"
    manifest_path.write_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    with pytest.raises(BundleError, match="unsupported bundle format"):
        verify_bundle(out.bundle_dir)


def test_invalid_seed_length_is_rejected(tmp_path: Path) -> None:
    inputs = _stage_inputs(tmp_path)
    with pytest.raises(BundleError, match="32 bytes"):
        build_bundle(inputs, tmp_path / "bundles", ed25519_private_key_hex="aa" * 31)


def test_invalid_seed_hex_is_rejected(tmp_path: Path) -> None:
    inputs = _stage_inputs(tmp_path)
    with pytest.raises(BundleError, match="hex"):
        build_bundle(inputs, tmp_path / "bundles", ed25519_private_key_hex="not-hex")
