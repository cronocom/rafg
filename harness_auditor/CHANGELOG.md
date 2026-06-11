# Changelog

All notable changes to `harness-auditor` are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Stability tiers — see `harness_auditor.__all__` for what counts as the
public API. Anything not re-exported there may change between minor
versions without notice.

---

## [Unreleased]

### Roadmap (v0.3 candidates, explicitly out of v0.2 scope)

- **B1 · Registry-as-a-class**: convert the module-level `REGISTRY` /
  `AGGREGATOR_ROLE` / `_USER_CRITERIA` triplet to a `CriterionRegistry`
  class so consumers can instantiate isolated registries. Today's
  process-wide singleton works but does not compose under multi-tenant
  service patterns.
- **B4 · Drop top-level `auditor_version` / `auditor_binary_sha256`**:
  v0.2 mirrors them from the `Environment` block for a transition period
  so existing readers do not break; v0.3 removes the duplication.
- **B6 · Symmetric aggregation of `ERROR`**: today `aggregate()` treats
  a blocking CC in `ERROR` as `FAILED`, but an advisory CC in `ERROR`
  is invisible — it slips through as `PASSED`. The asymmetry surfaced
  while debugging the notebook's missing-parameter path (CC-06 ran with
  the runner swallowing `Neo4jError` into `ERROR`, and the verdict still
  came out `PASSED`). The right semantic is to treat advisory `ERROR`
  as `REQUIRES_REVIEW`. Deferring to v0.3 because flipping it would
  change the verdict on any user's CI gate that today relies on the
  asymmetry; needs a `--strict-aggregation` migration flag.
- **E1 · Structured logging**: emit `cc.started` / `cc.completed`
  records through `logging.getLogger("harness_auditor")` so library
  consumers can subscribe to pipeline events without scraping the rich
  console output.
- **Bundle replay automation**: today's `replay.sh` invokes the auditor
  and prints a comparison hint; v0.3 will compute the diff against the
  bundled report.json programmatically and exit non-zero on mismatch.

---

## [0.2.0] — 2026-06-11

The "regulated environments" release. Closes the v0.1.0 adversarial-audit
findings, hardens the cryptographic guarantees, and adds the
**Attestation Bundle** — the v0.2 differentiator: a self-contained,
Ed25519-signed, third-party-verifiable certificate of computation.

### Added

#### Attestation bundles (the differentiator)

- New CLI subcommands:
  - `harness-audit bundle <REPORT_DIR> --ontology X.yaml [--previous Y.yaml] [--taxonomy Z.yaml]`
    packages an existing audit into `bundles/bundle-<sha>/` with
    `manifest.json` (canonical), `manifest.sig.ed25519` (detached
    Ed25519), `pubkey.ed25519`, the audit artefacts, the inputs, and a
    `replay/replay.sh` script.
  - `harness-audit verify-bundle <BUNDLE_DIR>` validates every file's
    SHA-256, verifies the Ed25519 signature, and supports
    `--pinned-pubkey` / `--pinned-binary-sha256` for trust-but-verify
    auditors.
- New public API: `harness_auditor.bundle.{build_bundle, verify_bundle,
  BundleInputs, BundleError, BUNDLE_FORMAT}`.
- New optional dependency extra: `pip install -e ".[bundle]"` pulls
  `cryptography>=42.0`. The core auditor still runs without it.
- New env vars: `AUDITOR_ED25519_KEY` (32-byte signing seed as 64 hex
  chars), `AUDITOR_ED25519_PIN_PUBKEY`, `AUDITOR_BINARY_PIN_SHA256`.

#### Hardened security baseline

- **A1 · HMAC domain separation**: the signing scheme now prepends
  `b"harness-auditor:report:v1\\0"` to canonical JSON before HMAC. A
  signature on a `harness-audit` report can no longer be replayed onto
  any other artefact a user signs with the same key. Existing v0.1.0
  signatures are NOT verifiable by v0.2.0 verify — they were produced
  with the un-tagged scheme and are explicitly retired.
- **A2 · No `--hmac-key` CLI flag**: the key is read exclusively from
  `AUDITOR_HMAC_KEY`. CLI args leak via `ps(1)` and shell history.
