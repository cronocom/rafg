"""
Runner · execute certification criteria against the loaded Neo4j graph.

For each registered criterion the runner reads its ``.cypher`` file, splits
it on top-level semicolons (stripping ``//`` and ``/* */`` comments),
executes the statements in order against the provided ``neo4j.Session``,
measures wall-clock latency, and packages the rows from the **last**
statement as ``evidence_rows`` in a ``CriterionResult``.

Multi-statement queries are required by criteria backed by Graph Data
Science: a GDS-based CC typically needs three statements -- drop the named
projection if it exists, project the relevant subgraph, run the algorithm
and emit rows. Single-statement queries (every CC that is pure Cypher) are
trivially handled as the degenerate "last statement = only statement" case.

Per-criterion severity is computed from the evidence rows themselves: a
CC-01 failure on a high-AMM verb is more severe than on a low-AMM one,
and so on. The escalation logic lives next to the criterion definition so
the ``.cypher`` files themselves stay declarative and reusable from the
Neo4j Browser.

Status mapping:

  - rows == []                        -> PASS
  - rows non-empty                    -> FAIL
  - Neo4jError raised during run      -> ERROR (aggregator treats as FAIL)
  - definition.skip_if(session) true  -> SKIP (precondition graph not loaded)

The ``skip_if`` hook is used by criteria that need optional inputs:

  - CC-07 needs a previous-version load (any ``ConstraintPrev`` node).
  - CC-10 needs a taxonomy load (any ``TaxonomyEntry`` node).
  - CC-11 needs at least one ``SUPERSEDES`` edge (Graph Data Science
    cannot project a relationship type that has no instances).

When the upstream caller does not provide them the relevant subgraph is
missing and the criterion SKIPs cleanly instead of producing a misleading
PASS or ERROR. All three hooks consult ``db.labels()`` /
``db.relationshipTypes()`` rather than running a ``MATCH`` against the
unknown label/type, so they do not emit the UnknownLabelWarning that
Neo4j attaches to patterns referencing a never-instantiated label.

Query parameters (such as the CC-11 threshold ratio) are propagated
through ``run_all(session, queries_dir, query_params=...)``. Neo4j silently
ignores parameters not referenced by a given query, so the same dict is
passed to every criterion without filtering.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from neo4j import Session
from neo4j.exceptions import Neo4jError

from harness_auditor.schemas.report_schema import (
    CriterionResult,
    CriterionStatus,
    Severity,
)

AggregatorRole = Literal["blocking", "advisory"]


@dataclass(frozen=True)
class CriterionDefinition:
    criterion_id: str
    name: str
    query_file: str
    aggregator_role: AggregatorRole
    severity_for: Callable[[list[dict[str, Any]]], Severity]
    message_for: Callable[[list[dict[str, Any]]], str]
    skip_if: Callable[[Session], tuple[bool, str]] | None = None


# ---------------------------------------------------------------------------
# Per-criterion severity + message logic
# ---------------------------------------------------------------------------


def _cc01_severity(rows: list[dict[str, Any]]) -> Severity:
    if any(int(r.get("min_amm_level") or 0) >= 3 for r in rows):
        return Severity.CRITICAL
    return Severity.HIGH


def _cc01_message(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "all verbs are anchored to at least one regulation"
    verbs = ", ".join(str(r["verb"]) for r in rows)
    return f"{len(rows)} verb(s) without MUST_SATISFY edge: {verbs}"


def _cc02_severity(rows: list[dict[str, Any]]) -> Severity:
    for r in rows:
        if r.get("severity") == "critical" and r.get("decision_if_violated") == "DENY":
            return Severity.CRITICAL
    return Severity.HIGH


def _cc02_message(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "every constraint references a field present in its verb payload"
    items = ", ".join(
        f"{r['constraint']}({r['verb']}.{r['parameter']})" for r in rows
    )
    return f"{len(rows)} unreachable constraint(s): {items}"


def _cc03_severity(_rows: list[dict[str, Any]]) -> Severity:
    return Severity.MEDIUM


def _cc03_message(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "every non-informational regulation is referenced by at least one constraint"
    codes = ", ".join(str(r["regulation"]) for r in rows)
    return f"{len(rows)} orphan regulation(s): {codes}"


def _cc04_severity(_rows: list[dict[str, Any]]) -> Severity:
    return Severity.CRITICAL


def _cc04_message(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "SUPERSEDES graph is acyclic"
    parts: list[str] = []
    for r in rows:
        members = list(r.get("members") or [])
        if len(members) == 1:
            parts.append(f"self-supersedes: {members[0]}")
        else:
            parts.append("cycle: " + " -> ".join(members))
    return f"{len(rows)} cycle(s) detected -- " + "; ".join(parts)


def _cc05_severity(_rows: list[dict[str, Any]]) -> Severity:
    return Severity.HIGH


def _cc05_message(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "no precedence collisions on any verb"
    items = ", ".join(
        f"{r['verb']}@precedence={r['precedence_level']}"
        f" ({int(r['collision_size'])} constraints)"
        for r in rows
    )
    return f"{len(rows)} precedence collision(s): {items}"


def _cc06_severity(_rows: list[dict[str, Any]]) -> Severity:
    return Severity.MEDIUM


def _cc06_message(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "every verb meets the 0.85 regulatory coverage threshold"
    items = ", ".join(
        f"{r['verb']} ({int(r['matched_count'])}/{int(r['declared_count'])} "
        f"= {float(r['coverage']):.2f})"
        for r in rows
    )
    return f"{len(rows)} verb(s) below coverage threshold: {items}"


def _cc07_severity(rows: list[dict[str, Any]]) -> Severity:
    if any(r.get("prev_decision") == "DENY" for r in rows):
        return Severity.CRITICAL
    return Severity.HIGH


def _cc07_message(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "no constraint dropped relative to the previous version"
    items = ", ".join(
        f"{r['removed_constraint']} (was {r['prev_decision']}/{r['prev_severity']})"
        for r in rows
    )
    return f"{len(rows)} constraint(s) removed since previous version: {items}"


def _cc07_skip(session: Session) -> tuple[bool, str]:
    # `db.labels()` reports labels currently in use; checking it via a
    # procedure call avoids the UnknownLabelWarning Neo4j emits when a
    # query references a never-instantiated label directly.
    if not _label_present(session, "ConstraintPrev"):
        return True, "no previous ontology loaded -- pass --previous to enable CC-07"
    return False, ""


def _cc08_severity(rows: list[dict[str, Any]]) -> Severity:
    if any(r.get("risk_level") == "critical" for r in rows):
        return Severity.CRITICAL
    return Severity.HIGH


def _cc08_message(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "every verb's min_amm_level is monotonic with its risk_level"
    items = ", ".join(
        f"{r['verb']} (risk={r['risk_level']}, "
        f"amm={int(r['min_amm_level'])} < {int(r['required_min_amm'])})"
        for r in rows
    )
    return f"{len(rows)} authority-gradient violation(s): {items}"


def _cc09_severity(_rows: list[dict[str, Any]]) -> Severity:
    return Severity.CRITICAL


def _cc09_message(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "no constraint has decision_if_violated = ALLOW"
    items = ", ".join(f"{r['constraint']}({r['verb']})" for r in rows)
    return f"{len(rows)} ALLOW constraint(s) -- post-schema drift: {items}"


def _cc10_severity(_rows: list[dict[str, Any]]) -> Severity:
    return Severity.CRITICAL


def _cc10_message(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "every verb is registered in the taxonomy"
    items = ", ".join(str(r["verb"]) for r in rows)
    return f"{len(rows)} hallucinated verb(s) (not in taxonomy): {items}"


def _cc10_skip(session: Session) -> tuple[bool, str]:
    if not _label_present(session, "TaxonomyEntry"):
        return True, "no taxonomy loaded -- pass --taxonomy to enable CC-10"
    return False, ""


def _cc11_severity(_rows: list[dict[str, Any]]) -> Severity:
    # Advisory severity HIGH: constraint centrality is a fragility signal,
    # not a structural bug. We want the verdict to flag REQUIRES_REVIEW so
    # a human inspects the central constraints before any future edit, but
    # we explicitly do NOT block releases on this -- a legitimately dense
    # SUPERSEDES tree (common in mature fintech ontologies) would otherwise
    # produce permanent FAILED status without any actionable defect.
    return Severity.HIGH


def _cc11_message(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "no constraint exceeds the centrality threshold"
    items = ", ".join(
        f"{r['constraint']} ({float(r['ratio_to_mean']):.2f}x mean)"
        for r in rows[:5]
    )
    suffix = f" (+{len(rows) - 5} more)" if len(rows) > 5 else ""
    return f"{len(rows)} central constraint(s): {items}{suffix}"


def _cc11_skip(session: Session) -> tuple[bool, str]:
    # GDS cannot project a relationship type that has zero instances --
    # `gds.graph.project` raises with the relevant message. Pre-check via
    # `db.relationshipTypes()` so an ontology with no SUPERSEDES (the most
    # common case for small fintech ontologies) SKIPs cleanly rather than
    # ERRORs, and without triggering an UnknownRelationshipTypeWarning.
    #
    # Note: when SUPERSEDES exists but the graph is cyclic, CC-11 does NOT
    # skip -- it fires alongside CC-04 as documented in CRITERIA.md
    # § CC-11 (Behaviour on cyclic SUPERSEDES graphs).
    if not _relationship_type_present(session, "SUPERSEDES"):
        return True, "no SUPERSEDES edges in the graph -- CC-11 not applicable"
    return False, ""


def _label_present(session: Session, label: str) -> bool:
    """True iff at least one node currently in the graph carries ``label``.

    Uses the ``db.labels()`` procedure to avoid the UnknownLabelWarning
    Neo4j emits when a Cypher query references a label that has never been
    instantiated in the running database.
    """
    rec = session.run(
        "CALL db.labels() YIELD label AS l "
        "WITH l WHERE l = $label "
        "RETURN count(l) AS n",
        label=label,
    ).single()
    return bool(rec and rec["n"] > 0)


def _relationship_type_present(session: Session, rel_type: str) -> bool:
    """True iff at least one relationship of ``rel_type`` exists in the graph."""
    rec = session.run(
        "CALL db.relationshipTypes() YIELD relationshipType AS rt "
        "WITH rt WHERE rt = $rel_type "
        "RETURN count(rt) AS n",
        rel_type=rel_type,
    ).single()
    return bool(rec and rec["n"] > 0)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


REGISTRY: tuple[CriterionDefinition, ...] = (
    CriterionDefinition(
        "CC-01", "Verb groundedness",
        "cc01_verb_groundedness.cypher",
        "blocking", _cc01_severity, _cc01_message,
    ),
    CriterionDefinition(
        "CC-02", "Constraint reachability",
        "cc02_constraint_reachability.cypher",
        "blocking", _cc02_severity, _cc02_message,
    ),
    CriterionDefinition(
        "CC-03", "Orphan regulations",
        "cc03_orphan_regulations.cypher",
        "advisory", _cc03_severity, _cc03_message,
    ),
    CriterionDefinition(
        "CC-04", "SUPERSEDES cycles",
        "cc04_supersedes_cycles.cypher",
        "blocking", _cc04_severity, _cc04_message,
    ),
    CriterionDefinition(
        "CC-05", "Precedence collision",
        "cc05_precedence_collision.cypher",
        "blocking", _cc05_severity, _cc05_message,
    ),
    CriterionDefinition(
        "CC-06", "Coverage map",
        "cc06_coverage_map.cypher",
        "advisory", _cc06_severity, _cc06_message,
    ),
    CriterionDefinition(
        "CC-07", "Drift delta",
        "cc07_drift_delta.cypher",
        "blocking", _cc07_severity, _cc07_message,
        skip_if=_cc07_skip,
    ),
    CriterionDefinition(
        "CC-08", "Authority gradient",
        "cc08_authority_gradient.cypher",
        "blocking", _cc08_severity, _cc08_message,
    ),
    CriterionDefinition(
        "CC-09", "Fail-closed defaults",
        "cc09_fail_closed_defaults.cypher",
        "blocking", _cc09_severity, _cc09_message,
    ),
    CriterionDefinition(
        "CC-10", "Hallucinated verbs",
        "cc10_hallucinated_verbs.cypher",
        "blocking", _cc10_severity, _cc10_message,
        skip_if=_cc10_skip,
    ),
    CriterionDefinition(
        "CC-11", "Constraint centrality",
        "cc11_constraint_centrality.cypher",
        "advisory", _cc11_severity, _cc11_message,
        skip_if=_cc11_skip,
    ),
)

#: Public lookup used by ``report.aggregate`` to classify failures.
AGGREGATOR_ROLE: dict[str, AggregatorRole] = {
    d.criterion_id: d.aggregator_role for d in REGISTRY
}


def packaged_queries_dir() -> Path:
    """Return the queries directory bundled with the installed package."""
    return Path(__file__).resolve().parent / "queries"


# ---------------------------------------------------------------------------
# Cypher splitting
# ---------------------------------------------------------------------------

#: Match ``/* ... */`` block comments (multiline).
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _split_cypher_statements(text: str) -> list[str]:
    """Split Cypher text on top-level semicolons, dropping comments.

    This is a deliberately simple splitter aimed at the ``.cypher`` files
    bundled with the auditor. It removes ``//`` line comments and
    ``/* ... */`` block comments, then splits the remaining text on ``;``.

    Caveats:

      * Does not handle ``;`` inside string literals. None of the bundled
        queries contain such literals; if a future query needs one, switch
        to a proper tokeniser or pre-split the file by hand.
      * Empty statements (whitespace-only after splitting) are dropped.
    """
    cleaned = _BLOCK_COMMENT_RE.sub("", text)
    no_line_comments: list[str] = []
    for line in cleaned.splitlines():
        idx = line.find("//")
        if idx != -1:
            line = line[:idx]
        no_line_comments.append(line)
    joined = "\n".join(no_line_comments)
    parts = [p.strip() for p in joined.split(";")]
    return [p for p in parts if p]


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def run_all(
    session: Session,
    queries_dir: Path,
    registry: Sequence[CriterionDefinition] = REGISTRY,
    query_params: dict[str, Any] | None = None,
) -> list[CriterionResult]:
    """Execute every registered criterion against ``session`` in declaration order.

    ``query_params`` is a global parameter dict applied to every Cypher
    statement; Neo4j silently ignores parameters not referenced by a query,
    so this keeps the runner uniform without per-criterion plumbing.
    """
    params = query_params or {}
    return [_run_one(session, queries_dir, d, params) for d in registry]


def _run_one(
    session: Session,
    queries_dir: Path,
    definition: CriterionDefinition,
    query_params: dict[str, Any],
) -> CriterionResult:
    if definition.skip_if is not None:
        should_skip, reason = definition.skip_if(session)
        if should_skip:
            return CriterionResult(
                criterion_id=definition.criterion_id,
                name=definition.name,
                status=CriterionStatus.SKIP,
                severity=Severity.LOW,
                evidence_query="",
                evidence_rows=[],
                latency_ms=0.0,
                message=reason,
            )

    query_path = queries_dir / definition.query_file
    query_text = query_path.read_text(encoding="utf-8")
    statements = _split_cypher_statements(query_text)
    if not statements:
        return CriterionResult(
            criterion_id=definition.criterion_id,
            name=definition.name,
            status=CriterionStatus.ERROR,
            severity=Severity.HIGH,
            evidence_query=query_text,
            evidence_rows=[],
            latency_ms=0.0,
            message="query file contains no executable statements",
            error="empty query file",
        )

    start = time.perf_counter()
    try:
        # Setup statements (drop projection, project, etc.) -- evidence is
        # always taken from the LAST statement only.
        for setup_stmt in statements[:-1]:
            session.run(setup_stmt, **query_params)
        result = session.run(statements[-1], **query_params)
        rows: list[dict[str, Any]] = [record.data() for record in result]
    except Neo4jError as e:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return CriterionResult(
            criterion_id=definition.criterion_id,
            name=definition.name,
            status=CriterionStatus.ERROR,
            severity=Severity.HIGH,
            evidence_query=query_text,
            evidence_rows=[],
            latency_ms=latency_ms,
            message=f"query execution failed: {e!s}",
            error=str(e),
        )
    latency_ms = (time.perf_counter() - start) * 1000.0

    status = CriterionStatus.PASS if not rows else CriterionStatus.FAIL
    return CriterionResult(
        criterion_id=definition.criterion_id,
        name=definition.name,
        status=status,
        severity=definition.severity_for(rows),
        evidence_query=query_text,
        evidence_rows=rows,
        latency_ms=latency_ms,
        message=definition.message_for(rows),
    )
