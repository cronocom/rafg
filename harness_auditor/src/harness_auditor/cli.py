"""
CLI entrypoint for the RAGF Ontology Auditor.

End-to-end pipeline:

  1. Validate the candidate YAML against the ontology schema.
  2. Hash the canonical JSON form (SHA-256) for provenance.
  3. Wipe and project the ontology into the Neo4j sandbox.
  4. Execute every registered certification criterion.
  5. Aggregate, render, and HMAC-sign the report.

Exit codes follow ``docs/ARCHITECTURE.md``:

  0 — PASSED
  1 — FAILED or REQUIRES_REVIEW (any blocking/advisory failure, or unsigned)
  2 — input invalid (YAML parse / schema validation failure / file missing)
  3 — infrastructure error (Neo4j unreachable, query execution failure)
"""

from __future__ import annotations

import hashlib

# Stdlib hmac is kept for ``hmac.compare_digest`` (constant-time string
# comparison) in the verify command. The HMAC computation itself goes
# through ``harness_auditor.report.hmac_signature`` so the domain tag is
# applied in exactly one place.
import hmac
import json
import os
from contextlib import ExitStack
from pathlib import Path

import typer
import yaml
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable
from pydantic import ValidationError
from rich.console import Console

from harness_auditor import __version__
from harness_auditor._attestation import auditor_binary_sha256
from harness_auditor._audit_lock import AuditLockBusy, AuditLockUnsupported, audit_lock
from harness_auditor._environment import probe_gds_version, probe_neo4j_version
from harness_auditor.bundle import (
    BundleError,
    BundleInputs,
    CryptographyMissingError,
    build_bundle,
    verify_bundle,
)
from harness_auditor.loader import (
    LoaderMismatchError,
    load,
    load_previous,
    load_taxonomy,
)
from harness_auditor.report import build_report, hmac_signature, write_artifacts
from harness_auditor.runner import (
    REGISTRY,
    effective_registry,
    packaged_queries_dir,
    run_all,
)
from harness_auditor.schemas.ontology_schema import Ontology, Taxonomy
from harness_auditor.schemas.report_schema import (
    AuditReport,
    CertificationStatus,
    CriterionStatus,
)

EXIT_OK = 0
EXIT_VERDICT_FAILURE = 1
EXIT_INPUT_INVALID = 2
EXIT_INFRA_ERROR = 3

#: Default threshold for CC-11. A constraint is reported when its PageRank
#: score strictly exceeds ``(threshold_ratio + CC11_HYSTERESIS) * mean_score``
#: — see ``docs/CRITERIA.md`` § CC-11 for the hysteresis rationale.
DEFAULT_CC11_THRESHOLD_RATIO = 1.3

#: Default per-verb regulatory-coverage floor for CC-06. A verb is flagged
#: when its `matched/declared` regulation ratio falls below this fraction.
#: 0.85 matches the canonical RAGF v2.4 dictionary; permissive domains may
#: lower it, stricter domains may raise it (must be in (0, 1]).
DEFAULT_CC06_COVERAGE_THRESHOLD = 0.85

#: CC-11 hysteresis margin applied on top of ``threshold_ratio``. PageRank
#: converges iteratively and tolerance noise can flip a borderline
#: constraint between PASS and FAIL across runs; the margin stabilises the
#: verdict at the cost of shifting the *effective* threshold to
#: ``(threshold_ratio + CC11_HYSTERESIS)``. Documented at every site that
#: mentions the threshold so the number a user sets and the number the
#: query applies never diverge silently.
CC11_HYSTERESIS = 0.05

app = typer.Typer(
    name="harness-audit",
    add_completion=False,
    no_args_is_help=True,
    help="Pre-execution certification of RAGF governance harnesses.",
)
console = Console()


@app.callback()
def _main() -> None:
    """Force ``audit`` (and any future subcommand) to be explicit at the CLI."""


