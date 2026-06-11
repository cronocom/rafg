# Certification Criteria · Full specification

This document is the source of truth for the eleven certification criteria
(CCs) that the auditor evaluates. Each criterion is independent: it can fail
without affecting the others. The aggregate verdict is fail-closed — see
§Aggregation.

All eleven criteria are shipped as of v0.2.0. CC-07, CC-10 and CC-11 require
optional inputs or graph preconditions and SKIP automatically when those are
absent. CC-09 is also enforced statically by the Pydantic ontology schema
(`Decision` enum) and exists at runtime to catch drift introduced via direct
Cypher writes that bypass the loader.

---

## Common contract

Every criterion exposes:

| Field | Meaning |
|---|---|
| `criterion_id` | `CC-NN` (zero-padded) for built-ins; user-registered CCs use any pattern matching `^CC-[A-Z0-9][A-Z0-9_-]*$` (e.g. `CC-X1`, `CC-FOO_BAR`). Collisions with built-ins are rejected at registration time. |
| `name` | Human-readable label |
| `mechanism` | `cypher` \| `cypher+gds` \| `cypher+diff` |
| `severity_default` | Default severity if the criterion fires |
| `severity_escalation` | Conditions that escalate severity to `critical` |
| `evidence_query` | Path to the `.cypher` file under the runner's `queries_dir` (built-ins) or the CC's own `query_dir` (user-registered) |
| `expected_pass` | The exact result the query must return for `PASS` |
| `aggregator_role` | `blocking` \| `advisory` |

`blocking` criteria failing any single instance produce `FAILED`. `advisory`
criteria failing produce `REQUIRES_REVIEW`. `PASSED` requires every blocking
criterion to PASS and every advisory criterion to be PASS or WARN.

---

## CC-01 · Verb Groundedness  *(shipped)*

- **Mechanism**: Cypher
- **Severity default**: HIGH
- **Severity escalation**: → CRITICAL when `min_amm_level >= 3`
- **Aggregator role**: blocking
- **Expected pass**: empty result set
- **Detects**: verbs declared in the ontology with no `MUST_SATISFY` edge to
  any regulation. Such verbs cannot produce a regulatorily anchored verdict
  and are inadmissible under the RAGF v2.4 framework.

---

## CC-02 · Constraint Reachability  *(shipped)*

- **Mechanism**: Cypher
- **Severity default**: HIGH
- **Severity escalation**: → CRITICAL when `severity = critical` AND
  `decision_if_violated = DENY`
- **Aggregator role**: blocking
- **Expected pass**: empty result set
- **Detects**: constraints whose `parameter` references a field that is not
  part of the verb's `payload_schema`. At runtime such constraints are
  silently skipped, producing a hidden governance gap.
- **Exclusions**: `required_field`-type constraints (the absence of the field
  is itself the trigger).

---

## CC-03 · Orphan Regulations  *(shipped)*

- **Mechanism**: Cypher
- **Severity default**: MEDIUM
- **Aggregator role**: advisory
- **Expected pass**: empty result set
- **Detects**: regulations declared in the ontology that are never
  `REFERENCED` by any constraint, unless the regulation has
  `informational: true`.
- **Rationale**: orphan regulations bloat the audit graph and dilute coverage
  metrics. Either remove them or mark them informational.

---

## CC-04 · `SUPERSEDES` Cycles  *(shipped)*

- **Mechanism**: Cypher (variable-length pattern over `SUPERSEDES`)
- **Severity default**: CRITICAL
- **Aggregator role**: blocking
- **Expected pass**: no cycle detected (empty result set)
- **Detects**: cycles in conditional precedence, including self-supersedes
  (`A → A`, reported as a component of size 1). A cycle means the evaluator
  cannot pick a deterministic winner, which violates DO-178C-style
  determinism guarantees referenced in the RAGF v2.4 paper.
- **Note**: bounded to paths of length ≤ 50; longer cycles are vanishingly
  unlikely in real ontologies and would surface as other CC failures first.
- **Interaction with CC-11**: when CC-04 fires, CC-11 may also fire on the
  cycle members. CC-04 is the source of truth for diagnosing the cycle; the
  CC-11 cycle hits are a side-effect of PageRank's behaviour on cyclic
  subgraphs (see CC-11 § Behaviour on cyclic SUPERSEDES graphs).

