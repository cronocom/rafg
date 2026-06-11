# Certification Criteria · Full specification

This document is the source of truth for the eleven certification criteria
(CCs) that the auditor evaluates. Each criterion is independent: it can fail
without affecting the others. The aggregate verdict is fail-closed — see
§Aggregation.

All eleven criteria are shipped as of v0.1.0. CC-07, CC-10 and CC-11 require
optional inputs or graph preconditions and SKIP automatically when those are
absent. CC-09 is also enforced statically by the Pydantic ontology schema
(`Decision` enum) and exists at runtime to catch drift introduced via direct
Cypher writes that bypass the loader.

---

## Common contract

Every criterion exposes:

| Field | Meaning |
|---|---|
| `criterion_id` | `CC-NN` (zero-padded) |
| `name` | Human-readable label |
| `mechanism` | `cypher` \| `cypher+gds` \| `cypher+diff` |
| `severity_default` | Default severity if the criterion fires |
| `severity_escalation` | Conditions that escalate severity to `critical` |
| `evidence_query` | Path to the `.cypher` file under `queries/` |
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
  constraint on this verb) / (#declared regs)`. Verbs below the hard-coded
  threshold (0.85, matching the AgentSave dictionary default) are flagged
  with their list of uncovered regulation codes.
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
- **Threshold**: `score > $threshold_ratio * mean_score`, where
  `threshold_ratio` is read by `cli.py` from the
  `CC11_THRESHOLD_RATIO` env var and propagated as a query parameter.
  Default is `1.3` — strict but realistic for fintech ontologies. Domains
  with permissive risk profiles can raise the ratio (e.g. `2.0`) to reduce
  noise; stricter domains can lower it (must be > 1.0).
- **Why advisory**: a legitimately dense `SUPERSEDES` tree is normal in
  mature fintech ontologies. Blocking releases on every dense subgraph
  would produce permanent `FAILED` status without any actionable defect.
  The advisory role produces `REQUIRES_REVIEW`, which is the correct
  signal: "a human must look at these central constraints before any
  edit". Organisations with stricter risk appetite can override the
  aggregator role to `blocking` in their fork.
- **Operational note**: requires the GDS plugin (loaded by the bundled
  `docker-compose.yml`). SKIPped automatically when the graph contains no
  `SUPERSEDES` edges (the runner's `skip_if` hook, which uses
  `db.relationshipTypes()` to avoid the UnknownRelationshipTypeWarning
  Neo4j emits when a pattern references a never-instantiated type) — GDS
  cannot project an empty relationship type.
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

The certification status is computed as:

```
if any blocking criterion has status FAIL or ERROR → FAILED
elif any advisory criterion has status FAIL        → REQUIRES_REVIEW
else                                                → PASSED
```

`SKIP` is never counted as a failure. `WARN` is only valid for advisory
criteria and never blocks a `PASSED` verdict on its own.
