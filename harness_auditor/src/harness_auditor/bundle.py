"""Attestation bundles for regulated environments.

The HMAC pipeline proves "someone with the key signed this report". For
audit trails that need to survive outside the organisation that produced
them — regulatory submissions, third-party verifications, long-term
archival — the right primitive is asymmetric: a public key the verifier
can pin out-of-band, a detached signature over the report payload, and a
self-contained directory that does not require access to the producing
auditor to be validated.

That is what an **attestation bundle** is. ``build_bundle`` packages a
previously-produced audit report into:

    bundle-<ontology_sha>/
    ├── manifest.json           # canonical metadata + per-file SHA-256
    ├── manifest.sig.ed25519    # detached Ed25519 signature over manifest.json
    ├── pubkey.ed25519          # hex-encoded public verification key
    ├── report.json             # the audit verdict (copied as-is)
    ├── report.md               # rendered narrative
    ├── inputs/
    │   ├── ontology.yaml       # the audited ontology
    │   ├── previous.yaml       # if --previous was provided
    │   └── taxonomy.yaml       # if --taxonomy was provided
    └── replay/
        ├── replay.sh           # one-command audit replay
        └── README.md           # how a third party verifies + replays

``verify_bundle`` validates the structure end-to-end:

    * Every file listed in the manifest exists and its SHA-256 matches.
    * The Ed25519 signature over the manifest verifies under the bundled
      public key (or under a pinned key the verifier passes in).
    * The bundled ``auditor_binary_sha256`` is recorded; a verifier that
      pins the expected binary hash can compare without trusting the
      bundle itself.

Why Ed25519 (and not HMAC) here:

    * **Public key**: a verifier does not need the private key. The
      report can be published, the signature is verifiable, the
      producer's identity is the public key.
    * **Standard library / standard format**: Ed25519 signatures are
      64 bytes, well-supported, and not patent-encumbered.

This module imports ``cryptography`` lazily so the core auditor runs
without the optional ``[bundle]`` extra installed.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Format version of the bundle manifest. Bumped on any backwards-
#: incompatible change to the manifest shape; verifiers reject unknown
#: versions to avoid the silent-skew problem the HMAC domain tag also
#: addresses.
BUNDLE_FORMAT: str = "ragf-audit-bundle/v1"


class BundleError(RuntimeError):
    """Bundle could not be built or verified."""


class CryptographyMissingError(BundleError):
    """The optional ``[bundle]`` extra is not installed."""


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BundleInputs:
    """Paths the bundle should incorporate. Optional inputs are ``None``."""

    report_dir: Path
    ontology: Path
    previous: Path | None = None
    taxonomy: Path | None = None


@dataclass(frozen=True)
class BuildOutcome:
    """Return value from ``build_bundle``; gives the verifier a head start."""

    bundle_dir: Path
    manifest_path: Path
    signature_path: Path
    pubkey_path: Path
    bundle_sha256: str


def build_bundle(
    inputs: BundleInputs,
    out_dir: Path,
    *,
    ed25519_private_key_hex: str | None = None,
) -> BuildOutcome:
    """Package ``inputs`` into a signed attestation bundle under ``out_dir``.

    ``ed25519_private_key_hex`` is the 32-byte signing seed encoded as
    hex (64 chars). When ``None``, an ephemeral keypair is generated and
    the public key is bundled — the bundle is then "self-signed" and the
    verifier pins the public key out-of-band (typically: publish the
    pubkey hex in the producer's release notes alongside the bundle).
    """
    _Ed25519 = _require_cryptography()

    if not inputs.report_dir.is_dir():
        raise BundleError(f"report directory not found: {inputs.report_dir}")
    report_json = inputs.report_dir / "report.json"
    report_md = inputs.report_dir / "report.md"
    report_sig = inputs.report_dir / "report.sig"
    if not report_json.is_file():
        raise BundleError(f"report.json not present in {inputs.report_dir}")
    if not inputs.ontology.is_file():
        raise BundleError(f"ontology source not present: {inputs.ontology}")

    # ----- 1. Establish the bundle directory layout
    report_payload = json.loads(report_json.read_bytes())
    ontology_sha = report_payload.get("ontology_sha256")
    if not isinstance(ontology_sha, str) or len(ontology_sha) != 64:
        raise BundleError(
            "report.json does not carry a valid ontology_sha256; refusing to "
            "build a bundle from a malformed report"
        )

    bundle_dir = out_dir / f"bundle-{ontology_sha}"
    inputs_dir = bundle_dir / "inputs"
    replay_dir = bundle_dir / "replay"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    inputs_dir.mkdir(exist_ok=True)
    replay_dir.mkdir(exist_ok=True)

    # ----- 2. Copy artifacts the verifier will re-hash
    shutil.copy2(report_json, bundle_dir / "report.json")
    if report_md.is_file():
        shutil.copy2(report_md, bundle_dir / "report.md")
    if report_sig.is_file():
        shutil.copy2(report_sig, bundle_dir / "report.sig")
    shutil.copy2(inputs.ontology, inputs_dir / "ontology.yaml")
    if inputs.previous is not None and inputs.previous.is_file():
        shutil.copy2(inputs.previous, inputs_dir / "previous.yaml")
    if inputs.taxonomy is not None and inputs.taxonomy.is_file():
        shutil.copy2(inputs.taxonomy, inputs_dir / "taxonomy.yaml")

    # ----- 3. Write replay script and README
    replay_sh = _render_replay_script(inputs, report_payload)
    (replay_dir / "replay.sh").write_text(replay_sh, encoding="utf-8")
    (replay_dir / "replay.sh").chmod(0o755)
    (replay_dir / "README.md").write_text(_REPLAY_README, encoding="utf-8")

    # ----- 4. Resolve the signing key (load given, or generate ephemeral)
    if ed25519_private_key_hex is not None:
        try:
            private_bytes = bytes.fromhex(ed25519_private_key_hex)
        except ValueError as e:
            raise BundleError(
                "Ed25519 signing seed must be 64 hex chars (32 bytes)"
            ) from e
        if len(private_bytes) != 32:
            raise BundleError(
                f"Ed25519 signing seed must be 32 bytes; got {len(private_bytes)}"
            )
        private_key = _Ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)
    else:
        private_key = _Ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    pubkey_hex = public_key.public_bytes_raw().hex()

    # ----- 5. Build the manifest
    files_to_hash = _walk_bundle_files(
        bundle_dir,
        exclude_basenames={"manifest.json", "manifest.sig.ed25519"},
    )
    file_hashes = {
        path.relative_to(bundle_dir).as_posix(): _file_sha256(path)
        for path in sorted(files_to_hash)
    }
    manifest: dict[str, Any] = {
        "format": BUNDLE_FORMAT,
        "created_at": datetime.now(UTC).isoformat(),
        "auditor_version": report_payload.get("auditor_version"),
        "auditor_binary_sha256": report_payload.get("auditor_binary_sha256"),
        "ontology_sha256": ontology_sha,
        "certification_status": report_payload.get("certification_status"),
        "signature_algorithm": "Ed25519",
        "signature_pubkey_hex": pubkey_hex,
        "files": file_hashes,
    }
    manifest_bytes = _canonical_bytes(manifest)
    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)

    # ----- 6. Sign the manifest (detached)
    signature = private_key.sign(manifest_bytes)
    signature_path = bundle_dir / "manifest.sig.ed25519"
    signature_path.write_text(signature.hex() + "\n", encoding="utf-8")

    pubkey_path = bundle_dir / "pubkey.ed25519"
    pubkey_path.write_text(pubkey_hex + "\n", encoding="utf-8")

    # ----- 7. Roll up the bundle SHA so the caller can pin it
    bundle_sha = _bundle_sha256(bundle_dir)
    return BuildOutcome(
        bundle_dir=bundle_dir,
        manifest_path=manifest_path,
        signature_path=signature_path,
        pubkey_path=pubkey_path,
        bundle_sha256=bundle_sha,
    )


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifyOutcome:
    """Verifier return value. ``warnings`` are non-fatal observations."""

    bundle_dir: Path
    pubkey_hex: str
    certification_status: str
    auditor_binary_sha256: str | None
    warnings: tuple[str, ...]


def verify_bundle(
    bundle_dir: Path,
    *,
    pinned_pubkey_hex: str | None = None,
    pinned_binary_sha256: str | None = None,
) -> VerifyOutcome:
    """Validate file integrity + Ed25519 signature on an attestation bundle.

    Raises ``BundleError`` on any mismatch. Returns a ``VerifyOutcome`` with
    non-fatal observations in ``warnings`` (e.g. binary drift without a
    pinned reference; the verifier can decide whether that warrants
    rejection in their own policy).
    """
    _Ed25519 = _require_cryptography()

    manifest_path = bundle_dir / "manifest.json"
    signature_path = bundle_dir / "manifest.sig.ed25519"
    pubkey_path = bundle_dir / "pubkey.ed25519"
    for required in (manifest_path, signature_path, pubkey_path):
        if not required.is_file():
            raise BundleError(f"missing required bundle file: {required}")

    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as e:
        raise BundleError(f"manifest.json is not valid JSON: {e}") from e
    if manifest.get("format") != BUNDLE_FORMAT:
        raise BundleError(
            f"unsupported bundle format {manifest.get('format')!r}; this "
            f"verifier expects {BUNDLE_FORMAT!r}"
        )

    # ----- Signature
    bundled_pubkey_hex = pubkey_path.read_text(encoding="utf-8").strip()
    if manifest.get("signature_pubkey_hex") != bundled_pubkey_hex:
        raise BundleError(
            "pubkey.ed25519 does not match the public key declared in the "
            "manifest; bundle has been tampered with"
        )
    if pinned_pubkey_hex is not None and pinned_pubkey_hex != bundled_pubkey_hex:
        raise BundleError(
            "bundled public key does not match the pinned key the verifier "
            "expected; bundle origin is unverified"
        )
    try:
        pubkey_bytes = bytes.fromhex(bundled_pubkey_hex)
    except ValueError as e:
        raise BundleError("pubkey.ed25519 is not valid hex") from e
    public_key = _Ed25519.Ed25519PublicKey.from_public_bytes(pubkey_bytes)
    signature_hex = signature_path.read_text(encoding="utf-8").strip()
    try:
        signature_bytes = bytes.fromhex(signature_hex)
    except ValueError as e:
        raise BundleError("manifest.sig.ed25519 is not valid hex") from e
    try:
        public_key.verify(signature_bytes, manifest_bytes)
    except Exception as e:  # cryptography's exact type is InvalidSignature
        raise BundleError(
            "Ed25519 signature does not verify under the bundled public key"
        ) from e

    # ----- File hashes
    declared_files: dict[str, str] = manifest.get("files") or {}
    for relpath, declared in declared_files.items():
        actual_path = bundle_dir / relpath
        if not actual_path.is_file():
            raise BundleError(
                f"manifest declares {relpath}, but the file is missing from the bundle"
            )
        actual = _file_sha256(actual_path)
        if actual != declared:
            raise BundleError(
                f"hash mismatch for {relpath}: manifest says {declared}, "
                f"actual {actual}"
            )

    # ----- Optional binary pinning
    warnings: list[str] = []
    declared_binary = manifest.get("auditor_binary_sha256")
    if pinned_binary_sha256 is not None and declared_binary != pinned_binary_sha256:
        raise BundleError(
            f"auditor_binary_sha256 mismatch: bundle declares {declared_binary}, "
            f"verifier pinned {pinned_binary_sha256}"
        )
    if pinned_binary_sha256 is None and declared_binary is None:
        warnings.append(
            "bundle does not record an auditor_binary_sha256; provenance "
            "continuity cannot be verified"
        )

    return VerifyOutcome(
        bundle_dir=bundle_dir,
        pubkey_hex=bundled_pubkey_hex,
        certification_status=str(manifest.get("certification_status") or "UNKNOWN"),
        auditor_binary_sha256=declared_binary,
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_cryptography() -> Any:
    """Lazy-import the cryptography library; raise a helpful error if absent.

    Returns the ``cryptography.hazmat.primitives.asymmetric.ed25519`` module.
    Kept in one place so every public function in this module produces the
    same actionable diagnostic when the extra is not installed.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError as exc:
        raise CryptographyMissingError(
            "the 'cryptography' library is required for attestation bundles. "
            "Install with: pip install -e \".[bundle]\""
        ) from exc
    return ed25519


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk_bundle_files(root: Path, exclude_basenames: set[str]) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in exclude_basenames:
            continue
        yield path


def _bundle_sha256(bundle_dir: Path) -> str:
    """SHA-256 over (relpath, file-hash) pairs, sorted. Stable across hosts."""
    digest = hashlib.sha256()
    for path in sorted(_walk_bundle_files(bundle_dir, exclude_basenames=set())):
        rel = path.relative_to(bundle_dir).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_file_sha256(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _render_replay_script(inputs: BundleInputs, report: dict[str, Any]) -> str:
    extras: list[str] = []
    if (inputs.previous is not None) and inputs.previous.is_file():
        extras.append('  --previous inputs/previous.yaml \\')
    if (inputs.taxonomy is not None) and inputs.taxonomy.is_file():
        extras.append('  --taxonomy inputs/taxonomy.yaml \\')
    extras_block = ("\n" + "\n".join(extras)) if extras else ""
    return f"""#!/usr/bin/env bash
# Replay the audit that produced this bundle.
#
# This is a thin convenience script: a verifier with their own Neo4j
# sandbox can re-run the audit and confirm the verdict matches
# manifest.certification_status (= {report.get("certification_status")!r}).
#
# Prerequisites: harness-auditor v{report.get("auditor_version", "?")} (or a
# version producing the same auditor_binary_sha256), Neo4j 5.x with the
# GDS plugin reachable on $NEO4J_URI, and AUDITOR_HMAC_KEY exported.
set -euo pipefail
cd "$(dirname "$0")/.."
harness-audit audit \\
  --ontology inputs/ontology.yaml \\{extras_block}
  --reports-dir replay/replay-output
echo "Replay complete. Compare replay-output/<sha>/report.json against report.json."
"""


_REPLAY_README: str = """\
# Bundle replay

This directory contains everything a third-party verifier needs to
re-run the audit that produced this bundle. The companion script
`replay.sh` invokes `harness-audit audit` against the bundled inputs and
writes a fresh report to `replay/replay-output/`.

After replay, the verifier should compare:

  * `manifest.json.certification_status` (the bundled verdict)
  * `replay/replay-output/<sha256>/report.json::certification_status`

A mismatch can mean any of:

  1. Cypher non-determinism (CC-11 PageRank is tolerance-bounded; the
     hysteresis margin in the query reduces but does not eliminate this).
  2. Neo4j version skew: dbms.components() in the replay should match
     the `environment.neo4j_version` in the bundled report.json.
  3. Auditor version skew: `harness-audit --version` must produce a
     `auditor_binary_sha256` equal to the one in the manifest.

The bundle's signature attests only that this PAYLOAD was produced and
signed by the holder of the published public key. Replay attests that
the payload is reproducible from the inputs.
"""
