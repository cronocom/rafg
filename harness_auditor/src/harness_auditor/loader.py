"""
Loader · YAML ontology → Neo4j graph.

Translates a validated ``Ontology`` into batched UNWIND CREATE statements,
executes them against an open ``neo4j.Session``, and runs a sanity check on
the resulting node and relationship counts. Fail-closed: any mismatch raises
``LoaderMismatchError`` and the auditor aborts before any criterion runs.

Two parallel projection modes are supported:

  - ``load(session, ontology)`` — projects the current ontology with the
    canonical labels (``Domain``, ``Verb``, ``Constraint``, ...). Reads by
    every shipped CC except CC-07.
  - ``load_previous(session, ontology)`` — projects a *previous* ontology
    version with the ``Prev`` suffix on every label (``DomainPrev``,
    ``VerbPrev``, ``ConstraintPrev``, ...). Read only by CC-07 (Drift Delta).
    Schema constraints are not re-applied (current load already did).

A third helper, ``load_taxonomy``, projects the registered verb taxonomy
used by CC-10 (Hallucinated Verbs) as ``(:TaxonomyEntry)`` nodes. The
projection uses MERGE on ``(domain, verb_name)`` so repeated invocations
against the same session are idempotent (no duplicate entries).

Graph model emitted — see ``docs/GRAPH_MODEL.md`` for the authoritative
contract (versioned, with cardinality invariants and per-CC dependencies):

    (Verb)       -[:BELONGS_TO]->        (Domain)
    (Verb)       -[:MUST_SATISFY]->      (Regulation)
    (Verb)       -[:HAS_FIELD]->         (Field)
    (Constraint) -[:HAS_CONSTRAINT_OF]-> (Verb)
    (Constraint) -[:REFERENCES]->        (Regulation)
    (Constraint) -[:SUPERSEDES]->        (Constraint)
"""

from __future__ import annotations

from neo4j import Session

from harness_auditor.schemas.ontology_schema import Ontology, Taxonomy

SCHEMA_STATEMENTS: tuple[str, ...] = (
    "CREATE CONSTRAINT domain_name IF NOT EXISTS "
    "FOR (d:Domain) REQUIRE d.name IS UNIQUE",
    "CREATE CONSTRAINT regulation_code IF NOT EXISTS "
    "FOR (r:Regulation) REQUIRE r.code IS UNIQUE",
    "CREATE CONSTRAINT verb_name IF NOT EXISTS "
    "FOR (v:Verb) REQUIRE v.name IS UNIQUE",
    "CREATE CONSTRAINT constraint_name IF NOT EXISTS "
    "FOR (c:Constraint) REQUIRE c.name IS UNIQUE",
)


class LoaderMismatchError(RuntimeError):
    """Post-load node/edge counts diverge from the source ontology."""


def load(session: Session, ontology: Ontology) -> dict[str, int]:
    """Project the current ontology with the canonical labels."""
    return _load_impl(session, ontology, label_suffix="", apply_constraints=True)


def load_previous(session: Session, ontology: Ontology) -> dict[str, int]:
    """Project a previous ontology version with the ``Prev`` label suffix."""
    return _load_impl(session, ontology, label_suffix="Prev", apply_constraints=False)


def load_taxonomy(session: Session, taxonomy: Taxonomy) -> int:
    """Project the registered verb taxonomy used by CC-10. Returns entry count.

    Uses ``MERGE`` keyed on ``(domain, verb_name)`` so repeated invocations
    against the same session are idempotent. Callers that rely on uniqueness
    do not need to wipe the graph between invocations of this function.
    """
    if not taxonomy.verbs:
        return 0
    session.run(
        """
        UNWIND $verbs AS verb_name
        MERGE (:TaxonomyEntry {domain: $domain, verb_name: verb_name})
        """,
        domain=taxonomy.domain,
        verbs=list(taxonomy.verbs),
    )
    return len(taxonomy.verbs)