---

## CC-05 · Precedence Collision  *(shipped)*

- **Mechanism**: Cypher aggregate (group by `(verb, precedence_level)`)
- **Severity default**: HIGH
- **Aggregator role**: blocking
- **Expected pass**: empty result set
- **Detects**: two or more constraints attached to the same verb with the
  same `precedence_level`. At runtime the evaluator's tie-breaking is
  implementation-defined, which is a determinism violation.

---

## CC-06 · Coverage Map  *(shipped)*

- **Mechanism**: Cypher aggregate with `OPTIONAL MATCH`
- **Severity default**: MEDIUM
- **Aggregator role**: advisory
- **Expected pass**: empty result set (every verb at or above threshold)
- **Detects**: per-verb regulatory coverage gaps. For each verb that declares
  ≥ 1 `MUST_SATISFY`, computes `coverage = (#declared regs with ≥ 1 enforcing
  constraint on this verb) / (#declared regs)`. Verbs below the configured
  threshold are flagged with their list of uncovered regulation codes.
- **Threshold**: `$coverage_threshold` (parameter from the runner; the CLI
  reads `CC06_COVERAGE_THRESHOLD` env var, default `0.85` — the canonical
  RAGF v2.4 dictionary default). Must be in `(0, 1]`. Domains with stricter
  coverage demands can raise it (e.g. `0.95`); more permissive domains can
  lower it. The threshold the query actually applied is returned in every
  evidence row.
- **Note**: verbs with zero `MUST_SATISFY` are not reported here — they are
  CC-01's domain.

---

## CC-07 · Drift Delta  *(shipped)*

- **Mechanism**: Cypher set difference between `Constraint` and
  `ConstraintPrev` nodes (the previous version is loaded with a `Prev`
  label suffix on every node — see `docs/GRAPH_MODEL.md`).
- **Severity default**: HIGH; escalates to CRITICAL when any removed
  constraint carried `decision_if_violated = DENY`.
- **Aggregator role**: blocking. (The CRITERIA v0 spec called for the role
  to flip to advisory when no DENY was dropped; in practice that is a
  per-evidence severity question already covered by the escalation rule,
  so the role itself is kept blocking for clarity.)
- **Expected pass**: empty result set
- **Detects**: silent regressions in semantic coverage when a new ontology
  version drops constraints that the previous version enforced.
- **Operational note**: requires `--previous` pointing to the previous
  ontology YAML. SKIPped automatically when no `ConstraintPrev` node is
  present in the graph (the runner's `skip_if` hook, which uses
  `db.labels()` to avoid the UnknownLabelWarning Neo4j emits when a
  pattern references a never-instantiated label).

---

## CC-08 · Authority Gradient  *(shipped)*

- **Mechanism**: Cypher with a `CASE` mapping `risk_level → required min_amm`
- **Severity default**: HIGH; escalates to CRITICAL when any offending verb
  has `risk_level = 'critical'`.
- **Aggregator role**: blocking
- **Expected pass**: empty result set
- **Canonical mapping**: `low → ≥ 1`, `medium → ≥ 2`, `high → ≥ 3`,
  `critical → ≥ 4`. A domain that needs a different mapping should fork the
  query.
- **Detects**: violations of monotonicity between verb `risk_level` and
  `min_amm_level`. A verb tagged `risk_level: critical` with
  `min_amm_level: 1` is structurally invalid: critical actions cannot be
  delegated to assisted-level agents.

---

## CC-09 · Fail-Closed Defaults  *(shipped)*

- **Mechanism**: Cypher pattern match on `decision_if_violated = 'ALLOW'`
- **Severity default**: CRITICAL
- **Aggregator role**: blocking
- **Expected pass**: empty result set
- **Detects**: constraints with `decision_if_violated = ALLOW`. The auditor
  enforces that constraints emit `ESCALATE` or `DENY` only; an `ALLOW`
  inverts the governance semantic.
- **Threat model**: the Pydantic `Decision` enum rejects `ALLOW` at YAML
  load time, so this CC is specifically a runtime gate against drift
  introduced post-validation — direct Cypher writes from a CI script, an
  APOC import that bypasses the loader, or a manual Browser edit.
  Integration-tested by `tests/test_examples.py::test_cc09_catches_post_load_allow_drift`.

