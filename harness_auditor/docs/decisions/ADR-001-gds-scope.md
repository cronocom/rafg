# ADR-001 · Scope of Graph Data Science in the Auditor

- **Status**: Accepted
- **Date**: 2026-06-11
- **Version**: v0.1.0
- **Supersedes**: —
- **Superseded by**: —

## Context

The RAGF Ontology Auditor evaluates a candidate governance ontology against
a battery of certification criteria. Several of those criteria require
graph algorithms that are not expressible in pure Cypher within reasonable
complexity:

- Cycle detection in `SUPERSEDES` (CC-04).
- Centrality / influence analysis in `SUPERSEDES` (CC-11).
- Potentially future criteria — Strongly Connected Components for
  redundancy detection, all-pairs shortest paths for cross-domain
  dependency analysis, blast radius simulation for change-impact analysis.

Neo4j's Graph Data Science (GDS) plugin provides production-grade
implementations of these algorithms. Pulling in GDS, however, has costs:

1. **Operational surface area.** GDS adds in-memory projections that
   coexist with the property graph and have a separate lifecycle
   (`gds.graph.project`, `gds.graph.drop`). State must be cleaned up
   between runs.
2. **Plugin dependency at deployment time.** The bundled
   `docker-compose.yml` must load `graph-data-science`, the image must be
   compatible, and the `NEO4J_dbms_security_procedures_unrestricted` /
   `_allowlist` must be set. A community Neo4j without the plugin cannot
   run any GDS-dependent CC.
3. **Conceptual leakage in `.cypher` files.** A pure-Cypher query reads as
   declarative graph algebra; a GDS query is procedure-oriented
   (`CALL gds.algo.stream(...)`) and harder to inspect in the Neo4j
   Browser without the plugin's UI.

## Decision

**GDS is loaded unconditionally by the bundled sandbox, but its use inside
the auditor is restricted to CC-11.** Specifically:

- **CC-04 (SUPERSEDES Cycles) is pure Cypher**, using a variable-length
  pattern `(:Constraint)-[:SUPERSEDES*1..50]->(:Constraint)` with
  rotational deduplication. This stays readable in the Browser, depends
  on no plugin at the query level, and is fast enough for ontologies of
  any realistic size.
- **CC-11 (Constraint Centrality) uses `gds.pageRank.stream`** over a
  named projection (`cc11_supersedes`) of the SUPERSEDES subgraph in
  `NATURAL` orientation. PageRank rewards nodes with many incoming edges,
  which is exactly the "base constraint" signal CC-11 surfaces.
- **No other CC may introduce a GDS dependency without amending this
  ADR.** If a future criterion would benefit from GDS (e.g. SCC for
  redundancy detection), it must be evaluated against the same trade-offs
  documented here.

The bundled Docker image loads GDS unconditionally rather than
conditionally because the auditor's behaviour must be deterministic
regardless of which CCs the caller enables. A sandbox that loaded GDS only
"when needed" would have variable startup time and complicate the
`make up` invariant.

## Consequences

### Pros

- **Visibility angle preserved.** The Auditor demonstrates a marquee
  Neo4j feature (GDS) on a real, domain-meaningful problem (governance
  centrality). Useful for community write-ups and conference talks.
- **CC-11 is non-trivial.** PageRank produces semantically meaningful
  ordering of constraints that Cypher would express as an awkward
  aggregation; the query reads naturally as "find the base of the
  SUPERSEDES tree".
- **Forward compatibility with M4 DORA work.** Concentration-risk
  analysis (Nth-party blast radius) is graph-algorithmic in nature.
  Keeping GDS in the auditor's dependency surface means downstream
  modules can adopt the same plugin without a step-change in
  operational complexity.

### Cons

- **Sandbox image is heavier.** The `neo4j:5.26-community` image with
  GDS adds ~150 MB and a longer `start_period` in the healthcheck (60 s
  vs. 30 s for plain community). Mitigation: `tmpfs` keeps every restart
  ephemeral, so the cold-start cost is amortised across many audits
  within a single `make up` lifecycle.
- **CC-11 has a stricter Neo4j requirement than the other ten CCs.** A
  fork of the auditor that wants to drop CC-11 must also remove the
  plugin from `docker-compose.yml` to avoid the heavier image. We
  document this in `docs/CRITERIA.md §CC-11`.
- **GDS projection lifecycle is non-obvious.** The CC-11 query uses three
  statements (drop-if-exists, project, run-and-emit) because the runner
  captures evidence only from the last statement. A reader must
  understand that idiom; we document it in the `.cypher` file itself.

### Neutral

- **CC-04 stays pure Cypher.** This decision was made deliberately when
  CC-04 was rewritten to drop its earlier GDS-based implementation; the
  query is readable, fast, and depends on no plugin. The current ADR
  does not change CC-04; it locks the position that CC-04 stays pure
  Cypher.

## Alternatives considered

### Alternative A · No GDS at all

Express CC-11 as a Cypher aggregate counting incoming `SUPERSEDES` edges
per constraint. This is a degree-centrality approximation of PageRank and
would catch the most obvious base constraints, but ignores transitive
flow: a constraint reached only through a long chain of supersessors
would have low in-degree but high PageRank. Rejected.

### Alternative B · GDS everywhere

Rewrite CC-04, CC-05 and CC-06 in GDS as well, to reduce the surface area
of "pure Cypher vs. GDS" in the codebase. Rejected because the
straightforward pure-Cypher implementations of those CCs are clearer and
faster for the ontology sizes the auditor targets (tens to hundreds of
constraints). GDS shines on large graphs; using it for small ones is
over-engineering.

### Alternative C · CC-11 as blocking

Make a CC-11 failure block releases (verdict `FAILED`) rather than
trigger `REQUIRES_REVIEW`. Rejected because a legitimately dense
SUPERSEDES tree is normal in mature fintech ontologies; blocking on every
dense subgraph would produce permanent `FAILED` status without any
actionable defect. The advisory role with `REQUIRES_REVIEW` is the
correct signal: "a human must look at these central constraints before
any edit". Organisations with stricter risk appetite may override the
aggregator role in their fork; the default ships as advisory.

## Notes for future amendments

This ADR should be revisited if any of the following becomes true:

- A future CC would gain significant analytical power from GDS that
  pure Cypher cannot match — propose an amendment naming the CC and
  the algorithm.
- The Neo4j Community 5.x image stops shipping GDS for free, or GDS
  itself moves to a paid-only license at the algorithms we use.
- The auditor is forked for a deployment context that explicitly
  cannot tolerate the GDS dependency (e.g. embedded edge deployments);
  in that case the fork should drop CC-11 and document the omission
  in its own ADR.
