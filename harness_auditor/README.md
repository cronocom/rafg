# RAGF Ontology Auditor

> **Certifica la jaula, antes de meter al pájaro.**
>
> Pre-execution certification of governance harnesses, expressed as Cypher queries over Neo4j.

The RAGF Ontology Auditor takes a candidate governance ontology (YAML), loads it into
an ephemeral Neo4j 5.26 sandbox, and evaluates it against a battery of certification
criteria. Each criterion is a Cypher query that returns structured evidence. The
auditor emits a domain-separated HMAC-signed report
(`PASSED` / `REQUIRES_REVIEW` / `FAILED`) and, optionally, an Ed25519-signed
**attestation bundle** suitable for inclusion in a regulatory or academic audit trail.

This is the operational artifact accompanying the RAGF addendum
*"Auditing the Boundary: Pre-Execution Certification of LLM-Generated Governance Harnesses"*.

---

## Why this exists

The core RAGF claim is that *governance harnesses* — not the underlying LLMs — are
the certifiable component of an agentic system. That argument is incomplete unless we
can certify the harness itself before it touches production traffic. When the harness
is hand-written that is a code review; when fragments of it are generated, refactored,
or extended by an LLM, code review is insufficient. The Auditor closes that gap by
treating the harness as a graph and applying structural, semantic, and integrity
checks to it before deployment.

---

## The eleven certification criteria

| ID | Role | Mechanism | Detects |
|----|------|-----------|---------|
| **CC-01** Verb groundedness | blocking | Cypher | Verbs with no `MUST_SATISFY` edge to any `Regulation` |
| **CC-02** Constraint reachability | blocking | Cypher | Constraints whose `parameter` is not in their verb's `payload_schema` |
| **CC-03** Orphan regulations | advisory | Cypher | Non-informational regulations never `REFERENCES`'d by any constraint |
| **CC-04** `SUPERSEDES` cycles | blocking | Cypher | Cyclic precedence in conditional supersession (incl. self-loops) |
| **CC-05** Precedence collision | blocking | Cypher (aggregate) | Two constraints on the same verb with the same `precedence_level` |
| **CC-06** Coverage map | advisory | Cypher (aggregate) | Per-verb regulatory coverage below the `CC06_COVERAGE_THRESHOLD` floor (default 0.85) |
| **CC-07** Drift delta | blocking | Cypher (diff) | Constraints removed vs. previous version — requires `--previous` |
| **CC-08** Authority gradient | blocking | Cypher | `min_amm_level` non-monotonic with verb `risk_level` |
| **CC-09** Fail-closed defaults | blocking | Cypher | Any `decision_if_violated = ALLOW` — runtime gate against post-schema drift |
| **CC-10** Hallucinated verbs | blocking | Cypher | Verbs outside the registered taxonomy — requires `--taxonomy` |
| **CC-11** Constraint centrality | advisory | Cypher + GDS PageRank | Base constraints whose edit cascades over many supersessors |

All eleven ship in v0.2.0. CC-07, CC-10 and CC-11 SKIP automatically when their
optional input or graph precondition is absent. CC-11 also SKIPs cleanly when
the GDS plugin is missing from the Neo4j installation — see
[`docs/CRITERIA.md`](docs/CRITERIA.md) § CC-11 for the contract (including the
hysteresis margin baked into the effective threshold) and
[`docs/GRAPH_MODEL.md`](docs/GRAPH_MODEL.md) for the graph schema each query
relies on.

CC-11 is the only criterion that uses the Graph Data Science plugin
(`gds.pageRank.stream`); see
[`docs/decisions/ADR-001-gds-scope.md`](docs/decisions/ADR-001-gds-scope.md)
for the scoping rationale.

---

## Quickstart

These commands are copy-paste-ready. The expected output is shown next to
each step; if you see something different, jump to **Troubleshooting** at
the end of the section.

### 0 · Prerequisites