# ---------------------------------------------------------------------------
# Internal: label-parameterised projection
# ---------------------------------------------------------------------------


def _load_impl(
    session: Session,
    ontology: Ontology,
    *,
    label_suffix: str,
    apply_constraints: bool,
) -> dict[str, int]:
    if apply_constraints:
        _apply_schema(session)
    _create_domain(session, ontology, label_suffix)
    _create_regulations(session, ontology, label_suffix)
    _create_verbs(session, ontology, label_suffix)
    _link_must_satisfy(session, ontology, label_suffix)
    _create_fields(session, ontology, label_suffix)
    _create_constraints(session, ontology, label_suffix)
    _link_supersedes(session, ontology, label_suffix)
    return _sanity_check(session, ontology, label_suffix)


def _apply_schema(session: Session) -> None:
    for stmt in SCHEMA_STATEMENTS:
        session.run(stmt)


def _create_domain(session: Session, ontology: Ontology, suffix: str) -> None:
    d = ontology.domain
    session.run(
        f"CREATE (:Domain{suffix} "
        f"{{name: $name, version: $version, description: $description}})",
        name=d.name,
        version=d.version,
        description=d.description,
    )


def _create_regulations(session: Session, ontology: Ontology, suffix: str) -> None:
    rows = [r.model_dump() for r in ontology.regulations]
    session.run(
        f"""
        UNWIND $rows AS row
        CREATE (:Regulation{suffix} {{
          code: row.code,
          name: row.name,
          description: row.description,
          celex: row.celex,
          informational: row.informational
        }})
        """,
        rows=rows,
    )


def _create_verbs(session: Session, ontology: Ontology, suffix: str) -> None:
    rows = [
        {
            "name": v.name,
            "description": v.description,
            "risk_level": v.risk_level.value,
            "min_amm_level": v.min_amm_level,
            "requires_human_approval": v.requires_human_approval,
        }
        for v in ontology.verbs
    ]
    session.run(
        f"""
        MATCH (d:Domain{suffix} {{name: $domain_name}})
        UNWIND $rows AS row
        CREATE (v:Verb{suffix} {{
          name: row.name,
          description: row.description,
          risk_level: row.risk_level,
          min_amm_level: row.min_amm_level,
          requires_human_approval: row.requires_human_approval
        }})
        CREATE (v)-[:BELONGS_TO]->(d)
        """,
        domain_name=ontology.domain.name,
        rows=rows,
    )


def _link_must_satisfy(session: Session, ontology: Ontology, suffix: str) -> None:
    rows = [
        {"verb": v.name, "reg_code": code}
        for v in ontology.verbs
        for code in v.must_satisfy
    ]
    if not rows:
        return
    session.run(
        f"""
        UNWIND $rows AS row
        MATCH (v:Verb{suffix} {{name: row.verb}})
        MATCH (r:Regulation{suffix} {{code: row.reg_code}})
        CREATE (v)-[:MUST_SATISFY]->(r)
        """,
        rows=rows,
    )


def _create_fields(session: Session, ontology: Ontology, suffix: str) -> None:
    rows = [
        {
            "verb": v.name,
            "name": f.name,
            "type": f.type.value,
            "description": f.description,
            "required": f.required,
        }
        for v in ontology.verbs
        for f in v.payload_schema
    ]
    if not rows:
        return
    session.run(
        f"""
        UNWIND $rows AS row
        MATCH (v:Verb{suffix} {{name: row.verb}})
        CREATE (f:Field{suffix} {{
          name: row.name,
          type: row.type,
          description: row.description,
          required: row.required
        }})
        CREATE (v)-[:HAS_FIELD]->(f)
        """,
        rows=rows,
    )


