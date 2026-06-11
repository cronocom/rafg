// ============================================================================
// CC-06 · Coverage Map  (pure Cypher · single statement)
// ============================================================================
//
// Per-verb regulatory coverage. For each verb that declares one or more
// `MUST_SATISFY` regulations, compute:
//
//     coverage = (#declared regulations with ≥1 enforcing constraint on this verb)
//                / (#declared regulations)
//
// A verb whose coverage falls below the configured threshold is reported,
// along with the regulation codes it failed to cover so the operator can
// write the missing constraint or remove the spurious MUST_SATISFY edge.
//
// Verbs with zero declared MUST_SATISFY are not reported here; they belong
// to CC-01 (Verb Groundedness) instead.
//
// Mechanism : pure Cypher aggregate with OPTIONAL MATCH.
// Severity  : MEDIUM. Advisory.
// Threshold : `$coverage_threshold` (parameter from the runner; the CLI
//             reads CC06_COVERAGE_THRESHOLD env var, default 0.85 — the
//             canonical RAGF v2.4 dictionary default). `coalesce(...)`
//             falls back to 0.85 when the parameter is missing so the
//             query stays runnable from the Neo4j Browser without setup.
//             The threshold the query actually applied is returned in
//             every output row so the runner's message can show it.
//
// ----------------------------------------------------------------------------
// Expected output
// ----------------------------------------------------------------------------
//
// Clean ontology (every verb covered):
//     []                              -- status = PASS
//
// `transfer_funds` declares 3 regulations, only 2 of which have a referencing
// constraint:
//     [
//       { verb: "transfer_funds",
//         declared_count: 3,
//         matched_count: 2,
//         coverage: 0.6666...,
//         uncovered: ["BANK_INTERNAL_POLICY_01"],
//         threshold: 0.85 }
//     ]
// ============================================================================

MATCH (v:Verb)-[:MUST_SATISFY]->(r:Regulation)
OPTIONAL MATCH (v)<-[:HAS_CONSTRAINT_OF]-(c:Constraint)-[:REFERENCES]->(r)
WITH v, r, count(c) > 0 AS is_covered
WITH v,
     count(r) AS declared_count,
     count(CASE WHEN is_covered THEN 1 END) AS matched_count,
     collect(CASE WHEN NOT is_covered THEN r.code END) AS uncovered_raw
WITH v,
     declared_count,
     matched_count,
     [code IN uncovered_raw WHERE code IS NOT NULL] AS uncovered,
     toFloat(matched_count) / toFloat(declared_count) AS coverage,
     coalesce($coverage_threshold, 0.85) AS threshold
WHERE coverage < threshold
RETURN v.name        AS verb,
       declared_count,
       matched_count,
       coverage,
       uncovered,
       threshold
ORDER BY coverage, v.name;