---

## CC-10 · Hallucinated Verbs  *(shipped)*

- **Mechanism**: Cypher set difference against `(:TaxonomyEntry)` nodes.
  The taxonomy is projected by `loader.load_taxonomy` from a separate YAML
  validated by the `Taxonomy` Pydantic model.
- **Severity default**: CRITICAL
- **Aggregator role**: blocking
- **Expected pass**: empty result set
- **Detects**: verbs in the ontology that are not present in the registered
  taxonomy for the declared domain. The taxonomy represents the union of
  verbs ever accepted by any auditor-recognised registry.
- **Operational note**: requires `--taxonomy` pointing to a taxonomy YAML.
  SKIPped automatically when no `TaxonomyEntry` node is present in the
  graph (the runner's `skip_if` hook, which uses `db.labels()` to avoid
  the UnknownLabelWarning Neo4j emits when a pattern references a
  never-instantiated label).
- **Taxonomy YAML schema**:
  ```yaml
  domain: fintech_minimal
  verbs:
    - transfer_funds
    - verify_identity
  ```

---

## CC-11 · Constraint Centrality  *(shipped)*

- **Mechanism**: Graph Data Science (`gds.pageRank.stream`) over a named
  projection of the `SUPERSEDES` subgraph in `NATURAL` orientation.
  Three statements: drop-if-exists projection, project, run PageRank and
  filter by threshold.
- **Severity default**: HIGH
- **Aggregator role**: advisory
- **Expected pass**: empty result set (no constraint above the threshold)
- **Detects**: "base" constraints — those overridden by many other
  constraints via `SUPERSEDES`. PageRank in NATURAL orientation rewards
  nodes with many incoming edges; a constraint with high PageRank IS a
  base. Editing or removing a central constraint cascades silently across
  every supersessor that resolves to it; CC-11 surfaces those constraints
  so they can be marked for elevated human review before any future edit.
- **Threshold (with hysteresis)**: a constraint is reported when

  ```
  score > ($threshold_ratio + $cc11_hysteresis) * mean_score
  ```

  - `$threshold_ratio` is read by `cli.py` from the `CC11_THRESHOLD_RATIO`
    env var (default `1.3`, must be > 1.0).
  - `$cc11_hysteresis` is a stability margin baked into the release at
    `0.05`. PageRank converges iteratively; tolerance noise can flip a
    borderline constraint between PASS and FAIL between two consecutive
    audits of the same input. The margin keeps verdicts reproducible at
    the cost of shifting the *effective* threshold above the documented
    ratio by a constant amount.

  With defaults, the effective threshold is `(1.3 + 0.05) * mean = 1.35 *
  mean`. A user setting `CC11_THRESHOLD_RATIO=1.5` shifts the effective
  threshold to `1.55 * mean`. The hysteresis is intentionally not
  user-configurable in v0.2 — it is a property of the algorithm's
  numerical stability, not a policy lever. If a future release exposes it
  (e.g. for offline analysis at lower margins), this section is the
  authoritative anchor for the contract change.
- **Why advisory**: a legitimately dense `SUPERSEDES` tree is normal in
  mature fintech ontologies. Blocking releases on every dense subgraph
  would produce permanent `FAILED` status without any actionable defect.
  The advisory role produces `REQUIRES_REVIEW`, which is the correct
  signal: "a human must look at these central constraints before any
  edit". Organisations with stricter risk appetite can override the
  aggregator role to `blocking` in their fork.
- **Operational note**: requires the GDS plugin (loaded by the bundled
  `docker-compose.yml`). The runner's `skip_if` checks two preconditions
  before firing CC-11, **in this order**:
    1. The GDS plugin is loaded — probed via `gds.version()`. On a
       community image without the plugin the call raises `Neo4jError`
       and CC-11 SKIPs with the reason
       `GDS plugin not available — CC-11 requires gds.pageRank.stream`.
       The other ten CCs run unaffected, so the report still produces a
       verdict; only the centrality signal is unavailable.
    2. At least one `SUPERSEDES` edge exists — probed via
       `db.relationshipTypes()` to avoid the
       UnknownRelationshipTypeWarning Neo4j emits when a pattern
       references a never-instantiated type. GDS cannot project an empty
       relationship type, so an empty SUPERSEDES means SKIP.

  The two SKIP reasons are stable strings; downstream pipelines that want
  to alert on GDS misconfiguration (but not on legitimately empty
  SUPERSEDES graphs) can match on the `GDS plugin not available` prefix.
