// ============================================================================
// CC-X1 · Critical-severity constraints must resolve to DENY  (custom · advisory)
// ============================================================================
//
// Custom organisational policy: any constraint marked ``severity: critical``
// must carry ``decision_if_violated: DENY``. A critical-severity rule that
// resolves to ESCALATE asks a human to make the call on what is, by
// definition, a critical-class violation — that defeats the point of marking
// the severity. The auditor treats this as advisory: it surfaces the
// drift so a human reviewer can decide whether the severity tag or the
// decision needs to change.
//
// This file is the canonical worked example of a user-registered CC. It
// lives outside the package (``examples/custom_cc/queries/``) and is wired
// into the runner via ``register_criterion`` in
// ``examples/custom_cc/register.py``.
//
// Mechanism : pure Cypher pattern match.
// Severity  : HIGH.
// Role      : advisory.
//
// ----------------------------------------------------------------------------
// Expected output
// ----------------------------------------------------------------------------
//
// Clean ontology (every critical constraint is DENY):
//     []                              -- status = PASS
//
// Ontology with a `severity: critical` + `decision_if_violated: ESCALATE`:
//     [
//       { constraint: "high_amount_emergency_rule",
//         verb:       "approve_internal_transfer",
//         decision:   "ESCALATE" }
//     ]
// ============================================================================

MATCH (c:Constraint)-[:HAS_CONSTRAINT_OF]->(v:Verb)
WHERE c.severity = 'critical'
  AND c.decision_if_violated <> 'DENY'
RETURN c.name                  AS constraint,
       v.name                  AS verb,
       c.decision_if_violated  AS decision
ORDER BY c.name;
