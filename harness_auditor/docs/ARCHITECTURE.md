# Architecture · End-to-end data flow

The auditor is a small, single-purpose pipeline. There are six stages, and
each one is replaceable. Stage 6 is optional and lives behind the
`[bundle]` install extra.

```
        ┌─────────────────────┐
   1.   │  YAML ontology      │   ← user input
        └──────────┬──────────┘
                   │ pydantic validation + SHA-256
                   ▼
        ┌─────────────────────┐
   2.   │  Loader             │   src/harness_auditor/loader.py
        │  YAML → Cypher CREATE
        └──────────┬──────────┘
                   │ idempotent batched UNWIND
                   ▼
        ┌─────────────────────┐
   3.   │  Neo4j 5.26 + GDS   │   docker-compose.yml + advisory fcntl lock
        │  (ephemeral sandbox)│   tmpfs, 127.0.0.1, GDS plugin loaded
        └──────────┬──────────┘
                   │ Bolt
                   ▼
        ┌─────────────────────┐
   4.   │  Runner             │   src/harness_auditor/runner.py
        │  Execute CC-NN.cypher per criterion
        │  Collect rows + latency_ms + status
        └──────────┬──────────┘
                   │ List[CriterionResult]
                   ▼
        ┌─────────────────────┐
   5.   │  Report             │   src/harness_auditor/report.py
        │  JSON + Markdown + domain-separated HMAC-SHA256
        └──────────┬──────────┘
                   │ reports/<sha>/{report.json, report.md, report.sig}
                   ▼
        ┌─────────────────────┐
   6.   │  Bundle (optional)  │   src/harness_auditor/bundle.py
        │  Ed25519-signed self-contained attestation
        └─────────────────────┘
```

## Stage 1 · Input validation

The YAML is parsed and validated against the Pydantic models in
`schemas/ontology_schema.py`. Validation is strict (`extra="forbid"`); any
unknown field causes the auditor to refuse the run. The canonical JSON
representation of the ontology is hashed (SHA-256) immediately after
validation. That digest accompanies the report.

## Stage 2 · Loader

The loader translates the validated `Ontology` object into Cypher `CREATE`
statements. It uses `UNWIND` over typed lists to load each node category in
a single batched transaction. The expected node and relationship counts
after loading are asserted by an in-line sanity check before the runner
proceeds; any mismatch raises `LoaderMismatchError` and the auditor aborts
fail-closed.

The exact node labels, relationship types, properties, uniqueness
constraints and cardinality invariants are pinned in
[`docs/GRAPH_MODEL.md`](GRAPH_MODEL.md) — the authoritative contract every
Cypher query and every new CC must respect.

## Stage 3 · Sandbox

Neo4j 5.26 Community with the Graph Data Science plugin. `tmpfs` for
`/data` and `/logs`, so every `down` produces a clean slate. Ports bound to
`127.0.0.1` only. The sandbox is not intended to be shared between
concurrent audits — each audit assumes exclusive ownership of the database
and begins with `MATCH (n) DETACH DELETE n` to clear any residual state.

To prevent two `harness-audit audit` invocations from racing that wipe,
every audit takes an **advisory file lock** (`fcntl.flock`) on
`<reports_dir>/.audit.lock` before opening the Bolt connection. A second
concurrent invocation against the same `--reports-dir` raises
`AuditLockBusy` and exits 3 with a diagnostic naming the lock path. The
lock is POSIX-only; on Windows the auditor emits a yellow warning and
continues without it (concurrent-audit safety becomes the user's
responsibility there). The lock and the Neo4j driver are managed through
a single `contextlib.ExitStack`, so partial failures clean up uniformly.

GDS is required only by CC-11 (Constraint Centrality), which uses
`gds.pageRank.stream` over the SUPERSEDES subgraph. The other ten criteria
are pure Cypher and would run on a community image without plugins; see
[`docs/decisions/ADR-001-gds-scope.md`](decisions/ADR-001-gds-scope.md) for
the scoping rationale.

## Stage 4 · Runner

The runner iterates the **effective registry**, which is the built-in
`REGISTRY` tuple (the canonical eleven CCs) concatenated with any user
criteria added via `register_criterion`. For each entry it reads the
`.cypher` file from `definition.query_dir` (custom CCs) or from the
runner's `queries_dir` argument (built-ins), splits it on top-level
semicolons (Cypher comments stripped), executes the statements in order
against the open session, captures the rows from the **last** statement
as evidence, measures wall-clock latency, and applies the `expected_pass`
predicate (empty → `PASS`, non-empty → `FAIL`) to derive a status.
A `Neo4jError` raised during execution produces status `ERROR`, which the
aggregator treats as `FAIL` for blocking criteria.