- **A5 · Advisory file lock**: every `audit` invocation acquires
  `fcntl.flock` on `reports/.audit.lock` to prevent two concurrent
  audits from racing the `MATCH (n) DETACH DELETE n` wipe. Lock and
  Neo4j driver are now managed through `contextlib.ExitStack` so an
  unexpected failure during `__enter__` cleans up without leaking the
  lock file handle.
- **A6 · Selective probe error handling**: `probe_neo4j_version` /
  `probe_gds_version` no longer swallow arbitrary `Neo4jError`; only
  errors whose code or message indicates "procedure / function
  absent" are treated as expected, anything else is re-raised so
  transient failures surface.

#### Frozen attestation baseline

- **A3 + C2**: `auditor_binary_sha256` now includes `_attestation.py`
  itself — a malicious edit to the attester cannot self-conceal. The
  expected baseline is committed at
  `tests/fixtures/_attestation_expected.txt` and asserted on every test
  run. Release ritual: refresh the file, bump the hash in this
  CHANGELOG section.

#### Operational ergonomics

- **E2 · `--dry-run`**: validates YAML, schema, queries directory, and
  registry without touching Neo4j. Sub-second pre-commit / PR gate.
- **E3 · `--strict-builtins`**: forces the audit to ignore any
  user-registered CCs. Trust-but-verify CI gates run with this flag.
- **F1 · CC-06 parametric threshold**: `CC06_COVERAGE_THRESHOLD` env
  var feeds `$coverage_threshold` into the Cypher; the report
  evidence now also returns the threshold that was applied, and the
  runner's PASS / FAIL message no longer hard-codes the default value.
- **F2 · CC-11 hysteresis (documented contract)**: the Cypher applies
  `score > ($threshold_ratio + $cc11_hysteresis) * mean_score` with
  `cc11_hysteresis = 0.05` baked into the release. The CLI prints both
  the requested ratio and the effective ratio at audit start. The
  hysteresis is documented identically in `docs/CRITERIA.md` § CC-11,
  in the README configuration table, and in the cc11 cypher header —
  the formula and the prose now refer to the same number.
- `Makefile`: new `notebook-test` target executes the demo notebook
  headlessly (catches drift between code and demo).

#### Schema rigor

- **B3**: `Constraint.value` rejects mixed-type lists at the Pydantic
  layer — Neo4j stores arrays homogeneously, so the auditor refuses
  inputs the loader would otherwise hit with an opaque Neo4jError.
- **B5**: `Ontology.schema_version` rejects any major != 1 (the
  current supported major). Stops a 2.x YAML from silently producing a
  wrong verdict against a 1.x reader.

#### Performance

- **B2**: `auditor_binary_sha256` is now cached with `functools.cache`.
  Multiple `build_report` calls in the same process amortize to one
  package walk.

### Changed

- **BREAKING (signatures)**: HMAC signatures from v0.1.0 do NOT verify
  under v0.2.0 because of the A1 domain separation. Re-run the audit
  with v0.2.0 to produce a v2 signature. The new `bundle` command
  encapsulates the canonical migration path: a v0.2.0 report wrapped
  in an Ed25519-signed bundle is the long-term format.
- **BREAKING (CLI)**: `harness-audit audit` and `harness-audit verify`
  no longer accept `--hmac-key`. Set `AUDITOR_HMAC_KEY` instead.
- **Internal · `build_report`**: the report's top-level
  `auditor_version` and `auditor_binary_sha256` are now mirrored from
  the `Environment` block (single source of truth) so the two cannot
  drift apart under refactor. JSON shape is unchanged; v0.3 removes the
  top-level duplicates entirely (see Unreleased § Roadmap · B4).
- **Internal · `cli.py`**: lock + driver lifecycle managed through
  `contextlib.ExitStack`, replacing the manual `__enter__` /
  `__exit__` pattern. Externally visible behaviour is unchanged.

### Fixed

- The previous "swallow every Neo4jError" path in environment probes
  could silently report a transient connection issue as "GDS not
  installed". A6 closes this.
- Two concurrent `harness-audit audit` invocations on the same host
  no longer corrupt each other (A5).
