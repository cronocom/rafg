# RAGF Ontology Auditor

> **Certifica la jaula, antes de meter al pájaro.**
>
> Pre-execution certification of governance harnesses, expressed as Cypher queries over Neo4j.

The RAGF Ontology Auditor takes a candidate governance ontology (YAML), loads it into
an ephemeral Neo4j 5.26 sandbox, and evaluates it against a battery of certification
criteria. Each criterion is a Cypher query that returns structured evidence. The
auditor emits a signed report
(`PASSED` / `REQUIRES_REVIEW` / `FAILED`) suitable for inclusion in a regulatory
or academic audit trail.

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
| **CC-06** Coverage map | advisory | Cypher (aggregate) | Per-verb regulatory coverage below 0.85 |
| **CC-07** Drift delta | blocking | Cypher (diff) | Constraints removed vs. previous version — requires `--previous` |
| **CC-08** Authority gradient | blocking | Cypher | `min_amm_level` non-monotonic with verb `risk_level` |
| **CC-09** Fail-closed defaults | blocking | Cypher | Any `decision_if_violated = ALLOW` — runtime gate against post-schema drift |
| **CC-10** Hallucinated verbs | blocking | Cypher | Verbs outside the registered taxonomy — requires `--taxonomy` |
| **CC-11** Constraint centrality | advisory | Cypher + GDS PageRank | Base constraints whose edit cascades over many supersessors |

All eleven ship in v0.1.0. CC-07, CC-10 and CC-11 SKIP automatically when their
optional input or graph precondition is absent. See [`docs/CRITERIA.md`](docs/CRITERIA.md)
for the per-criterion contract and [`docs/GRAPH_MODEL.md`](docs/GRAPH_MODEL.md)
for the graph schema each query relies on.

CC-11 is the only criterion that uses the Graph Data Science plugin
(`gds.pageRank.stream`); see
[`docs/decisions/ADR-001-gds-scope.md`](docs/decisions/ADR-001-gds-scope.md)
for the scoping rationale.

---

## Quickstart

```bash
# 1. Bring up the ephemeral Neo4j 5.26 sandbox (loads GDS for CC-11)
make up

# 2. (optional but recommended) Export a signing key for the report.
#    Without it the verdict is forced to REQUIRES_REVIEW even when every
#    criterion passes — see docs/ARCHITECTURE.md §Stage 5.
export AUDITOR_HMAC_KEY="dev-only-not-for-production"

# 3. (optional) Tighten or loosen CC-11's centrality threshold.
#    Default is 1.3x graph mean. Must be > 1.0.
#    export CC11_THRESHOLD_RATIO=1.5    # more permissive
#    export CC11_THRESHOLD_RATIO=1.2    # stricter

# 4. Audit a candidate ontology
make audit ONTOLOGY=examples/fintech_minimal.yaml          # → PASSED (CC-07/CC-10/CC-11 SKIP)

# 5. Audit the deliberately broken one
#    CC-11 also fires on the CC-04 cycle members — see docs/CRITERIA.md
#    § CC-11 (Behaviour on cyclic SUPERSEDES graphs).
make audit ONTOLOGY=examples/fintech_seeded_faults.yaml    # → FAILED (CC-01/02/03/04/05/06/08/11)

# 6. (optional) Enable CC-07 + CC-10 by providing their optional inputs
harness-audit audit \
  --ontology examples/fintech_minimal.yaml \
  --previous tests/fixtures/fintech_minimal_v0_9.yaml \
  --taxonomy tests/fixtures/fintech_taxonomy_complete.yaml

# 7. (optional) Exercise CC-11 against the centrality-concentrated fixture
harness-audit audit \
  --ontology tests/fixtures/fintech_centrality_concentrated.yaml
# → REQUIRES_REVIEW (CC-11 advisory flags `base_rule` as a central constraint)

# 8. Tear down
make down
```

Reports are written to `./reports/<ontology_sha256>/`:

- `report.json` — structured verdict with per-criterion evidence
- `report.md` — human-readable narrative
- `report.sig` — HMAC-SHA256 signature (reuses the audit chain pattern)

---

## Project layout

```
harness_auditor/
├── docker-compose.yml          # Neo4j 5.26 Community + Graph Data Science plugin
├── pyproject.toml              # Python package metadata
├── Makefile                    # up / down / audit / test / lint / install
├── src/harness_auditor/
│   ├── __init__.py
│   ├── cli.py                  # Typer entrypoint
│   ├── loader.py               # YAML → Cypher CREATE + sanity check
│   ├── runner.py               # Execute multi-statement CC queries
│   ├── report.py               # JSON + Markdown + HMAC sign
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
│       └── report_schema.py    # Pydantic models for the report
├── examples/
│   ├── fintech_minimal.yaml         # Clean ontology — should PASS
│   └── fintech_seeded_faults.yaml   # Deliberately broken — should FAIL
├── docs/
│   ├── CRITERIA.md             # Full specification of the 11 CCs
│   ├── ARCHITECTURE.md         # End-to-end data flow
│   ├── GRAPH_MODEL.md          # Authoritative graph schema (labels, edges, uniqueness)
│   └── decisions/
│       └── ADR-001-gds-scope.md  # Why GDS is scoped to CC-11 only
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── tiny_ontology.yaml
    │   ├── fintech_minimal_v0_9.yaml             # for CC-07
    │   ├── fintech_taxonomy_complete.yaml        # for CC-10 (PASS path)
    │   ├── fintech_taxonomy_partial.yaml         # for CC-10 (FAIL path)
    │   └── fintech_centrality_concentrated.yaml  # for CC-11
    ├── test_schemas.py            # schema-level regression (no Neo4j)
    ├── test_report.py             # aggregation + render (no Neo4j)
    └── test_examples.py           # full pipeline; auto-skipped if Neo4j down
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
| `CC11_THRESHOLD_RATIO` | `1.3` | Centrality threshold for CC-11. A constraint is reported when its PageRank score exceeds this multiple of the graph's mean score. Must be `> 1.0` |

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