def _read_ontology(path: Path) -> tuple[Ontology, str]:
    if not path.is_file():
        console.print(
            f"[red]error[/]: ontology file not found: {path}\n"
            f"  Hint: check the path is relative to the current directory, "
            f"or pass an absolute path."
        )
        raise typer.Exit(EXIT_INPUT_INVALID)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        console.print(_format_yaml_error(path, e))
        raise typer.Exit(EXIT_INPUT_INVALID) from e
    try:
        ontology = Ontology.model_validate(data)
    except ValidationError as e:
        console.print(_format_validation_error(path, e, kind="ontology"))
        raise typer.Exit(EXIT_INPUT_INVALID) from e
    canonical = json.dumps(
        ontology.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return ontology, digest


def _read_taxonomy(path: Path) -> Taxonomy:
    if not path.is_file():
        console.print(
            f"[red]error[/]: taxonomy file not found: {path}\n"
            f"  Hint: --taxonomy expects a YAML file with `domain:` and "
            f"`verbs:` keys. See tests/fixtures/fintech_taxonomy_complete.yaml."
        )
        raise typer.Exit(EXIT_INPUT_INVALID)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        console.print(_format_yaml_error(path, e))
        raise typer.Exit(EXIT_INPUT_INVALID) from e
    try:
        return Taxonomy.model_validate(data)
    except ValidationError as e:
        console.print(_format_validation_error(path, e, kind="taxonomy"))
        raise typer.Exit(EXIT_INPUT_INVALID) from e


def _format_yaml_error(path: Path, exc: yaml.YAMLError) -> str:
    line_hint = ""
    mark = getattr(exc, "problem_mark", None)
    if mark is not None:
        line_hint = (
            f"  Location: line {mark.line + 1}, column {mark.column + 1}.\n"
        )
    return (
        f"[red]error[/]: {path.name} is not valid YAML.\n"
        f"  Underlying: {exc}\n"
        f"{line_hint}"
        f"  Hint: check indentation (tabs vs. spaces), unclosed quotes, or "
        f"unbalanced braces. `yamllint {path}` gives precise locations."
    )


def _format_validation_error(
    path: Path, exc: ValidationError, *, kind: str
) -> str:
    header = f"[red]error[/]: {path.name} failed {kind} schema validation"
    bullets: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "<root>"
        msg = err["msg"]
        bullets.append(f"  - [yellow]{loc}[/]: {msg}")
        provided = err.get("input")
        if provided is not None and not isinstance(provided, dict | list):
            bullets.append(f"      got: {provided!r}")
    footer = (
        "  Hint: see docs/CRITERIA.md (criteria reference) and "
        "docs/GRAPH_MODEL.md (graph schema)."
    )
    return "\n".join([header, "", *bullets, "", footer])


def _format_neo4j_unreachable(uri: str, exc: BaseException) -> str:
    return (
        f"[red]error[/]: cannot reach Neo4j at {uri}.\n"
        f"  Underlying: {exc}\n"
        f"  Hint: is the sandbox running?\n"
        f"    make up           # start the ephemeral Neo4j container\n"
        f"    make wait         # block until Bolt accepts connections\n"
        f"  Override the endpoint with NEO4J_URI=bolt://host:7687 or "
        f"--neo4j-uri."
    )


def _format_neo4j_auth(uri: str, exc: BaseException) -> str:
    return (
        f"[red]error[/]: Neo4j authentication failed at {uri}.\n"
        f"  Underlying: {exc}\n"
        f"  Hint: check NEO4J_USER / NEO4J_PASSWORD (or --neo4j-user / "
        f"--neo4j-password).\n"
        f"  Sandbox default credentials are `neo4j` / `auditor_local_only`."
    )


def _resolve_cc06_threshold() -> float:
    raw = os.environ.get("CC06_COVERAGE_THRESHOLD")
    if raw is None:
        return DEFAULT_CC06_COVERAGE_THRESHOLD
    try:
        value = float(raw)
    except ValueError:
        console.print(
            f"[red]error[/]: CC06_COVERAGE_THRESHOLD is not a valid number.\n"
            f"  Got: {raw!r}\n"
            f"  Expected: a decimal in (0, 1] (e.g. 0.85, 0.9).\n"
            f"  Default: {DEFAULT_CC06_COVERAGE_THRESHOLD}."
        )
        raise typer.Exit(EXIT_INPUT_INVALID) from None
    if not (0.0 < value <= 1.0):
        console.print(
            f"[red]error[/]: CC06_COVERAGE_THRESHOLD must be in (0, 1], "
            f"got: {value}.\n"
            f"  Coverage is a ratio (matched/declared regulations); values "
            f"outside (0, 1] are meaningless. Use 0.85 (default) or higher "
            f"for stricter coverage demands."
        )
        raise typer.Exit(EXIT_INPUT_INVALID)
    return value


def _dry_run_validate_queries(
    resolved_queries_dir: Path, strict_builtins: bool
) -> None:
    """For --dry-run: confirm every CC's .cypher exists, then exit cleanly.

    The point of dry-run is to give pre-commit and PR hooks a sub-second
    "would this audit even start?" answer without paying the Neo4j
    round-trip cost. We validate the things that can fail BEFORE Neo4j
    is touched: YAML parsing (done upstream), schema validation (done
    upstream), and the queries directory (done here).
    """
    registry = REGISTRY if strict_builtins else effective_registry()
    missing: list[str] = []
    for definition in registry:
        candidate_dir = (
            definition.query_dir
            if definition.query_dir is not None
            else resolved_queries_dir
        )
        candidate = candidate_dir / definition.query_file
        if not candidate.is_file():
            missing.append(f"{definition.criterion_id} -> {candidate}")
    if missing:
        console.print(
            "[red]error[/]: --dry-run found missing CC query files:\n"
            + "\n".join(f"  - {m}" for m in missing)
            + "\n  Hint: pass --queries-dir pointing at a directory that "
            + "contains every CC.cypher above, or unregister the offending CC."
        )
        raise typer.Exit(EXIT_INPUT_INVALID)


def _resolve_cc11_threshold() -> float:
    raw = os.environ.get("CC11_THRESHOLD_RATIO")
    if raw is None:
        return DEFAULT_CC11_THRESHOLD_RATIO
    try:
        value = float(raw)
    except ValueError:
        console.print(
            f"[red]error[/]: CC11_THRESHOLD_RATIO is not a valid number.\n"
            f"  Got: {raw!r}\n"
            f"  Expected: a decimal > 1.0 (e.g. 1.3, 1.5, 2.0).\n"
            f"  This controls how aggressively CC-11 (Constraint Centrality)\n"
            f"  flags constraints whose PageRank exceeds the graph mean. "
            f"Default: {DEFAULT_CC11_THRESHOLD_RATIO}. Note that the\n"
            f"  effective threshold applied by the query is\n"
            f"  ``threshold_ratio + {CC11_HYSTERESIS}`` (hysteresis margin)."
        )
        raise typer.Exit(EXIT_INPUT_INVALID) from None
    if value <= 1.0:
        console.print(
            f"[red]error[/]: CC11_THRESHOLD_RATIO must be strictly > 1.0, "
            f"got: {value}.\n"
            f"  Values at or below 1.0 would flag every constraint at or "
            f"below the graph mean, which is not actionable.\n"
            f"  Try 1.3 (default, moderate sensitivity) or 2.0 (strict). "
            f"The query adds a {CC11_HYSTERESIS} hysteresis margin on top."
        )
        raise typer.Exit(EXIT_INPUT_INVALID)
    return value


@app.command()
def audit(
    ontology: Path = typer.Option(
        ...,
        "--ontology",
        help="Path to the candidate ontology YAML.",
    ),
    previous: Path = typer.Option(
        None,
        "--previous",
        help="Path to the previous ontology YAML — enables CC-07 (Drift Delta).",
    ),
    taxonomy: Path = typer.Option(
        None,
        "--taxonomy",
        help="Path to the registered verb taxonomy YAML — enables CC-10 "
        "(Hallucinated Verbs).",
    ),
    reports_dir: Path = typer.Option(
        Path("./reports"),
        "--reports-dir",
        help="Directory under which reports/<sha256>/ artifacts are written.",
    ),
    queries_dir: Path = typer.Option(
        None,
        "--queries-dir",
        help="Directory containing CC-NN.cypher files. Defaults to the bundled set.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate YAML + schema + queries directory + key resolution, then "
        "exit 0 without touching Neo4j. Useful as a fast pre-commit / PR gate.",
    ),
    strict_builtins: bool = typer.Option(
        False,
        "--strict-builtins",
        help="Ignore any user-registered CCs and run only the canonical "
        "11 built-ins. Use in CI gates that want trust-but-verify isolation.",
    ),
    neo4j_uri: str = typer.Option(
        "bolt://127.0.0.1:7687",
        "--neo4j-uri",
        envvar="NEO4J_URI",
        help="Bolt URI of the auditor sandbox.",
    ),
    neo4j_user: str = typer.Option(
        "neo4j",
        "--neo4j-user",
        envvar="NEO4J_USER",
    ),
    neo4j_password: str = typer.Option(
        "auditor_local_only",
        "--neo4j-password",
        envvar="NEO4J_PASSWORD",
        hide_input=True,
    ),
) -> None:
    """Audit a candidate ontology against the certification criteria.

    The HMAC signing key is read from the ``AUDITOR_HMAC_KEY`` environment
    variable. There is no CLI flag for the key on purpose: a value passed on
    the command line leaks via ``ps(1)`` and shell history.
    """
    hmac_key = os.environ.get("AUDITOR_HMAC_KEY", "")
    console.print(f"[bold]harness-auditor[/] v{__version__}")

    ontology_obj, digest = _read_ontology(ontology)
    console.print(f"  ontology      : {ontology}")
    console.print(
        f"  domain        : {ontology_obj.domain.name} v{ontology_obj.domain.version}"
    )
    console.print(f"  sha256        : {digest}")

    resolved_queries_dir = queries_dir or packaged_queries_dir()
    if not resolved_queries_dir.is_dir():
        console.print(
            f"[red]error[/]: queries directory not found: {resolved_queries_dir}"
        )
        raise typer.Exit(EXIT_INPUT_INVALID)
    console.print(f"  queries dir   : {resolved_queries_dir}")

    cc06_threshold = _resolve_cc06_threshold()
    cc11_threshold = _resolve_cc11_threshold()
    cc11_effective = cc11_threshold + CC11_HYSTERESIS
    console.print(f"  CC-06 coverage: {cc06_threshold:.2f} (min ratio)")
    console.print(
        f"  CC-11 ratio   : {cc11_threshold:.2f}x mean "
        f"(effective {cc11_effective:.2f}x with {CC11_HYSTERESIS:.2f} hysteresis)"
    )
    if strict_builtins:
        console.print("  registry      : strict-builtins (user CCs ignored)")
    if dry_run:
        _dry_run_validate_queries(resolved_queries_dir, strict_builtins)
        console.print("[green]OK[/]: --dry-run passed (no Neo4j round-trip)")
        raise typer.Exit(EXIT_OK)

    reports_dir.mkdir(parents=True, exist_ok=True)

    # Everything that needs cleanup — the advisory lock and the Neo4j
    # driver — is registered with ExitStack so unwinding is uniform and
    # exception-safe. If `audit_lock` raises during __enter__ for any
    # reason other than the two we model (busy or unsupported), the
    # ExitStack guarantees the partially-opened resources clean up
    # correctly without us juggling __enter__/__exit__ by hand.
    with ExitStack() as stack:
        try:
            stack.enter_context(audit_lock(reports_dir))
        except AuditLockBusy as e:
            console.print(f"[red]error[/]: {e}")
            raise typer.Exit(EXIT_INFRA_ERROR) from e
        except AuditLockUnsupported:
            # Windows / unusual platforms: continue without the lock and
            # emit a one-line warning. Concurrent-audit safety becomes the
            # user's responsibility on that platform.
            console.print(
                "[yellow]note[/]: advisory lock unavailable on this platform; "
                "concurrent audits against the same Neo4j may corrupt verdicts."
            )

        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        stack.callback(driver.close)

        try:
            driver.verify_connectivity()
        except AuthError as e:
            console.print(_format_neo4j_auth(neo4j_uri, e))
            raise typer.Exit(EXIT_INFRA_ERROR) from e
        except ServiceUnavailable as e:
            console.print(_format_neo4j_unreachable(neo4j_uri, e))
            raise typer.Exit(EXIT_INFRA_ERROR) from e

        previous_obj: Ontology | None = None
        taxonomy_obj: Taxonomy | None = None
        if previous is not None:
            previous_obj, prev_digest = _read_ontology(previous)
            console.print(f"  previous ont  : {previous} (sha256: {prev_digest[:12]}…)")
        if taxonomy is not None:
            taxonomy_obj = _read_taxonomy(taxonomy)
            console.print(
                f"  taxonomy      : {taxonomy} "
                f"(domain={taxonomy_obj.domain}, {len(taxonomy_obj.verbs)} verbs)"
            )

        neo4j_v: str | None = None
        gds_v: str | None = None
        try:
            with driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
                load(session, ontology_obj)
                if previous_obj is not None:
                    load_previous(session, previous_obj)
                if taxonomy_obj is not None:
                    load_taxonomy(session, taxonomy_obj)
                # ``strict_builtins`` pins the runner to REGISTRY (built-in
                # 11 only) so a CC accidentally imported into the process
                # via a transitive dep cannot influence the verdict.
                effective_reg = REGISTRY if strict_builtins else None
                criteria = run_all(
                    session,
                    resolved_queries_dir,
                    registry=effective_reg,
                    query_params={
                        "threshold_ratio": cc11_threshold,
                        "coverage_threshold": cc06_threshold,
                        "cc11_hysteresis": CC11_HYSTERESIS,
                    },
                )
                # Probe the runtime stack INSIDE the session so the report
                # environment block reflects the exact server that produced
                # the verdict, not whatever happens to be running later.
                neo4j_v = probe_neo4j_version(session)
                gds_v = probe_gds_version(session)
        except LoaderMismatchError as e:
            # LoaderMismatchError's __str__ already prints a per-kind
            # diagnostic with probable causes and remediation; just frame it.
            console.print(f"[red]error[/]: loader sanity check failed.\n\n{e}")
            raise typer.Exit(EXIT_INFRA_ERROR) from e
        except Neo4jError as e:
            console.print(f"[red]error[/]: Neo4j query error: {e}")
            raise typer.Exit(EXIT_INFRA_ERROR) from e

    # The report is built and written *outside* the ExitStack — at this
    # point we are only touching the local filesystem, so concurrent
    # `harness-audit` instances writing to different ontology
    # subdirectories cannot conflict.
    report = build_report(
        ontology_sha256=digest,
        domain=ontology_obj.domain.name,
        domain_version=ontology_obj.domain.version,
        criteria=criteria,
        hmac_key_present=bool(hmac_key),
        neo4j_version=neo4j_v,
        gds_version=gds_v,
    )
    out_dir = write_artifacts(report, reports_dir, hmac_key or None)

    _print_summary(report, out_dir)

    if report.certification_status == CertificationStatus.PASSED:
        raise typer.Exit(EXIT_OK)
    raise typer.Exit(EXIT_VERDICT_FAILURE)


@app.command()
def verify(
    report_dir: Path = typer.Argument(
        ...,
        help="Path to a reports/<ontology_sha256>/ directory containing "
        "report.json and report.sig.",
    ),
) -> None:
    """Verify the HMAC signature on a previously-produced audit report.

    The HMAC key is read from ``AUDITOR_HMAC_KEY``. No CLI flag is offered:
    a value passed on the command line would leak via ``ps(1)`` and shell
    history.

    Exit codes:
      0 — signature is valid for the report bytes
      1 — signature does NOT match (tampered, wrong key, or replaced .sig)
      2 — report directory / files missing, or AUDITOR_HMAC_KEY unset
    """
    hmac_key = os.environ.get("AUDITOR_HMAC_KEY", "")
    if not report_dir.is_dir():
        console.print(
            f"[red]error[/]: report directory not found: {report_dir}\n"
            f"  Hint: pass the path printed by `harness-audit audit` (e.g. "
            f"reports/<ontology_sha256>/)."
        )
        raise typer.Exit(EXIT_INPUT_INVALID)
    if not hmac_key:
        console.print(
            "[red]error[/]: AUDITOR_HMAC_KEY is not set.\n"
            "  Hint: export the same key that was used at audit time, e.g.\n"
            "    export AUDITOR_HMAC_KEY=\"...\"\n"
            "    harness-audit verify reports/<sha256>/\n"
            "  The key is never accepted on the command line because it would\n"
            "  leak via ps(1) and shell history."
        )
        raise typer.Exit(EXIT_INPUT_INVALID)

    json_path = report_dir / "report.json"
    sig_path = report_dir / "report.sig"
    if not json_path.is_file():
        console.print(
            f"[red]error[/]: report.json not found in {report_dir}\n"
            f"  Hint: confirm the path points at a single audit dir "
            f"(reports/<sha256>/), not the parent reports/ directory."
        )
        raise typer.Exit(EXIT_INPUT_INVALID)
    if not sig_path.is_file():
        console.print(
            f"[red]error[/]: report.sig not found in {report_dir}\n"
            f"  Hint: this report was produced WITHOUT AUDITOR_HMAC_KEY and\n"
            f"  is therefore unsigned. Re-run the audit with the key set,\n"
            f"  or treat this report as REQUIRES_REVIEW by policy."
        )
        raise typer.Exit(EXIT_INPUT_INVALID)

    json_bytes = json_path.read_bytes()
    stored_sig = sig_path.read_text(encoding="utf-8").strip()
    expected_sig = hmac_signature(hmac_key, json_bytes)

    if not hmac.compare_digest(stored_sig, expected_sig):
        console.print(
            f"[red]error[/]: signature mismatch — report has been altered or "
            f"the wrong key was provided.\n"
            f"  expected: {expected_sig}\n"
            f"  found:    {stored_sig}\n"
            f"  Probable causes (most likely first):\n"
            f"    1. The HMAC key passed here differs from the one used at "
            f"audit time.\n"
            f"    2. report.json was modified after signing.\n"
            f"    3. report.sig was replaced with bytes from another report."
        )
        raise typer.Exit(EXIT_VERDICT_FAILURE)

    console.print(f"[green]OK[/]: report.sig is valid for {json_path}")
    _maybe_warn_binary_drift(json_bytes)
    raise typer.Exit(EXIT_OK)


@app.command(name="bundle")
def bundle_cmd(
    report_dir: Path = typer.Argument(
        ...,
        help="Existing reports/<sha256>/ directory whose audit will be packaged.",
    ),
    ontology: Path = typer.Option(
        ...,
        "--ontology",
        help="Path to the ontology YAML the audit consumed; embedded in the bundle.",
    ),
    previous: Path = typer.Option(
        None,
        "--previous",
        help="Optional previous-version ontology that was passed to the audit.",
    ),
    taxonomy: Path = typer.Option(
        None,
        "--taxonomy",
        help="Optional taxonomy that was passed to the audit.",
    ),
    out_dir: Path = typer.Option(
        Path("./bundles"),
        "--out-dir",
        help="Parent directory under which bundle-<sha>/ is written.",
    ),
) -> None:
    """Build an Ed25519-signed attestation bundle from a previous audit.

    The Ed25519 signing seed is read from ``AUDITOR_ED25519_KEY`` (64 hex
    chars = 32 bytes). When unset, an ephemeral keypair is generated and
    the public key is included in the bundle; the verifier still gets a
    cryptographically valid signature but pinning the producer's identity
    out-of-band becomes the verifier's responsibility.

    The output bundle is self-contained: report + inputs + replay script
    + manifest + signature + public key. A third party can verify it with
    ``harness-audit verify-bundle`` without access to this auditor.
    """
    seed_hex = os.environ.get("AUDITOR_ED25519_KEY") or None
    try:
        outcome = build_bundle(
            BundleInputs(
                report_dir=report_dir,
                ontology=ontology,
                previous=previous,
                taxonomy=taxonomy,
            ),
            out_dir=out_dir,
            ed25519_private_key_hex=seed_hex,
        )
    except CryptographyMissingError as e:
        console.print(f"[red]error[/]: {e}")
        raise typer.Exit(EXIT_INPUT_INVALID) from e
    except BundleError as e:
        console.print(f"[red]error[/]: {e}")
        raise typer.Exit(EXIT_INPUT_INVALID) from e

    console.print(f"[green]OK[/]: bundle built at {outcome.bundle_dir}")
    console.print(f"  manifest         : {outcome.manifest_path}")
    console.print(f"  signature        : {outcome.signature_path}")
    console.print(f"  pubkey           : {outcome.pubkey_path}")
    console.print(f"  bundle sha256    : {outcome.bundle_sha256}")
    if seed_hex is None:
        console.print(
            "[yellow]note[/]: AUDITOR_ED25519_KEY was unset; an ephemeral "
            "keypair was generated for this bundle. Publish the public "
            "key shown above out-of-band so verifiers can pin it."
        )
    raise typer.Exit(EXIT_OK)


@app.command(name="verify-bundle")
def verify_bundle_cmd(
    bundle_dir: Path = typer.Argument(
        ...,
        help="Path to a bundle-<sha>/ directory produced by `harness-audit bundle`.",
    ),
    pinned_pubkey: str = typer.Option(
        "",
        "--pinned-pubkey",
        envvar="AUDITOR_ED25519_PIN_PUBKEY",
        help="Expected Ed25519 public key (64 hex chars). When provided, the "
        "bundle's pubkey MUST match — protects against an attacker who "
        "ships a bundle signed with their own key.",
    ),
    pinned_binary: str = typer.Option(
        "",
        "--pinned-binary-sha256",
        envvar="AUDITOR_BINARY_PIN_SHA256",
        help="Expected auditor_binary_sha256. When provided, the bundle's "
        "declared binary hash MUST match the pinned value — protects "
        "against accepting a bundle from a non-canonical auditor build.",
    ),
) -> None:
    """Verify an attestation bundle: file hashes + Ed25519 signature.

    Exit codes:
      0 — bundle is valid; any warnings are informational
      1 — bundle is invalid (hash mismatch, signature failure, pin mismatch)
      2 — inputs missing, cryptography extra not installed
    """
    try:
        outcome = verify_bundle(
            bundle_dir,
            pinned_pubkey_hex=pinned_pubkey or None,
            pinned_binary_sha256=pinned_binary or None,
        )
    except CryptographyMissingError as e:
        console.print(f"[red]error[/]: {e}")
        raise typer.Exit(EXIT_INPUT_INVALID) from e
    except BundleError as e:
        console.print(f"[red]error[/]: {e}")
        raise typer.Exit(EXIT_VERDICT_FAILURE) from e

    console.print(f"[green]OK[/]: bundle verified at {outcome.bundle_dir}")
    console.print(f"  verdict          : {outcome.certification_status}")
    console.print(f"  pubkey           : {outcome.pubkey_hex}")
    if outcome.auditor_binary_sha256:
        console.print(f"  auditor binary   : {outcome.auditor_binary_sha256}")
    for warning in outcome.warnings:
        console.print(f"[yellow]warning[/]: {warning}")
    raise typer.Exit(EXIT_OK)


def _maybe_warn_binary_drift(json_bytes: bytes) -> None:
    """Compare the report's ``auditor_binary_sha256`` to the current install.

    A mismatch does not invalidate the HMAC (the report is still
    authentically signed by whoever held the key) but tells the verifier
    that the auditor binary that produced this report is NOT the binary
    they currently have installed. Useful for audit-trail continuity.
    """
    try:
        data = json.loads(json_bytes)
    except json.JSONDecodeError:
        return
    declared = data.get("auditor_binary_sha256")
    current = auditor_binary_sha256()
    if declared and declared != current:
        console.print(
            "[yellow]note[/]: this report was produced by a DIFFERENT auditor "
            "binary than the one currently installed.\n"
            f"  report's auditor_binary_sha256:    {declared}\n"
            f"  current installation's hash:       {current}\n"
            "  The signature is valid; if you intended to confirm continuity\n"
            "  with the producing auditor, the source set has changed."
        )


_VERDICT_COLOR = {
    "PASSED": "green",
    "REQUIRES_REVIEW": "yellow",
    "FAILED": "red",
}
_CRITERION_COLOR = {
    "PASS": "green",
    "WARN": "yellow",
    "FAIL": "red",
    "ERROR": "red",
    "SKIP": "white",
}


def _print_summary(report: AuditReport, out_dir: Path) -> None:
    status = report.certification_status.value
    color = _VERDICT_COLOR.get(status, "white")
    console.print()
    console.print(f"[bold {color}]verdict[/]: {status}")
    console.print(
        f"  PASS: {report.passed}  WARN: {report.warned}  "
        f"FAIL: {report.failed}  SKIP: {report.skipped}"
    )
    console.print(f"  latency       : {report.total_latency_ms:.1f} ms")
    console.print(f"  report dir    : {out_dir}")

    for c in report.criteria:
        cc = _CRITERION_COLOR.get(c.status.value, "white")
        console.print(
            f"  [{cc}]{c.status.value:<5}[/] "
            f"{c.criterion_id} · {c.name} "
            f"({c.severity.value}, {c.latency_ms:.1f} ms)"
        )
        if c.status != CriterionStatus.PASS:
            console.print(f"        {c.message}")


if __name__ == "__main__":
    app()