def _create_constraints(session: Session, ontology: Ontology, suffix: str) -> None:
    rows = [
        {
            "name": c.name,
            "type": c.type.value,
            "verb": c.verb,
            "decision_if_violated": c.decision_if_violated.value,
            "regulation": c.regulation,
            "reason": c.reason,
            "severity": c.severity.value,
            "precedence_level": c.precedence_level,
            "parameter": c.parameter,
            "operator": c.operator.value if c.operator else None,
            "value": c.value,
            "condition_field": c.condition_field,
            "condition_value": c.condition_value,
        }
        for c in ontology.constraints
    ]
    if not rows:
        return
    session.run(
        f"""
        UNWIND $rows AS row
        MATCH (v:Verb{suffix} {{name: row.verb}})
        MATCH (r:Regulation{suffix} {{code: row.regulation}})
        CREATE (c:Constraint{suffix} {{
          name: row.name,
          type: row.type,
          decision_if_violated: row.decision_if_violated,
          regulation: row.regulation,
          reason: row.reason,
          severity: row.severity,
          precedence_level: row.precedence_level,
          parameter: row.parameter,
          operator: row.operator,
          value: row.value,
          condition_field: row.condition_field,
          condition_value: row.condition_value
        }})
        CREATE (c)-[:HAS_CONSTRAINT_OF]->(v)
        CREATE (c)-[:REFERENCES]->(r)
        """,
        rows=rows,
    )


def _link_supersedes(session: Session, ontology: Ontology, suffix: str) -> None:
    rows = [
        {"name": c.name, "supersedes": c.supersedes}
        for c in ontology.constraints
        if c.supersedes is not None
    ]
    if not rows:
        return
    session.run(
        f"""
        UNWIND $rows AS row
        MATCH (a:Constraint{suffix} {{name: row.name}})
        MATCH (b:Constraint{suffix} {{name: row.supersedes}})
        CREATE (a)-[:SUPERSEDES]->(b)
        """,
        rows=rows,
    )


def _sanity_check(
    session: Session, ontology: Ontology, suffix: str
) -> dict[str, int]:
    expected = {
        f"Domain{suffix}": 1,
        f"Regulation{suffix}": len(ontology.regulations),
        f"Verb{suffix}": len(ontology.verbs),
        f"Field{suffix}": sum(len(v.payload_schema) for v in ontology.verbs),
        f"Constraint{suffix}": len(ontology.constraints),
        "BELONGS_TO": len(ontology.verbs),
        "MUST_SATISFY": sum(len(v.must_satisfy) for v in ontology.verbs),
        "HAS_FIELD": sum(len(v.payload_schema) for v in ontology.verbs),
        "HAS_CONSTRAINT_OF": len(ontology.constraints),
        "REFERENCES": len(ontology.constraints),
        "SUPERSEDES": sum(1 for c in ontology.constraints if c.supersedes is not None),
    }
    observed: dict[str, int] = {}
    for label in (
        f"Domain{suffix}",
        f"Regulation{suffix}",
        f"Verb{suffix}",
        f"Field{suffix}",
        f"Constraint{suffix}",
    ):
        rec = session.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()
        observed[label] = rec["c"] if rec else 0

    # Relationship counts are scoped to the suffix by the label of the
    # source endpoint, which is unambiguous for every relationship type in
    # the contract.
    rel_source = {
        "BELONGS_TO":         f"Verb{suffix}",
        "MUST_SATISFY":       f"Verb{suffix}",
        "HAS_FIELD":          f"Verb{suffix}",
        "HAS_CONSTRAINT_OF":  f"Constraint{suffix}",
        "REFERENCES":         f"Constraint{suffix}",
        "SUPERSEDES":         f"Constraint{suffix}",
    }
    for rel, source_label in rel_source.items():
        rec = session.run(
            f"MATCH (:{source_label})-[r:{rel}]->() RETURN count(r) AS c"
        ).single()
        observed[rel] = rec["c"] if rec else 0

    mismatches = {
        k: (expected[k], observed[k])
        for k in expected
        if expected[k] != observed[k]
    }
    if mismatches:
        raise LoaderMismatchError(
            "post-load counts diverge from ontology "
            f"(expected vs. observed): {mismatches}"
        )
    return observed
