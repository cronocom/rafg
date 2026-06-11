// ============================================================================
// CC-11 · Constraint Centrality  (Cypher + Graph Data Science)
// ============================================================================
//
// Identifies "base" constraints in the SUPERSEDES subgraph: constraints
// that are overridden by many other constraints and therefore act as the
// foundational layer of the governance harness. Editing or removing a
// central constraint cascades silently across every supersessor that
// resolves to it. CC-11 surfaces those constraints so they can be marked
// for elevated human review before any future edit.
//
// Conceptually: in the graph `(supersessor)-[:SUPERSEDES]->(base)`, a base
// constraint accumulates incoming SUPERSEDES edges from each of its
// supersessors. Classic PageRank in the NATURAL orientation already
// rewards nodes with many incoming edges, so we do NOT reverse the
// orientation here — a constraint with high PageRank IS a base.
//
// Severity        : HIGH advisory. The criterion does not block releases
//                   (a legitimately dense SUPERSEDES tree is normal in
//                   mature fintech ontologies) but emits REQUIRES_REVIEW
//                   so a human inspects the central constraints. Domains
//                   with stricter risk appetite can override the
//                   aggregator role to "blocking" in their fork.
// Mechanism       : GDS PageRank (gds.pageRank.stream) over a named
//                   projection of the SUPERSEDES subgraph. Three
//                   statements: drop-if-exists (idempotent), project,
//                   then PageRank + threshold filter.
// Pre-req         : Neo4j 5.x with the graph-data-science plugin loaded
//                   (handled by docker-compose.yml).
//
// ----------------------------------------------------------------------------
// Skip conditions
// ----------------------------------------------------------------------------
// The runner's `skip_if` hook (see `runner.py::_cc11_skip`) evaluates two
// preconditions in this order:
//
//   1. **GDS plugin loaded** — probed via `gds.version()`. On a community
//      Neo4j image without the plugin the call raises Neo4jError; CC-11
//      SKIPs with the reason "GDS plugin not available — CC-11 requires
//      gds.pageRank.stream". Other CCs run unaffected.
//
//   2. **At least one SUPERSEDES edge** — probed via
//      `db.relationshipTypes()`. GDS cannot project an empty relationship
//      type, so a zero-SUPERSEDES ontology SKIPs with reason "no
//      SUPERSEDES edges in the graph — CC-11 not applicable".
//
// ----------------------------------------------------------------------------
// Threshold (with hysteresis)
// ----------------------------------------------------------------------------
// A constraint is reported when:
//
//     score > ($threshold_ratio + $cc11_hysteresis) * mean_score
//
// where:
//
//   * `$threshold_ratio`   — read from the CLI from the CC11_THRESHOLD_RATIO
//                            env var. Default `1.3` (strict but realistic
//                            for fintech ontologies). Must be > 1.0.
//   * `$cc11_hysteresis`   — small margin to stabilise the verdict across
//                            runs. PageRank converges iteratively and
//                            tolerance noise can flip a borderline
//                            constraint between PASS and FAIL between
//                            two consecutive audits of the same input;
//                            the margin keeps the verdict reproducible.
//                            Default `0.05` (= 5 percentage points on top
//                            of the ratio). Bake-into-default rather than
//                            an env var so the released contract has a
//                            single source of truth.
//
// **Effective threshold** with defaults: `(1.3 + 0.05) * mean = 1.35 *
// mean`. A user setting `CC11_THRESHOLD_RATIO=1.5` raises the effective
// threshold to `1.55 * mean`. The README and `docs/CRITERIA.md` say the
// same numbers in the same form. Whenever this query, the README, or
// CRITERIA.md changes the constant, the other two must be updated in the
// same commit; the `make notebook-test` target catches drift between the
// query and the demo, but does not catch drift between the prose
// documentation and the formula here.
//
// `coalesce(..., 0.05)` falls back to the default hysteresis when the
// parameter is missing, so the query stays runnable from the Neo4j
// Browser without setup.
//
// ----------------------------------------------------------------------------
// Why no cleanup statement
// ----------------------------------------------------------------------------
// The runner captures evidence rows ONLY from the LAST statement of a
// query. A post-analysis cleanup `gds.graph.drop` as statement #4 would
// discard the rows we need. Instead, statement #1 is itself a conditional
// drop — every CC-11 invocation begins by dropping any leftover
// projection, so the projection lifetime is bounded by the next CC-11 run
// (or by `make down`, which discards the entire sandbox).
//
// ----------------------------------------------------------------------------
// Behaviour on cyclic SUPERSEDES graphs
// ----------------------------------------------------------------------------
// When the SUPERSEDES graph contains a cycle (CC-04 fires), CC-11 may
// also fire on the cycle members. This is a side-effect of PageRank's
// steady-state behaviour on cyclic subgraphs: cycle members accumulate
// identical scores via the feedback loop, and if the surrounding
// ontology contains acyclic constraints without SUPERSEDES edges, those
// drag the graph mean down enough that the cycle members' uniform ratio
// exceeds the threshold. The cycle rows reported by CC-11 are
// correlated evidence with CC-04, not independent signal: CC-04 is the
// source of truth for diagnosis. Resolving CC-04 (breaking the cycle)
// typically removes the spurious CC-11 hits as well.
//
// ----------------------------------------------------------------------------
// Expected output
// ----------------------------------------------------------------------------
//
// Ontology with no SUPERSEDES (e.g. examples/fintech_minimal.yaml):
//     SKIPped by the runner before this query ever executes.
//
// Ontology with a 3-cycle plus 4 acyclic constraints
// (examples/fintech_seeded_faults.yaml):
//     [
//       { constraint: "high_amount_emergency_rule",
//         regulation: "PSD2_ART97_SCA",
//         constraint_severity: "critical",
//         centrality_score: ~0.143,
//         graph_mean_score: ~0.0735,
//         ratio_to_mean: ~1.94 },
//       { constraint: "pep_overrides_threshold",
//         regulation: "AMLD_ART18_EDD",
//         constraint_severity: "high",
//         centrality_score: ~0.143,
//         graph_mean_score: ~0.0735,
//         ratio_to_mean: ~1.94 },
//       { constraint: "threshold_baseline_rule",
//         regulation: "PSD2_ART97_SCA",
//         constraint_severity: "medium",
//         centrality_score: ~0.143,
//         graph_mean_score: ~0.0735,
//         ratio_to_mean: ~1.94 }
//     ]
//     -- Status = FAIL (advisory), severity = HIGH.
//     -- All three cycle members tie at ratio ~1.94x due to PageRank's
//     -- steady-state symmetry across the cycle. The 4 acyclic
//     -- constraints have no incoming SUPERSEDES (~0.0214 each), which
//     -- pulls the graph mean down; the cycle members' 1.94x exceeds
//     -- the default effective threshold (1.30 + 0.05 = 1.35).
//
// Concentrated fixture (tests/fixtures/fintech_centrality_concentrated.yaml,
// four constraints all SUPERSEDE `base_rule`):
//     [
//       { constraint: "base_rule",
//         regulation: "REG_BASIC",
//         constraint_severity: "high",
//         centrality_score: ~0.132,
//         graph_mean_score: ~0.0504,
//         ratio_to_mean: ~2.62 }
//     ]
//     -- Status = FAIL (advisory), severity = HIGH.
//     -- Pure base-constraint signal: no cycles, one node legitimately
//     -- central. Canonical positive case for CC-11.
// ============================================================================

