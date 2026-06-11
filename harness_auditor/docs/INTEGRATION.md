# Integration Guide

This document shows how to embed the auditor as a **Python library**, not as
a CLI. Three audiences are explicitly in scope:

* Application teams that already manage their own Neo4j connection and want
  the auditor to act on it.
* Platform teams that want a CI gate enforcing certain CCs on every PR.
* Teams that want to register their own organisation-specific CCs without
  forking the package.

All symbols used below are part of the **stable** API (re-exported from
`harness_auditor.__all__`). Anything else is internal and may change.

> **Install hint** — the snippets that follow only need the core install
> (`pip install harness-auditor` or `pip install -e .`). The
> end-to-end demo notebook (`notebooks/01_quickstart.ipynb`) additionally
> needs jupyter and pandas: `pip install -e ".[notebook]"`. Section 8
> (attestation bundles) requires the `[bundle]` extra:
> `pip install -e ".[bundle]"`.

---

## 1 · Open a session you already own

The package never opens a Neo4j connection on its own — `load` and `run_all`
accept a `neo4j.Session`. Bring your own:

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "bolt://my-neo4j.internal:7687",
    auth=("ops", "REDACTED"),
)
session = driver.session(database="audits")  # use a dedicated database
```

The auditor expects exclusive write access during a load + audit cycle: it
runs `MATCH (n) DETACH DELETE n` before projecting the ontology. If you
share the database, isolate audits in their own database
(`session = driver.session(database="audits")`) or in a fresh container.

---

## 2 · Load an ontology from a dict (not from YAML)

YAML is one of several inputs you can validate through the Pydantic schema.
A dict produced by your CMS, message bus, or API gateway works identically:

```python
from harness_auditor import Ontology, load

payload = {
    "schema_version": "1.0",
    "domain": {"name": "fintech_pilot", "version": "1.0.0"},
    "regulations": [
        {"code": "PSD2_ART97_SCA", "name": "PSD2 Article 97"},
    ],
    "verbs": [
        {
            "name": "transfer_funds",
            "risk_level": "high",
            "min_amm_level": 3,
            "must_satisfy": ["PSD2_ART97_SCA"],
            "payload_schema": [
                {"name": "amount_eur", "type": "float", "required": True},
            ],
        },
    ],
    "constraints": [
        {
            "name": "high_amount_requires_sca",
            "type": "threshold",
            "verb": "transfer_funds",
            "parameter": "amount_eur",
            "operator": "gte",
            "value": 30.0,
            "decision_if_violated": "ESCALATE",
            "regulation": "PSD2_ART97_SCA",
            "reason": "PSD2 SCA threshold",
            "severity": "high",
            "precedence_level": 90,
        },
    ],
}

ontology = Ontology.model_validate(payload)   # validates, raises pydantic.ValidationError on bad input
load(session, ontology)                       # projects into Neo4j
```

`Ontology` is a Pydantic v2 model: it rejects unknown keys
(`extra="forbid"`), enforces identifier patterns, and produces actionable
errors. Catch `pydantic.ValidationError` for programmatic handling.

---

## 3 · Run a subset of CCs

`run_all` defaults to **every** registered criterion. To gate on a specific
subset (a CI pipeline that only enforces CC-01/02/09 on PRs, for example),
pass the list explicitly:

```python
from harness_auditor import REGISTRY, packaged_queries_dir, run_all

WANTED = {"CC-01", "CC-02", "CC-09"}
subset = tuple(d for d in REGISTRY if d.criterion_id in WANTED)

results = run_all(
    session,
    queries_dir=packaged_queries_dir(),
    registry=subset,
)
```

Three notes:

* `REGISTRY` is the immutable built-in tuple. To include your own custom
  CCs in the subset, use `effective_registry()` instead.
* The `queries_dir` argument applies only to CCs whose
  `CriterionDefinition.query_dir` is `None`. Custom CCs that carry their own
  directory ignore it. The packaged set is the canonical default.
* `run_all` accepts `query_params=...` to feed Cypher query parameters
  through to every statement. The CLI populates this dict from
  environment variables; library callers can do the same:

  ```python
  results = run_all(
      session,
      queries_dir=packaged_queries_dir(),
      query_params={
          "threshold_ratio": 1.5,        # CC-11 — CC11_THRESHOLD_RATIO equivalent
          "cc11_hysteresis": 0.05,       # CC-11 — stability margin, default 0.05
          "coverage_threshold": 0.90,    # CC-06 — CC06_COVERAGE_THRESHOLD equivalent
      },
  )
  ```

  Neo4j silently ignores parameters not referenced by a given query, so
  the same dict goes to every CC without per-criterion plumbing. The
  effective CC-11 threshold applied by the Cypher is
  `(threshold_ratio + cc11_hysteresis) * mean_score`; see
  `docs/CRITERIA.md` § CC-11 for the rationale.

---

## 4 · Consume the report as a Python object

Don't read `report.json` from disk just to parse it again:

```python
from harness_auditor import (
    build_report,
    aggregate,
    CertificationStatus,
    CriterionStatus,
)