```bash
# Docker is running and the daemon is reachable
docker info >/dev/null && echo "docker: OK"
# → docker: OK

# Python 3.11 or newer (the package targets 3.11+)
python3 --version
# → Python 3.11.x  (or 3.12.x / 3.13.x)

# Port 7687 is free (the Bolt port the sandbox binds to)
(! lsof -i :7687 >/dev/null 2>&1) && echo "port 7687: free"
# → port 7687: free
```

If any check fails, see **Troubleshooting** before continuing.

### 1 · Install the auditor

```bash
git clone https://github.com/cronocom/ragf && cd ragf/harness_auditor
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# → Successfully installed harness-auditor-0.2.0 ...
```

Optional extras:

```bash
pip install -e ".[dev,notebook]"   # adds Jupyter, pandas, matplotlib for notebooks/
pip install -e ".[dev,bundle]"     # adds cryptography for Ed25519 attestation bundles
pip install -e ".[dev,notebook,bundle]"   # everything
```

### 2 · Start the ephemeral Neo4j sandbox

```bash
make up
# → Container ragf-auditor-neo4j Starting
# → Container ragf-auditor-neo4j Started
# → Waiting for Neo4j to become healthy...
# → Neo4j is healthy.
```

First run pulls the `neo4j:5.26-community` image (~500 MB) and the Graph
Data Science plugin; allow up to 2 minutes. Subsequent runs are instant.

### 3 · Export an HMAC key (recommended)

```bash
export AUDITOR_HMAC_KEY="dev-only-not-for-production"
```

Without this, every verdict is **forced to** `REQUIRES_REVIEW` — see
[`docs/ARCHITECTURE.md §Stage 5`](docs/ARCHITECTURE.md). Use a real secret
in CI, not a constant. The key is read exclusively from the environment;
there is no `--hmac-key` flag because a value passed on the command line
would leak via `ps(1)` and shell history.

### 4 · Audit the clean reference ontology

```bash
make audit ONTOLOGY=examples/fintech_minimal.yaml
# → harness-auditor v0.2.0
# →   ontology      : examples/fintech_minimal.yaml
# →   domain        : fintech_minimal v1.0.0
# →   sha256        : f17a09946df31c9591e81bf4fbd92892bf749f5d8fc0761f9b4b3545a48ee12d
# →   CC-06 coverage: 0.85 (min ratio)
# →   CC-11 ratio   : 1.30x mean (effective 1.35x with 0.05 hysteresis)
# → ...
# → verdict: PASSED
# →   PASS: 8  WARN: 0  FAIL: 0  SKIP: 3
```

Exit code 0. `CC-07`, `CC-10`, `CC-11` `SKIP` because their preconditions
(`--previous`, `--taxonomy`, any `SUPERSEDES` edge) are not present.

### 5 · Audit the deliberately broken ontology

```bash
make audit ONTOLOGY=examples/fintech_seeded_faults.yaml
# → verdict: FAILED
# →   PASS: 1  WARN: 0  FAIL: 8  SKIP: 2
# → ... 8 CCs flagged (CC-01/02/03/04/05/06/08/11)
```

Exit code 1. Each failing CC prints a one-line diagnostic. CC-11 fires as
a consequence of the CC-04 SUPERSEDES cycle — see
[`docs/CRITERIA.md`](docs/CRITERIA.md) § CC-11 for the cycle/centrality
interaction.

### 6 · Verify the signature

```bash
harness-audit verify reports/f17a09946df31c9591e81bf4fbd92892bf749f5d8fc0761f9b4b3545a48ee12d/
# → OK: report.sig is valid for reports/<sha256>/report.json
```

The verifier reads `AUDITOR_HMAC_KEY` from the environment and compares
the report's `auditor_binary_sha256` to the currently installed
auditor — a mismatch is reported as a `note` (not an error) so the
operator can confirm continuity in long-lived audit trails. Exit code 1
on signature mismatch, 2 on missing inputs.

