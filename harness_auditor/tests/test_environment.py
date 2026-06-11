"""Tests for the report's ``environment`` block.

Pure-Python tests guard the schema shape and the offline-derivable fields
(``auditor_version``, ``auditor_binary_sha256``, ``python_version``,
``platform``). An integration test exercises the live Neo4j probes
(``neo4j_version``, ``gds_version``) when a sandbox is reachable.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from neo4j import Driver, GraphDatabase
from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable

from harness_auditor import __version__
from harness_auditor._attestation import auditor_binary_sha256
from harness_auditor._environment import (
    platform_string,
    probe_gds_version,
    probe_neo4j_version,
    python_version,
)
from harness_auditor.loader import load
from harness_auditor.report import build_report
from harness_auditor.schemas.ontology_schema import Ontology
from harness_auditor.schemas.report_schema import (
    CriterionResult,
    CriterionStatus,
    Environment,
    Severity,
)


def _result() -> CriterionResult:
    return CriterionResult(
        criterion_id="CC-01",
        name="dummy",
        status=CriterionStatus.PASS,
        severity=Severity.LOW,
        evidence_query="// stub",
        evidence_rows=[],
        latency_ms=1.0,
        message="ok",
    )


# ---------------------------------------------------------------------------
# Pure-Python: offline-derivable fields
# ---------------------------------------------------------------------------


def test_python_version_shape() -> None:
    v = python_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", v), v


def test_platform_string_shape() -> None:
    s = platform_string()
    assert "-" in s
    system, _, machine = s.partition("-")
    assert system and machine
    assert system == system.lower()


def test_report_embeds_environment() -> None:
    report = build_report(
        ontology_sha256="0" * 64,
        domain="demo",
        domain_version="1.0.0",
        criteria=[_result()],
        hmac_key_present=True,
    )
    env = report.environment
    assert env.auditor_version == __version__
    assert env.auditor_binary_sha256 == auditor_binary_sha256()
    assert env.python_version == python_version()
    assert env.platform == platform_string()
    # Probes default to None in the unit-test path (no session was passed).
    assert env.neo4j_version is None
    assert env.gds_version is None


def test_report_propagates_provided_neo4j_and_gds_versions() -> None:
    report = build_report(
        ontology_sha256="0" * 64,
        domain="demo",
        domain_version="1.0.0",
        criteria=[_result()],
        hmac_key_present=True,
        neo4j_version="5.26.0",
        gds_version="2.13.4",
    )
    assert report.environment.neo4j_version == "5.26.0"
    assert report.environment.gds_version == "2.13.4"


def test_environment_rejects_extra_fields() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Environment.model_validate({
            "auditor_version": __version__,
            "auditor_binary_sha256": "0" * 64,
            "python_version": "3.13.1",
            "platform": "darwin-arm64",
            "neo4j_version": None,
            "gds_version": None,
            "rogue_field": "drift",
        })


def test_environment_rejects_malformed_sha256() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Environment.model_validate({
            "auditor_version": __version__,
            "auditor_binary_sha256": "not-a-hash",
            "python_version": "3.13.1",
            "platform": "darwin-arm64",
        })


# ---------------------------------------------------------------------------
# Integration: live Neo4j probes
# ---------------------------------------------------------------------------


_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687")
_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "auditor_local_only")


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


def test_probe_neo4j_version_swallows_only_procedure_not_found() -> None:
    """A blanket swallow hides transient failures behind 'GDS not installed'.

    The probe must re-raise any Neo4jError that does NOT clearly indicate
    "procedure / function absent". This guards against the security audit
    finding A6: silenced exceptions producing falsely-clean reports.
    """
    from unittest.mock import MagicMock

    # 1. Procedure-not-found is the expected absence signal → return None.
    session = MagicMock()
    err = Neo4jError("Procedure not found", "Neo.ClientError.Procedure.ProcedureNotFound")
    session.run.side_effect = err
    assert probe_neo4j_version(session) is None

    # 2. A transient connection error must propagate so the user sees it.
    session = MagicMock()
    transient = Neo4jError(
        "Transaction terminated due to connection loss",
        "Neo.TransientError.Network.CommunicationError",
    )
    session.run.side_effect = transient
    with pytest.raises(Neo4jError):
        probe_neo4j_version(session)


def test_probe_gds_version_swallows_only_unknown_function() -> None:
    from unittest.mock import MagicMock

    # 1. Unknown-function on a community image → return None.
    session = MagicMock()
    err = Neo4jError(
        "Unknown function 'gds.version'",
        "Neo.ClientError.Statement.SyntaxError",
    )
    session.run.side_effect = err
    assert probe_gds_version(session) is None

    # 2. An unrelated syntax error (a typo in our own future query) must NOT
    #    be swallowed — that path would mask real bugs.
    session = MagicMock()
    err2 = Neo4jError(
        "Variable `x` not defined",
        "Neo.ClientError.Statement.SyntaxError",
    )
    session.run.side_effect = err2
    with pytest.raises(Neo4jError):
        probe_gds_version(session)


@pytest.mark.requires_neo4j
def test_neo4j_version_probe_returns_a_version(neo4j_driver: Driver) -> None:
    with neo4j_driver.session() as session:
        v = probe_neo4j_version(session)
    assert v is not None, "expected dbms.components() to expose Neo4j Kernel"
    # Sandbox runs 5.26.x — accept any 5.x.y for forward compatibility.
    assert re.match(r"^\d+\.\d+\.\d+", v), v


@pytest.mark.requires_neo4j
def test_gds_version_probe_is_none_or_semver(neo4j_driver: Driver) -> None:
    """GDS may or may not be installed; either path must be clean."""
    with neo4j_driver.session() as session:
        v = probe_gds_version(session)
    if v is not None:
        assert re.match(r"^\d+\.\d+\.\d+", v), v


@pytest.mark.requires_neo4j
def test_report_environment_populated_end_to_end(
    neo4j_driver: Driver,
    examples_dir: Path,
) -> None:
    ontology = Ontology.model_validate(
        yaml.safe_load((examples_dir / "fintech_minimal.yaml").read_text(encoding="utf-8"))
    )
    with neo4j_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        load(session, ontology)
        neo4j_v = probe_neo4j_version(session)
        gds_v = probe_gds_version(session)

    report = build_report(
        ontology_sha256="0" * 64,
        domain=ontology.domain.name,
        domain_version=ontology.domain.version,
        criteria=[_result()],
        hmac_key_present=True,
        neo4j_version=neo4j_v,
        gds_version=gds_v,
    )
    assert report.environment.neo4j_version == neo4j_v
    assert report.environment.gds_version == gds_v