Criteria that require optional inputs advertise a `skip_if` hook that
inspects the graph before the query runs and returns `SKIP` cleanly when
the precondition is absent. The hooks are graph-based, not flag-based, so
they work whether the runner is invoked through `cli.py` or directly from
Python.

| CC | Precondition | Probe |
|---|---|---|
| CC-07 | `ConstraintPrev` label present (i.e. `--previous` was loaded) | `db.labels()` |
| CC-10 | `TaxonomyEntry` label present (i.e. `--taxonomy` was loaded) | `db.labels()` |
| CC-11 | GDS plugin loaded **and** at least one `SUPERSEDES` edge present (probes evaluated in this order) | `gds.version()` + `db.relationshipTypes()` |

The probe queries use `db.labels()` / `db.relationshipTypes()` to avoid the
`UnknownLabelWarning` / `UnknownRelationshipTypeWarning` Neo4j attaches to
patterns that reference a never-instantiated identifier.

Query parameters propagate through a single global `query_params` dict
the CLI populates from env vars:

| Parameter | Source env var | Default | Consumer |
|---|---|---|---|
| `threshold_ratio` | `CC11_THRESHOLD_RATIO` | `1.3` | CC-11 |
| `cc11_hysteresis` | _(not user-configurable; baked at `0.05`)_ | `0.05` | CC-11 |
| `coverage_threshold` | `CC06_COVERAGE_THRESHOLD` | `0.85` | CC-06 |

Neo4j silently ignores parameters not referenced by a given query, so
per-criterion plumbing stays uniform. User-registered CCs receive the
same parameter dict.

User-defined CCs are documented in [`INTEGRATION.md`](INTEGRATION.md) §6
and walked through end-to-end in `examples/custom_cc/`.

## Stage 5 · Report

Three artifacts are written under `reports/<ontology_sha256>/`:

- `report.json` — canonical compact JSON. Two **provenance fields** are
  always present:
    - `auditor_binary_sha256` — SHA-256 over every `*.py` and `*.cypher`
      file under the package root, including `_attestation.py` itself
      (sorted POSIX paths, normalised line endings). Detects post-hoc
      edits to the auditor.
    - `environment` — a self-contained snapshot of the producing stack:
      `auditor_version`, `auditor_binary_sha256` (mirrored from the
      top-level field for one-block reads), `python_version`, `platform`,
      `neo4j_version` (probed via `dbms.components()`), `gds_version`
      (probed via `gds.version()`; `null` when GDS is not installed).
      The top-level provenance fields and the `environment` block are
      kept consistent by `build_report`; v0.3 will drop the top-level
      duplicates entirely.
- `report.md`   — rendered narrative (auto-generated from the JSON).
- `report.sig`  — **domain-separated** HMAC-SHA256, hex-encoded:

  ```
  signature = HMAC-SHA256(AUDITOR_HMAC_KEY,
                          HMAC_DOMAIN_TAG ‖ canonical_json_bytes)

  HMAC_DOMAIN_TAG = b"harness-auditor:report:v1\0"
  ```

  The domain tag scopes the signature to this auditor and this
  report-format version, preventing a signature replay onto any other
  artefact a holder of the same key may sign. The key is read from
  `AUDITOR_HMAC_KEY`. If unset, the auditor refuses to sign and emits
  the report with status `REQUIRES_REVIEW` regardless of criterion
  outcomes. **Breaking change vs v0.1.0**: signatures produced by
  v0.1.0 (un-tagged scheme) do not verify under v0.2.0.

The signature lets a third party verify report integrity without trusting
the auditor process or the Neo4j sandbox. The pattern matches the
HMAC-chained audit ledger used elsewhere in RAGF deployments and described
in §6 of the v2.4 paper.

### Verification

A separate CLI subcommand re-checks an existing report without re-running
the audit:

```bash
export AUDITOR_HMAC_KEY="..."
harness-audit verify reports/<sha256>/
```