### 7 · (optional) Package an attestation bundle

For audit trails that need to survive outside your organisation, build an
Ed25519-signed self-contained bundle:

```bash
pip install -e ".[bundle]"      # cryptography is an optional extra
export AUDITOR_ED25519_KEY="$(python -c 'from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; print(Ed25519PrivateKey.generate().private_bytes_raw().hex())')"
harness-audit bundle reports/<sha256>/ --ontology examples/fintech_minimal.yaml
# → OK: bundle built at bundles/bundle-<sha>/
# →   manifest         : ...
# →   signature        : ...
# →   pubkey           : ...
```

A third party can verify the bundle without access to this auditor:

```bash
harness-audit verify-bundle bundles/bundle-<sha>/
# → OK: bundle verified at bundles/bundle-<sha>/
# →   verdict          : PASSED
# →   pubkey           : ...
```

Pin the producer's public key out-of-band (publish in release notes,
CHANGELOG, or the company website) and the verifier can pass it via
`--pinned-pubkey` for trust-but-verify confirmation. See
`docs/INTEGRATION.md` § Attestation bundles for the regulated-environment
workflow.

### 8 · Tear down

```bash
make down
# → Container ragf-auditor-neo4j Removed
```

The sandbox is `tmpfs`-backed, so every `down` returns a clean slate.

---

### Reports

Each audit writes three artifacts to `reports/<ontology_sha256>/`:

| File | Contents |
|---|---|
| `report.json` | Canonical JSON verdict, ready for ingestion by any downstream tool. |
| `report.md`   | Human-readable Markdown narrative with evidence per CC. |
| `report.sig`  | Domain-separated HMAC-SHA256 over `report.json`, hex-encoded. See `docs/CRITERIA.md` § Aggregation for the exact scheme; verifiable via `harness-audit verify`. |

The `bundle` command additionally packages these artifacts into a
self-contained `bundles/bundle-<sha>/` directory with an Ed25519
signature, a public key, a manifest, the inputs, and a replay script.
See § 7 above.

---

### Useful flags and operational commands

| Command / flag | Purpose |
|---|---|
| `harness-audit audit --dry-run` | Validate YAML, schema, queries directory, and the registry without touching Neo4j. Sub-second pre-commit / PR gate. |
| `harness-audit audit --strict-builtins` | Ignore any user-registered CCs and run only the canonical 11 built-ins. Use in CI gates that want trust-but-verify isolation. |
| `harness-audit verify <reports/...>` | HMAC + binary-drift verification of a previously produced report. |
| `harness-audit bundle <reports/...> --ontology X.yaml` | Build an Ed25519-signed attestation bundle from an existing report. |
| `harness-audit verify-bundle <bundles/...>` | Validate a bundle's signature + file hashes + (optional) pubkey / binary pin. |
| `make notebook-test` | Headlessly executes the demo notebook end-to-end. **Requires a live sandbox** — run `make up` first. Fast-fails with a clear message when Bolt is not reachable. |

---

### Troubleshooting