report = build_report(
    ontology_sha256="0" * 64,            # plug your own digest in
    domain=ontology.domain.name,
    domain_version=ontology.domain.version,
    criteria=results,
    hmac_key_present=False,              # programmatic use; sign downstream
)

# Branch on the verdict directly.
if report.certification_status == CertificationStatus.PASSED:
    promote_to_production()
elif report.certification_status == CertificationStatus.REQUIRES_REVIEW:
    notify_humans(report)
else:
    block_release(report)

# Inspect the failure surface programmatically.
failures = [c for c in report.criteria if c.status == CriterionStatus.FAIL]
for c in failures:
    log.warning("%s failed: %s", c.criterion_id, c.message)
    for row in c.evidence_rows:
        log.debug("  evidence: %s", row)

# All schema models implement `.model_dump(mode="json")` for serialisation.
metric.gauge("audit.failed_criteria", len(failures))
metric.histogram("audit.total_latency_ms", report.total_latency_ms)
```

The aggregation rule is exposed as a pure function (`aggregate`) when you
want to compute a verdict without going through `build_report`. Useful for
custom report shapes.

---

## 5 · Three integration patterns

### A · Pre-commit hook

Reject commits whose ontology fails any blocking CC. Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: ragf-audit
        name: RAGF ontology audit
        entry: harness-audit audit --ontology
        language: system
        files: '^ontologies/.*\.yaml$'
        pass_filenames: true
```

`harness-audit` exits 0 on `PASSED`, 1 on `FAILED`/`REQUIRES_REVIEW`, so
git aborts the commit on any non-zero outcome. Local dev still needs
`make up` running. Add `--dry-run` to a faster pre-commit variant that
validates YAML + schema + queries directory without touching Neo4j (no
sandbox needed, sub-second response).

### B · CI gate

GitHub Actions example. Spin up Neo4j as a service, audit, post the report
as a PR comment:

```yaml
name: RAGF audit
on:
  pull_request:
    paths: [ "ontologies/**.yaml" ]

jobs:
  audit:
    runs-on: ubuntu-latest
    services:
      neo4j:
        image: neo4j:5.26-community
        ports: [ "7687:7687" ]
        env:
          NEO4J_AUTH: neo4j/auditor_local_only
          NEO4J_PLUGINS: '["graph-data-science"]'
          NEO4J_dbms_security_procedures_unrestricted: "gds.*"
        options: >-
          --health-cmd "wget --spider -q http://localhost:7474"
          --health-interval 5s
          --health-retries 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install harness-auditor
      - run: |
          for f in ontologies/*.yaml; do
            AUDITOR_HMAC_KEY=${{ secrets.AUDITOR_HMAC_KEY }} \
              harness-audit audit --ontology "$f" --reports-dir reports \
              --strict-builtins
          done
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: audit-reports
          path: reports/**
```

The `--queries-dir` flag accepts your organisation-specific Cypher
directory if you want to override the built-in set. `--strict-builtins`
forces the runner to ignore any user-registered CCs, which is the
trust-but-verify stance recommended for CI gates: a transitive import of
some other code path cannot influence the verdict.

### C · Runtime invocation

A long-running service (e.g. an admin console that lets ops edit the
ontology) imports the auditor directly and rejects edits that would break
the verdict:

```python
import threading

from harness_auditor import Ontology, load, run_all, aggregate, CertificationStatus
from harness_auditor import packaged_queries_dir

_session_lock = threading.Lock()  # the loader wipes the DB before projecting

def validate_proposed_change(neo4j_session, proposed: dict) -> dict:
    ontology = Ontology.model_validate(proposed)  # raises on schema violation

    with _session_lock:
        load(neo4j_session, ontology)
        criteria = run_all(neo4j_session, packaged_queries_dir())

    return {
        "verdict": aggregate(criteria).value,
        "failed": [
            {"id": c.criterion_id, "message": c.message}
            for c in criteria
            if c.status.value in ("FAIL", "ERROR")
        ],
    }
```

The session lock matters: every load wipes the database first. Serialise or
use a dedicated database per concurrent audit.

---

## 6 · Register a custom CC

See [`examples/custom_cc/`](../examples/custom_cc/) for a worked example.
The short version:

