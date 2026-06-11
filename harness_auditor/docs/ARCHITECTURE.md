# Architecture · End-to-end data flow

The auditor is a small, single-purpose pipeline. There are five stages, and
each one is replaceable.

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
   3.   │  Neo4j 5.26 + GDS   │   docker-compose.yml
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
        │  JSON + Markdown + HMAC-SHA256
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
concurrent audits — each audit assumes exclusive ownership of the database.

GDS is required only by CC-11 (Constraint Centrality), which uses
`gds.pageRank.stream` over the SUPERSEDES subgraph. The other ten criteria
are pure Cypher and would run on a community image without plugins; see
[`docs/decisions/ADR-001-gds-scope.md`](decisions/ADR-001-gds-scope.md) for
the scoping rationale.

## Stage 4 · Runner

The runner iterates the configured certification criteria (default: all CCs
present in `queries/`). For each one it reads the `.cypher` file, splits it
on top-level semicolons (Cypher comments stripped), executes the
statements in order against the open session, captures the rows from the
**last** statement as evidence, measures wall-clock latency, and applies
the `expected_pass` predicate to derive a status. Per-criterion timeout is
configurable (default 5 s); a timeout produces status `ERROR`, which the
aggregator treats as `FAIL`.

Criteria that require optional inputs (CC-07 needs a previous-version
load, CC-10 needs a taxonomy load, CC-11 needs at least one `SUPERSEDES`
edge) advertise a `skip_if` hook that inspects the graph before the query
runs and returns `SKIP` cleanly when the precondition is absent. The hook
is graph-based, not flag-based — it works whether the runner is invoked
through `cli.py` or directly from Python.

Query parameters (e.g. the CC-11 threshold ratio) are passed through a
single global `query_params` dict; Neo4j silently ignores parameters not
referenced by a given query, so per-criterion plumbing stays uniform.

## Stage 5 · Report

Three artifacts are written under `reports/<ontology_sha256>/`:

- `report.json` — canonical machine representation.
- `report.md`   — rendered narrative (auto-generated from the JSON).
- `report.sig`  — `HMAC-SHA256(canonical_json, AUDITOR_HMAC_KEY)`,
  hex-encoded. The key is read from the `AUDITOR_HMAC_KEY` environment
  variable. If unset, the auditor refuses to sign and emits the report with
  status `REQUIRES_REVIEW` regardless of criterion outcomes.

The signature lets a third party verify report integrity without trusting
the auditor process or the Neo4j sandbox. The pattern matches the
HMAC-chained audit ledger used elsewhere in RAGF deployments and described
in §6 of the v2.4 paper.

## Failure modes and fail-closed behaviour

| Failure | Behaviour |
|---|---|
| YAML parse error | Refuse to run. Exit code 2. |
| Pydantic validation error | Refuse to run. Exit code 2. |
| Neo4j unreachable | Refuse to run. Exit code 3. |
| GDS plugin missing (CC-11 required) | Status `ERROR` for CC-11 → `FAIL` in aggregate. |
| Per-criterion query timeout | Status `ERROR` for that criterion → `FAIL` in aggregate. |
| HMAC key missing | Report status forced to `REQUIRES_REVIEW`. |
| Any blocking criterion FAIL | Verdict `FAILED`. Exit code 1. |
| Any advisory criterion FAIL | Verdict `REQUIRES_REVIEW`. Exit code 1. |
| All criteria PASS or SKIP/WARN | Verdict `PASSED`. Exit code 0. |