The key is read exclusively from the environment; the CLI deliberately
does not accept a `--hmac-key` flag because a value passed on the
command line would leak via `ps(1)` and shell history. Exit codes:
0 on a valid signature, 1 on mismatch (tampered JSON, wrong key, or a
swapped `.sig`), 2 when the inputs are missing or the key was not
provided. When the verification succeeds, the command also compares the
report's `auditor_binary_sha256` to the currently installed auditor's
hash and emits a `note` if they differ — useful for confirming
continuity in long-lived audit trails.

## Stage 6 · Bundle (optional)

For audit trails that need to survive outside the producing
organisation — regulatory submissions, third-party verifications,
long-term archival — the HMAC primitive is the wrong shape: anyone who
can verify a symmetric signature can also forge one. Stage 6 wraps an
existing Stage 5 output into an **attestation bundle**: a self-contained,
Ed25519-signed directory that a third party can verify with just the
producer's public key.

```bash
pip install -e ".[bundle]"   # the cryptography extra
harness-audit bundle reports/<sha>/ --ontology examples/fintech_minimal.yaml
# → bundles/bundle-<sha>/{manifest.json, manifest.sig.ed25519, pubkey.ed25519,
#                         report.json, report.md, report.sig,
#                         inputs/, replay/replay.sh}
```

The bundle records:

- The audit artefacts (`report.json`, `report.md`, `report.sig`) byte-for-byte.
- The inputs the audit consumed (ontology, optional previous, optional taxonomy).
- A `manifest.json` listing every file with its SHA-256, plus the
  `auditor_binary_sha256` for binary-pin continuity.
- A detached Ed25519 signature over the canonical manifest.
- A `replay/replay.sh` that re-runs the audit against the bundled inputs
  so a verifier can confirm reproducibility.

`harness-audit verify-bundle <bundle-dir>` validates structure +
signature; `--pinned-pubkey` and `--pinned-binary-sha256`
(or the env vars `AUDITOR_ED25519_PIN_PUBKEY` /
`AUDITOR_BINARY_PIN_SHA256`) elevate the verification from
"valid signature" to "valid signature from the producer I trust running
the auditor build I trust". The bundle format is versioned
(`ragf-audit-bundle/v1`); verifiers reject unknown formats so a
future-skewed bundle cannot be silently misread.

The Ed25519 signing seed is read from `AUDITOR_ED25519_KEY` (64 hex
chars = 32 bytes). When unset, an ephemeral keypair is generated and the
public key is bundled; the verifier must pin the pubkey out-of-band (via
release notes, internal registry, or similar) for the bundle to convey
producer identity. See `INTEGRATION.md` § 8 for the regulated-environment
workflow.

## Failure modes and fail-closed behaviour

| Failure | Behaviour |
|---|---|
| YAML parse error | Refuse to run. Exit code 2. Diagnostic names the file and offending line. |
| Pydantic validation error | Refuse to run. Exit code 2. Diagnostic enumerates every offending field path. |
| Neo4j unreachable | Refuse to run. Exit code 3. Diagnostic prints the URI and suggests `make up`. |
| Neo4j authentication failed | Refuse to run. Exit code 3. Diagnostic names the env vars to check. |
| `AuditLockBusy` — concurrent audit holds the advisory lock | Refuse to run. Exit code 3. Diagnostic names the lock file and recommends waiting or using a different `--reports-dir`. |
| GDS plugin missing (CC-11 requested) | CC-11 SKIPs with reason "GDS plugin not available — CC-11 requires gds.pageRank.stream"; other CCs run normally. |
| Per-criterion query error (Neo4jError) | Status `ERROR` for that criterion → `FAIL` in aggregate. |
| Loader sanity-check mismatch | Refuse to run. Exit code 3. `LoaderMismatchError` names the kind and the probable cause per kind. |
| HMAC key missing at audit time | Report status forced to `REQUIRES_REVIEW`; `report.sig` is omitted. |
| HMAC mismatch at verify time | `harness-audit verify` exits 1 with a per-cause diagnostic (wrong key / tampered JSON / replaced sig). |
| `cryptography` not installed when invoking `bundle` / `verify-bundle` | Refuse to run. Exit code 2. Diagnostic suggests `pip install -e ".[bundle]"`. |
| Bundle hash mismatch / signature failure / pin mismatch | `harness-audit verify-bundle` exits 1 with the specific invariant that failed. |
| Any blocking criterion FAIL or ERROR | Verdict `FAILED`. Exit code 1. |
| Any advisory criterion FAIL | Verdict `REQUIRES_REVIEW`. Exit code 1. |
| All criteria PASS or SKIP/WARN | Verdict `PASSED`. Exit code 0. |