// ---- Statement 1: drop any leftover projection (idempotent) ----
CALL gds.graph.exists('cc11_supersedes') YIELD exists
WITH exists WHERE exists
CALL gds.graph.drop('cc11_supersedes', false) YIELD graphName
RETURN graphName AS dropped;

// ---- Statement 2: project the SUPERSEDES subgraph ----
CALL gds.graph.project(
  'cc11_supersedes',
  'Constraint',
  { SUPERSEDES: { orientation: 'NATURAL' } }
) YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;

// ---- Statement 3: PageRank, compute mean, filter by threshold + hysteresis ----
CALL gds.pageRank.stream('cc11_supersedes', {
  maxIterations: 20,
  dampingFactor: 0.85
})
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS c, score
WITH collect({c: c, score: score}) AS all_rows
WITH all_rows,
     CASE
       WHEN size(all_rows) > 0
       THEN reduce(s = 0.0, r IN all_rows | s + r.score) / size(all_rows)
       ELSE 0.0
     END AS mean_score
UNWIND all_rows AS row
// Effective threshold = ($threshold_ratio + $cc11_hysteresis) * mean.
// See the "Threshold (with hysteresis)" comment block above for why
// the hysteresis is applied here and how it interacts with the
// documented defaults.
WITH row.c AS c, row.score AS score, mean_score,
     coalesce($cc11_hysteresis, 0.05) AS hysteresis
WHERE mean_score > 0
  AND score > ($threshold_ratio + hysteresis) * mean_score
RETURN c.name             AS constraint,
       c.regulation        AS regulation,
       c.severity          AS constraint_severity,
       score               AS centrality_score,
       mean_score          AS graph_mean_score,
       score / mean_score  AS ratio_to_mean
ORDER BY centrality_score DESC, c.name;