```python
from pathlib import Path

from harness_auditor import CriterionDefinition, Severity, register_criterion

QUERIES = Path(__file__).resolve().parent / "queries"


def _severity(_rows):
    return Severity.MEDIUM


def _message(rows):
    return f"{len(rows)} violation(s)" if rows else "ok"


register_criterion(CriterionDefinition(
    criterion_id="CC-X1",                       # any uppercase suffix, no collision with built-ins
    name="My custom policy",
    query_file="my_policy.cypher",              # lives in QUERIES
    aggregator_role="advisory",                 # or "blocking"
    severity_for=_severity,
    message_for=_message,
    query_dir=QUERIES,                          # bind the .cypher to this directory
))
```

`register_criterion` raises `ValueError` on collisions and is process-wide.
`unregister_criterion(criterion_id)` and `reset_user_criteria()` are
available for tests and short-lived registrations.

---

## 7 · Verify a signature

Treat verification as a separate concern from audit. Receive a
`reports/<sha256>/` directory + the HMAC key out-of-band, then:

```bash
export AUDITOR_HMAC_KEY="..."
harness-audit verify reports/<sha256>/
```

The key is **only** read from `AUDITOR_HMAC_KEY`; the CLI no longer
accepts `--hmac-key` because the value would leak via `ps(1)` and shell
history.

Exit codes mirror the audit command (0 OK, 1 mismatch, 2 inputs missing).
The verifier also compares the report's `auditor_binary_sha256` against
the currently installed auditor and emits a note on drift — useful for
long-lived audit trails where the producing auditor may have been
upgraded between audit time and verification time.

---

## 8 · Attestation bundles (regulated environments)

The HMAC signature proves "someone with the symmetric key signed this".
For regulated environments — submissions, third-party audits, long-term
archival — a symmetric primitive is the wrong shape: anyone who can
verify can also forge. v0.2 adds **attestation bundles**: an
Ed25519-signed, file-hash-anchored, self-contained directory that a
third party can verify without ever talking to the producing auditor.

### Producing a bundle

```bash
pip install -e ".[bundle]"             # adds the cryptography dep
export AUDITOR_HMAC_KEY="..."
export AUDITOR_ED25519_KEY="$(openssl rand -hex 32)"   # 32-byte signing seed

harness-audit audit --ontology examples/fintech_minimal.yaml
harness-audit bundle reports/<sha256>/ \
  --ontology examples/fintech_minimal.yaml \
  --out-dir ./bundles
```

The produced `bundles/bundle-<sha>/` contains:

```
manifest.json            canonical metadata + per-file SHA-256
manifest.sig.ed25519     detached Ed25519 signature over manifest.json
pubkey.ed25519           hex-encoded public verification key
report.json, report.md   the audit verdict
inputs/                  copies of the ontology and any --previous/--taxonomy
replay/replay.sh         one-command audit replay against the bundled inputs
```

If `AUDITOR_ED25519_KEY` is unset, an ephemeral keypair is generated and
the public key is bundled. Publish the public key out-of-band (release
notes, ATOM feed, internal registry) so verifiers can pin it.

### Verifying a bundle (with pinning)

```bash
harness-audit verify-bundle bundles/bundle-<sha>/ \
  --pinned-pubkey "<expected hex pubkey>" \
  --pinned-binary-sha256 "<expected auditor binary hash>"
```

Both pins are optional: omit them for a structural check (file hashes +
signature self-consistency), include them for "I expect this bundle came
from THIS publisher running THIS auditor build". Pinning is the path
that turns a bundle from "valid signature" into "valid signature from
the producer I trust".

### Library use

```python
from pathlib import Path

from harness_auditor.bundle import (
    BundleInputs, build_bundle, verify_bundle,
)

outcome = build_bundle(
    BundleInputs(report_dir=Path("reports/<sha>/"), ontology=Path("o.yaml")),
    out_dir=Path("bundles"),
    ed25519_private_key_hex="<64 hex chars>",  # or None for ephemeral
)

verify_bundle(
    outcome.bundle_dir,
    pinned_pubkey_hex="<expected>",
    pinned_binary_sha256="<expected>",
)
```

Both functions raise `BundleError` on any failure; the message names the
failing invariant (hash mismatch, signature failure, pin mismatch).

---

## Stability and versioning

* Anything in `harness_auditor.__all__` is **stable**. Breaking changes
  require a major version bump and a CHANGELOG entry.
* `LoaderMismatchError.mismatches` (the structured dict) is stable; the
  rendered string is not — pin behaviour to the dict.
* `CriterionDefinition` is a frozen dataclass; adding new fields is a
  backwards-compatible minor change as long as they carry a default.
* `Environment` and `AuditReport` are Pydantic models with
  `extra="forbid"`; downstream consumers should pin a major and read the
  CHANGELOG before upgrading minors.
* `BUNDLE_FORMAT` is part of the bundle contract: any backwards-
  incompatible change to the manifest shape bumps the version suffix
  (`ragf-audit-bundle/v1` → `/v2`) and v1 verifiers reject v2 bundles
  explicitly rather than silently misreading them.