- CC-06 PASS message no longer hard-codes `0.85` when the user has
  raised or lowered `CC06_COVERAGE_THRESHOLD`.
- CC-11 effective threshold is now identical in code, in
  `cc11_constraint_centrality.cypher` header, in `docs/CRITERIA.md`
  § CC-11, and in the README configuration table; the previous "1.3
  documented, 1.35 applied" drift is resolved by documenting the
  hysteresis on every surface.
- `notebooks/01_quickstart.ipynb` now defines a single `QUERY_PARAMS`
  dict at the top and passes it everywhere `run_all` / `session.run`
  is invoked. The previous notebook only passed `threshold_ratio`,
  which after F1 + F2 caused
  `Neo.ClientError.Statement.ParameterMissing: coverage_threshold` when
  CC-06's `.cypher` was re-executed inline. `make notebook-test` now
  passes against the full pipeline.

### Housekeeping

- `tests/test_skip_conditions.py` is consolidated into
  `tests/test_runner_skip_hooks.py` and marked for removal. The file
  was never committed to git in the first place (untracked working-tree
  artefact); deleting the local file or letting `git status` ignore it
  is equivalent to the original `git rm` instruction.

### Notes for downstream consumers

- `auditor_binary_sha256` changes any time a package file changes.
  Downstream pipelines that pin the hash MUST upgrade by:
  1. Re-running the audit with v0.2.0.
  2. Recording the new hash from the report's `environment` block.
  3. Updating their pin reference.
- The HMAC signature now proves "this exact bytes were signed by the
  HMAC-key holder for the harness-audit:report:v1 contract". For
  cross-organisation provenance, prefer the Ed25519 bundle.
- CC-11's effective threshold is `(CC11_THRESHOLD_RATIO + 0.05)` of
  the graph mean. A user setting `CC11_THRESHOLD_RATIO=1.3` (the
  default) gets `1.35x mean` as the actual filter cutoff. The
  hysteresis is intentionally not user-configurable in v0.2 — it is a
  property of PageRank's numerical stability, not a policy lever.
- Library callers that build their own `query_params` dict for
  `run_all` MUST include every parameter referenced by any CC in the
  active registry — Neo4j 5.x raises `ParameterMissing` on referenced-
  but-absent parameters even when the query wraps them in
  `coalesce(...)`. The bundled CCs read `threshold_ratio`,
  `cc11_hysteresis`, and `coverage_threshold`; the notebook
  (`notebooks/01_quickstart.ipynb`) shows the canonical pattern.

---

## [0.1.0] — 2026-06-11

First public release. Eleven certification criteria are shipping, plus the
machinery to add user-defined CCs without forking the package.

### Added

#### Pipeline

- `harness-audit audit` CLI: end-to-end pipeline (YAML → Pydantic → Neo4j
  projection → CC execution → aggregation → HMAC-signed report).
- `harness-audit verify` CLI: re-checks the HMAC signature on a
  previously-produced report, with a continuity-check warning when the
  report's `auditor_binary_sha256` differs from the installed binary.
- Python library API: every symbol re-exported from
  `harness_auditor.__all__` is part of the stable surface (`load`,
  `run_all`, `build_report`, `aggregate`, `Ontology`, `AuditReport`, etc.).

#### Certification criteria

- **CC-01** Verb groundedness (blocking, pure Cypher).
- **CC-02** Constraint reachability (blocking, pure Cypher).
- **CC-03** Orphan regulations (advisory, pure Cypher).
- **CC-04** SUPERSEDES cycles (blocking, pure Cypher,
  variable-length pattern with self-loop detection).
- **CC-05** Precedence collision (blocking, pure Cypher aggregate).
- **CC-06** Coverage map (advisory, pure Cypher aggregate with 0.85
  default threshold).
- **CC-07** Drift delta (blocking, requires `--previous`; SKIPs cleanly
  when absent; severity escalates to CRITICAL when a removed constraint
  carried `DENY`).
- **CC-08** Authority gradient (blocking, severity escalates on
  `risk_level: critical`).
- **CC-09** Fail-closed defaults (blocking; runtime gate against
  post-schema drift via direct Cypher writes).