- **Behaviour on cyclic SUPERSEDES graphs**: when the SUPERSEDES graph
  contains a cycle (i.e. CC-04 fires), CC-11 may also fire on the cycle
  members. This is a side-effect of PageRank's steady-state behaviour on
  cyclic subgraphs: cycle members accumulate identical scores via the
  feedback loop, and if the surrounding ontology contains acyclic
  constraints without `SUPERSEDES` edges, those drag the graph mean down
  enough that the cycle members' uniform ratio exceeds the threshold.
  The cycle rows reported by CC-11 are **correlated evidence**, not
  independent signal — CC-04 is the source of truth for diagnosing the
  cycle. Resolving the cycle (so that CC-04 passes) typically removes
  the spurious CC-11 hits as well. This behaviour is documented as part
  of the test contract in
  `tests/test_examples.py::test_example_verdict_matches_expectation[fintech_seeded_faults.yaml]`,
  which expects both CC-04 and CC-11 to fail on the seeded-faults
  ontology.

---

## Aggregation

The certification status is computed by `harness_auditor.report.aggregate`
as:

```
if any blocking criterion has status FAIL or ERROR → FAILED
elif any advisory criterion has status FAIL        → REQUIRES_REVIEW
else                                                → PASSED
```

`SKIP` is never counted as a failure. `WARN` is only valid for advisory
criteria and never blocks a `PASSED` verdict on its own.

**HMAC overlay**: when `AUDITOR_HMAC_KEY` is unset at audit time, the
verdict is **forced** to `REQUIRES_REVIEW` regardless of the per-criterion
outcome, and `report.sig` is omitted. The rationale: an unsigned report
cannot be trusted in a downstream verifier chain, and the auditor refuses
to certify an artifact it cannot prove it produced. This is implemented
in `build_report(..., hmac_key_present=...)`; downstream embedders that
build reports programmatically should pass `True` when their pipeline
applies a signature externally.

**HMAC scheme (v0.2.0)**: the signature is
`HMAC-SHA256(key, HMAC_DOMAIN_TAG ‖ canonical_json)`, where
`HMAC_DOMAIN_TAG = b"harness-auditor:report:v1\0"`. The domain tag
scopes the signature to this auditor and this report-format version,
preventing a signature replay onto any other artefact a holder of the
same key may sign. **Breaking change vs v0.1.0**: signatures produced by
v0.1.0 do not verify under v0.2.0; re-run the audit on the new version
to produce a v2 signature, or use the attestation bundle (Ed25519) for
cross-organisation provenance.

---

## User-defined certification criteria

The eleven CCs above are the **built-in** registry. Organisations with
domain-specific policies can extend the auditor with their own CCs
without forking the package, using the public registry-extension API:

```python
from harness_auditor import CriterionDefinition, register_criterion, Severity

register_criterion(CriterionDefinition(
    criterion_id="CC-X1",                       # any uppercase suffix, no built-in collision
    name="Critical-severity must DENY",
    query_file="ccx_critical_must_deny.cypher",
    aggregator_role="advisory",                 # or "blocking"
    severity_for=lambda rows: Severity.HIGH,
    message_for=lambda rows: f"{len(rows)} violation(s)" if rows else "ok",
    query_dir=Path(__file__).resolve().parent / "queries",
))
```

A user CC must:

- Use a `criterion_id` that matches `^CC-[A-Z0-9][A-Z0-9_-]*$` and does
  not collide with any built-in. `register_criterion` enforces both at
  registration time.
- Express its check in terms of the graph schema documented in
  `docs/GRAPH_MODEL.md`. New relationship types or labels require a
  minor-version bump of the contract; see GRAPH_MODEL.md §Versioning.
- Honour the same `expected_pass = empty result set` convention (rows
  → FAIL, no rows → PASS). The runner has no other return-shape support.

A complete worked example lives under
[`examples/custom_cc/`](../examples/custom_cc/) (CC-X1 "Critical-severity
must DENY"). The library-side API is documented in
[`INTEGRATION.md`](INTEGRATION.md) §6.