| Symptom | Probable cause | Fix |
|---|---|---|
| `docker info` reports `Cannot connect to the Docker daemon` | Docker Desktop / Engine not running. | macOS/Win: open Docker Desktop and wait for the daemon. Linux: `sudo systemctl start docker`. |
| `make up` succeeds but `Neo4j did not become healthy in 90s` | Cold first-run is downloading the image + GDS plugin (~500 MB). | `docker logs ragf-auditor-neo4j` to watch progress; re-run `make wait` after a few minutes. |
| `make up` reports `bind: address already in use` on port 7687 | Another Neo4j or service holds the port. | `lsof -i :7687` to identify; stop the other service, or set `NEO4J_URI` to a different host:port and re-run with the custom URI. |
| `pip install -e .` fails with `error: externally-managed-environment` (PEP 668) | System Python on Debian/Ubuntu/Fedora refuses non-virtualenv installs. | Always install inside a venv: `python3 -m venv .venv && source .venv/bin/activate`. |
| `command not found: python` after install | Many distros ship only `python3` in PATH. | The Makefile defaults to `python3`. To use a different binary: `make audit PYTHON=/path/to/python ONTOLOGY=...`. |
| `make audit` returns exit 2 immediately with "ontology not found" | The `ONTOLOGY=` path is relative to the current directory. | Use an absolute path, or run `make audit` from the repo root. |
| `harness-audit audit` exits with "Neo4j unreachable" | Sandbox not up, or `NEO4J_URI` points elsewhere. | `make up && make wait`. The CLI hint shows the exact commands. |
| `make notebook-test` exits with `Neo4j sandbox is not reachable at bolt://127.0.0.1:7687` | Same root cause as the row above, but the notebook does not have the CLI's friendly diagnostic — the `_check-bolt-up` precondition in the Makefile prints the hint before running nbconvert. | `make up` first; then `make notebook-test`. Common one-liner: `make up && make notebook-test && make down`. |
| `harness-audit audit` exits with `another auditor process holds the lock` | Another `harness-audit audit` is running against the same `--reports-dir`. The auditor uses an advisory `fcntl.flock` to prevent two pipelines from racing the `MATCH (n) DETACH DELETE n` wipe. | Wait for the other run to finish, or pass a different `--reports-dir`. |
| CC-11 reports `SKIP: GDS plugin not available` | Running against a Neo4j that does not have the Graph Data Science plugin loaded. | The bundled `docker-compose.yml` loads GDS automatically; if you point the auditor at a different Neo4j, install GDS there too — or accept that CC-11 will SKIP. The other ten CCs run unaffected. |
| `harness-audit bundle` exits with `the 'cryptography' library is required for attestation bundles` | The `[bundle]` extra is not installed. | `pip install -e ".[bundle]"` (the optional dependency that brings in `cryptography>=42.0`). |
| Audit verdict is always `REQUIRES_REVIEW` even on the clean ontology | `AUDITOR_HMAC_KEY` is unset. | `export AUDITOR_HMAC_KEY="..."` before invoking the CLI; the verdict will then reflect the criterion outcomes. |
| Audit fails with `LoaderMismatchError` and an unfamiliar count | A reference in the YAML points at an undeclared entity (regulation code, verb name, or `supersedes` target). | The error message names the offending kind and the probable cause; fix the dangling reference and re-run. |
| `test_hash_matches_frozen_baseline` fails after a code change | The package's source files changed and the frozen attestation baseline is stale. | This is the release ritual: refresh `tests/fixtures/_attestation_expected.txt` with `python -c "from harness_auditor._attestation import auditor_binary_sha256; print(auditor_binary_sha256())" > tests/fixtures/_attestation_expected.txt` and bump the hash in `CHANGELOG.md` so verifiers can pin it. |

---

## Project layout