- **CC-10** Hallucinated verbs (blocking, requires `--taxonomy`; SKIPs
  cleanly when absent).
- **CC-11** Constraint centrality (advisory, GDS `gds.pageRank.stream`
  with configurable threshold; SKIPs cleanly when the GDS plugin is
  absent **or** when no `SUPERSEDES` edge exists in the graph; the GDS
  check runs first to keep diagnostics unambiguous on community-edition
  Neo4j installations).

#### Inputs and outputs

- Ontology YAML schema with Pydantic v2 (`Ontology`, `Domain`,
  `Regulation`, `Verb`, `Field`, `Constraint`; strict `extra="forbid"`,
  identifier regexes, range constraints).
- Taxonomy YAML schema for CC-10 (`Taxonomy`).
- Report artifacts under `reports/<ontology_sha256>/`: `report.json`
  (canonical compact JSON), `report.md` (rendered narrative), `report.sig`
  (HMAC-SHA256, hex).
- `Environment` block in every report capturing
  `auditor_version`, `auditor_binary_sha256`, `python_version`,
  `neo4j_version` (probed via `dbms.components()`), `gds_version` (probed
  via `gds.version()`), and `platform`.
- Self-attestation (`auditor_binary_sha256`) over every `*.py` and
  `*.cypher` under the package root, canonicalised across platforms
  (sorted POSIX paths, normalised line endings).

#### Registry extension

- `CriterionDefinition.query_dir` field — custom CCs may carry their own
  `.cypher` directory; the runner falls back to the bundled set for
  built-ins.
- `register_criterion`, `unregister_criterion`, `reset_user_criteria`,
  `effective_registry` for process-wide custom-CC registration.
- Worked example under `examples/custom_cc/` (CC-X1 "Critical-severity
  must DENY").

#### Documentation

- `README.md` with copy-paste Quickstart, Configuration table, **Public
  API** section, and Troubleshooting matrix (incl. the GDS-missing case).
- `docs/ARCHITECTURE.md` (five-stage pipeline).
- `docs/CRITERIA.md` (full spec of all 11 CCs, including CC-11's two-stage
  skip contract: GDS plugin first, SUPERSEDES second).
- `docs/GRAPH_MODEL.md` (authoritative graph schema with auxiliary
  subgraphs for CC-07/CC-10).
- `docs/INTEGRATION.md` (library-usage guide, three integration patterns,
  custom CC registration walkthrough).
- `docs/decisions/ADR-001-gds-scope.md` (why GDS is scoped to CC-11).
- `notebooks/01_quickstart.ipynb` (executable end-to-end demo). Install
  with `pip install -e ".[notebook]"` to pick up Jupyter + pandas +
  matplotlib.

#### Tests

- Test suite covering: schema invariants, report aggregation, every CC's
  positive/negative path, custom-CC registration, error-message shape,
  self-attestation, environment capture, the verify command, and the
  `skip_if` hooks for CC-07/10/11 in pure-Python form (mocked sessions,
  no Neo4j required).
- Integration tests auto-skip when the Neo4j sandbox is not reachable;
  `requires_neo4j` marker is registered in `pyproject.toml`.

### Notes for downstream consumers

- The HMAC signature alone proves report integrity but not auditor
  provenance — combine with `verify`'s binary-drift check (or pin a
  package version) for the full chain.
- `LoaderMismatchError.mismatches` (the structured dict) is stable; the
  rendered diagnostic string is not. Pin behaviour to the dict.
- `Environment` and `AuditReport` use `extra="forbid"`. Adding fields in a
  minor version is breaking for consumers that round-trip the JSON
  through their own strict schema.
- CC-11's SKIP reason strings are stable and machine-parseable. Two
  distinct reasons exist: `"GDS plugin not available ..."` and
  `"no SUPERSEDES edges ..."`. Downstream pipelines that want to alert on
  GDS misconfiguration (but not on legitimately empty SUPERSEDES graphs)
  can match on the first prefix.

[Unreleased]: https://github.com/cronocom/ragf/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/cronocom/ragf/releases/tag/v0.2.0
[0.1.0]: https://github.com/cronocom/ragf/releases/tag/v0.1.0
