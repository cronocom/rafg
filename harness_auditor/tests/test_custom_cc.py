"""Tests for the extensible registry (register_criterion / unregister_criterion).

The pure-Python tests (no Neo4j) exercise validation, collision detection,
and idempotency. The integration test loads the worked example from
``examples/custom_cc/`` against a live sandbox and asserts that the
registered CC participates in ``run_all`` end-to-end.
"""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from neo4j import Driver, GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

from harness_auditor import (
    REGISTRY,
    CriterionDefinition,
    Severity,
    effective_registry,
    register_criterion,
    reset_user_criteria,
    unregister_criterion,
)
from harness_auditor.loader import load
from harness_auditor.runner import run_all
from harness_auditor.schemas.ontology_schema import Ontology

_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687")
_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "auditor_local_only")


def _dummy_severity(_rows: list[dict[str, Any]]) -> Severity:
    return Severity.MEDIUM


def _dummy_message(rows: list[dict[str, Any]]) -> str:
    return f"{len(rows)} row(s)"


def _make_definition(criterion_id: str) -> CriterionDefinition:
    return CriterionDefinition(
        criterion_id=criterion_id,
        name=f"Test {criterion_id}",
        query_file="dummy.cypher",
        aggregator_role="advisory",
        severity_for=_dummy_severity,
        message_for=_dummy_message,
    )


@pytest.fixture(autouse=True)
def _isolate_user_criteria() -> Iterator[None]:
    """Every test gets a clean user-registry; no cross-test leakage."""
    reset_user_criteria()
    yield
    reset_user_criteria()


# ---------------------------------------------------------------------------
# Pure-Python: registration semantics
# ---------------------------------------------------------------------------


def test_effective_registry_starts_at_builtin_count() -> None:
    assert effective_registry() == REGISTRY


def test_register_appends_to_effective_registry() -> None:
    extra = _make_definition("CC-TEST_1")
    register_criterion(extra)
    eff = effective_registry()
    assert eff[-1] is extra
    assert len(eff) == len(REGISTRY) + 1


def test_collision_with_builtin_is_rejected() -> None:
    with pytest.raises(ValueError, match="collides with a built-in"):
        register_criterion(_make_definition("CC-01"))


def test_double_registration_is_rejected() -> None:
    register_criterion(_make_definition("CC-TEST_DUP"))
    with pytest.raises(ValueError, match="already registered"):
        register_criterion(_make_definition("CC-TEST_DUP"))


def test_unregister_removes_user_cc() -> None:
    register_criterion(_make_definition("CC-TEST_DEL"))
    unregister_criterion("CC-TEST_DEL")
    assert "CC-TEST_DEL" not in {d.criterion_id for d in effective_registry()}


def test_unregister_builtin_is_rejected() -> None:
    with pytest.raises(ValueError, match="built-in CC"):
        unregister_criterion("CC-04")


def test_reset_user_criteria_clears_extensions() -> None:
    register_criterion(_make_definition("CC-TEST_RESET_A"))
    register_criterion(_make_definition("CC-TEST_RESET_B"))
    reset_user_criteria()
    assert effective_registry() == REGISTRY


def test_user_cc_appears_in_aggregator_role_lookup() -> None:
    from harness_auditor import AGGREGATOR_ROLE
    register_criterion(_make_definition("CC-TEST_AGG"))
    assert AGGREGATOR_ROLE["CC-TEST_AGG"] == "advisory"


# ---------------------------------------------------------------------------
# Integration: worked example end-to-end
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def neo4j_driver() -> Iterator[Driver]:
    driver = GraphDatabase.driver(_NEO4J_URI, auth=(_NEO4J_USER, _NEO4J_PASSWORD))
    try:
        driver.verify_connectivity()
    except (ServiceUnavailable, AuthError) as e:
        driver.close()
        pytest.skip(f"Neo4j sandbox unreachable at {_NEO4J_URI}: {e}")
    yield driver
    driver.close()


def _load_ontology(path: Path) -> Ontology:
    return Ontology.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@pytest.mark.requires_neo4j
def test_worked_example_ccx1_runs_against_seeded_faults(
    neo4j_driver: Driver,
    repo_root: Path,
    examples_dir: Path,
    queries_dir: Path,
) -> None:
    """Importing examples.custom_cc.register wires CC-X1 into run_all."""
    # Add the repo root to sys.path so the dotted module path is importable.
    sys.path.insert(0, str(repo_root))
    try:
        if "examples.custom_cc.register" in sys.modules:
            module = importlib.reload(sys.modules["examples.custom_cc.register"])
        else:
            module = importlib.import_module("examples.custom_cc.register")
    finally:
        sys.path.pop(0)

    ontology = _load_ontology(examples_dir / "fintech_seeded_faults.yaml")
    with neo4j_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        load(session, ontology)
        results = run_all(session, queries_dir, query_params={"threshold_ratio": 1.3})

    by_id = {c.criterion_id: c for c in results}
    assert "CC-X1" in by_id, [c.criterion_id for c in results]
    # The seeded-faults fixture has `high_amount_emergency_rule` as
    # critical + DENY, the only critical-severity constraint there, so
    # CC-X1 passes on this input.
    assert by_id["CC-X1"].status.value == "PASS", by_id["CC-X1"].message
    # Sanity: the module we imported actually exposed the spec.
    assert module.CCX1.criterion_id == "CC-X1"


@pytest.mark.requires_neo4j
def test_user_cc_fires_when_policy_violated(
    neo4j_driver: Driver,
    queries_dir: Path,
    tmp_path: Path,
) -> None:
    """Inject a critical+ESCALATE constraint and verify CC-X1 catches it.

    Uses the same `.cypher` as the worked example but builds the fixture
    in-place: load fintech_minimal, then create a rogue critical+ESCALATE
    constraint via direct Cypher (mirrors the CC-09 threat model).
    """
    # Use the worked example's query directory so the test does not need to
    # duplicate the .cypher file.
    custom_query_dir = (
        Path(__file__).resolve().parent.parent
        / "examples" / "custom_cc" / "queries"
    )
    register_criterion(
        CriterionDefinition(
            criterion_id="CC-X1",
            name="Critical-severity must DENY",
            query_file="ccx_critical_must_deny.cypher",
            aggregator_role="advisory",
            severity_for=_dummy_severity,
            message_for=_dummy_message,
            query_dir=custom_query_dir,
        )
    )

    examples_dir = Path(__file__).resolve().parent.parent / "examples"
    ontology = _load_ontology(examples_dir / "fintech_minimal.yaml")
    with neo4j_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        load(session, ontology)
        session.run(
            """
            MATCH (v:Verb {name: 'transfer_funds'})
            MATCH (r:Regulation {code: 'PSD2_ART97_SCA'})
            CREATE (drift:Constraint {
              name: 'critical_escalate_drift',
              type: 'threshold',
              decision_if_violated: 'ESCALATE',
              regulation: 'PSD2_ART97_SCA',
              reason: 'drift',
              severity: 'critical',
              precedence_level: 1
            })
            CREATE (drift)-[:HAS_CONSTRAINT_OF]->(v)
            CREATE (drift)-[:REFERENCES]->(r)
            """
        )
        results = run_all(session, queries_dir, query_params={"threshold_ratio": 1.3})

    by_id = {c.criterion_id: c for c in results}
    cc_x1 = by_id["CC-X1"]
    assert cc_x1.status.value == "FAIL", cc_x1.message
    constraints = {row["constraint"] for row in cc_x1.evidence_rows}
    assert "critical_escalate_drift" in constraints, constraints