```
harness_auditor/
├── README.md                   # This file
├── CHANGELOG.md                # Keep-a-Changelog format, semver-aware
├── CONTRIBUTING.md             # Local setup, PR checklist, commit conventions
├── docker-compose.yml          # Neo4j 5.26 Community + Graph Data Science plugin
├── pyproject.toml              # Python package metadata + tool config
├── Makefile                    # up / down / audit / test / lint / install / notebook-test
├── src/harness_auditor/
│   ├── __init__.py             # Public API (see __all__)
│   ├── _attestation.py         # SHA-256 self-attestation over package source
│   ├── _audit_lock.py          # POSIX advisory lock guarding the audit pipeline
│   ├── _environment.py         # Python/OS/Neo4j/GDS version probes
│   ├── bundle.py               # Ed25519-signed attestation bundles (v0.2 differentiator)
│   ├── cli.py                  # Typer entrypoint: audit + verify + bundle + verify-bundle
│   ├── loader.py               # YAML → Cypher CREATE + sanity check
│   ├── runner.py               # CC registry, execution, skip_if hooks
│   ├── report.py               # JSON + Markdown + domain-separated HMAC sign
│   ├── queries/                # Bundled CC-NN.cypher files (package data)
│   │   ├── cc01_verb_groundedness.cypher
│   │   ├── cc02_constraint_reachability.cypher
│   │   ├── cc03_orphan_regulations.cypher
│   │   ├── cc04_supersedes_cycles.cypher
│   │   ├── cc05_precedence_collision.cypher
│   │   ├── cc06_coverage_map.cypher
│   │   ├── cc07_drift_delta.cypher
│   │   ├── cc08_authority_gradient.cypher
│   │   ├── cc09_fail_closed_defaults.cypher
│   │   ├── cc10_hallucinated_verbs.cypher
│   │   └── cc11_constraint_centrality.cypher
│   └── schemas/
│       ├── ontology_schema.py  # Pydantic models for input YAML (Ontology + Taxonomy)
│       └── report_schema.py    # Pydantic models for the report (AuditReport + Environment)
├── examples/
│   ├── README.md                       # Documented fixtures + expected verdicts
│   ├── fintech_minimal.yaml            # Clean ontology — should PASS
│   ├── fintech_seeded_faults.yaml      # Deliberately broken — should FAIL
│   └── custom_cc/                      # Worked example: user-registered CC-X1
│       ├── README.md
│       ├── register.py
│       └── queries/
│           └── ccx_critical_must_deny.cypher
├── notebooks/
│   └── 01_quickstart.ipynb     # End-to-end demo against a live sandbox
├── docs/
│   ├── CRITERIA.md             # Full specification of the 11 CCs + user-defined CC contract
│   ├── ARCHITECTURE.md         # End-to-end data flow, failure modes
│   ├── GRAPH_MODEL.md          # Authoritative graph schema (v1.0)
│   ├── INTEGRATION.md          # Library-usage guide, integration patterns, bundle workflow
│   └── decisions/
│       └── ADR-001-gds-scope.md  # Why GDS is scoped to CC-11 only
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── _attestation_expected.txt           # Frozen attestation baseline (release ritual)
    │   ├── tiny_ontology.yaml
    │   ├── fintech_minimal_v0_9.yaml           # for CC-07
    │   ├── fintech_taxonomy_complete.yaml      # for CC-10 (PASS path)
    │   ├── fintech_taxonomy_partial.yaml       # for CC-10 (FAIL path)
    │   └── fintech_centrality_concentrated.yaml  # for CC-11
    ├── test_schemas.py             # Schema-level regression (no Neo4j)
    ├── test_report.py              # Aggregation + render (no Neo4j)
    ├── test_attestation.py         # Self-attestation hash invariants + frozen baseline
    ├── test_environment.py         # Environment probes + schema rejection
    ├── test_audit_lock.py          # Advisory-lock contract (POSIX-only)
    ├── test_bundle.py              # Ed25519 bundle build + verify + tamper + pin
    ├── test_custom_cc.py           # Registry extension (pure + integration)
    ├── test_cli_flags.py           # --dry-run + --strict-builtins behaviour
    ├── test_thresholds.py          # CC-06 / CC-11 threshold env var resolution
    ├── test_error_messages.py      # Actionable-diagnostic regression
    ├── test_runner_skip_hooks.py   # CC-07/10/11 skip_if hooks (pure-Python)
    ├── test_verify_command.py      # `verify` subcommand contract
    └── test_examples.py            # Full pipeline; auto-skipped if Neo4j down
```

---

## Configuration

Environment variables that the CLI honours:

| Variable | Default | Purpose |
|---|---|---|
| `NEO4J_URI` | `bolt://127.0.0.1:7687` | Bolt URI of the auditor sandbox |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `auditor_local_only` | Neo4j password |
| `AUDITOR_HMAC_KEY` | _(unset)_ | HMAC-SHA256 key for the report signature. **If unset, verdict is forced to `REQUIRES_REVIEW`** |
| `CC06_COVERAGE_THRESHOLD` | `0.85` | Per-verb regulatory coverage floor. CC-06 flags any verb whose `(matched / declared)` ratio falls below this. Must be in `(0, 1]` |
| `CC11_THRESHOLD_RATIO` | `1.3` | Centrality threshold ratio for CC-11. The Cypher applies `score > (ratio + 0.05) * mean_score`, so the **effective threshold** is `(1.3 + 0.05) = 1.35` of the graph mean by default. See `docs/CRITERIA.md` § CC-11 for the rationale on the hysteresis margin |
| `AUDITOR_ED25519_KEY` | _(unset)_ | Ed25519 signing seed (64 hex chars = 32 bytes) for `harness-audit bundle`. When unset, an ephemeral keypair is generated and the public key is included in the bundle |
| `AUDITOR_ED25519_PIN_PUBKEY` | _(unset)_ | When set, `harness-audit verify-bundle` requires the bundle's pubkey to match this hex value. Equivalent to `--pinned-pubkey` |
| `AUDITOR_BINARY_PIN_SHA256` | _(unset)_ | When set, `harness-audit verify-bundle` requires the bundle's `auditor_binary_sha256` to match. Equivalent to `--pinned-binary-sha256` |

---

## Public API

The auditor is consumable as a CLI **and** as a Python library. Everything
re-exported from the top-level `harness_auditor` package is part of the
**stable** API; anything else is internal and may change between minor
versions without notice.

```python
from harness_auditor import (
    # Pipeline entrypoints
    load, load_previous, load_taxonomy,
    run_all,
    build_report, write_artifacts, aggregate,
    hmac_signature, HMAC_DOMAIN_TAG,
    packaged_queries_dir,
    # Registry extension (custom CCs)
    REGISTRY, AGGREGATOR_ROLE, CriterionDefinition,
    effective_registry, register_criterion,
    unregister_criterion, reset_user_criteria,
    # Ontology schema
    Ontology, Domain, Regulation, Verb, Field, Constraint, Taxonomy,
    # Report schema
    AuditReport, CertificationStatus, CriterionResult, CriterionStatus,
    Environment, Severity,
    # Attestation bundles (v0.2 differentiator; needs the [bundle] extra)
    BUNDLE_FORMAT, BundleInputs, build_bundle, verify_bundle,
    # Errors
    LoaderMismatchError, BundleError, CryptographyMissingError,
)
```

Stability guarantees:

| Tier | Rule | Examples |
|---|---|---|
| **Stable** | Anything in `harness_auditor.__all__`. Breaking changes require a major version bump and a CHANGELOG entry. | `load`, `run_all`, `Ontology`, `AuditReport` |
| **Internal** | Everything else, including private helpers, undocumented attributes, and submodule details. | `harness_auditor.runner._cc01_severity`, `loader._sanity_check` |

See [`docs/INTEGRATION.md`](docs/INTEGRATION.md) for supported library usage
patterns (programmatic loading, custom CCs, CI gate embedding, attestation
bundles).

---

## Relationship to AgentSave

The Auditor is a **RAGF artifact**. It carries no AgentSave branding, no commercial
references, no AgentSave-specific schema. It exists in its own repository
(`github.com/cronocom/ragf`) under an open license. AgentSave consumes it internally
as a CI gate on changes to `ontology_seed_fintech_v1_0.yaml`, but that integration is
opaque to this codebase. Per architectural decision, the public framework (RAGF) and
its commercial implementation (AgentSave) remain strictly separated.

---

## License

Apache-2.0. See [`LICENSE`](../LICENSE) at the repository root.
