"""Tests for the --dry-run and --strict-builtins flags (E2 + E3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_auditor import (
    CriterionDefinition,
    Severity,
    register_criterion,
    reset_user_criteria,
)
from harness_auditor.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def _isolate_user_criteria() -> None:
    """Drop any user CCs between tests so registry state stays clean."""
    reset_user_criteria()
    yield
    reset_user_criteria()


def _stage_minimal_ontology(tmp_path: Path) -> Path:
    yaml_text = """\
schema_version: '1.0'
domain:
  name: demo
  version: 1.0.0
regulations:
  - code: R1
    name: r
verbs:
  - name: do_thing
    risk_level: low
    min_amm_level: 1
    must_satisfy: [R1]
    payload_schema:
      - name: field_a
        type: string
constraints:
  - name: field_a_required
    type: required_field
    verb: do_thing
    parameter: field_a
    decision_if_violated: DENY
    regulation: R1
    reason: demo
    severity: low
    precedence_level: 1
"""
    path = tmp_path / "min.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------


def test_dry_run_exits_zero_without_touching_neo4j(
    runner: CliRunner, tmp_path: Path
) -> None:
    """--dry-run never connects to Neo4j; we point at an unreachable URI
    to prove the audit short-circuits before that step."""
    ontology = _stage_minimal_ontology(tmp_path)
    result = runner.invoke(
        app,
        [
            "audit",
            "--ontology", str(ontology),
            "--reports-dir", str(tmp_path / "reports"),
            "--neo4j-uri", "bolt://127.0.0.1:1",  # closed port; if hit, raises
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "--dry-run passed" in result.stdout
    # No verdict line should be emitted on a dry-run.
    assert "verdict" not in result.stdout.lower()


def test_dry_run_flags_missing_custom_cc_queries(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Registering a CC whose .cypher does not exist must fail dry-run."""
    ontology = _stage_minimal_ontology(tmp_path)
    register_criterion(
        CriterionDefinition(
            criterion_id="CC-MISSING1",
            name="missing",
            query_file="does_not_exist.cypher",
            aggregator_role="advisory",
            severity_for=lambda _rows: Severity.LOW,
            message_for=lambda rows: f"{len(rows)} row(s)",
            query_dir=tmp_path / "no_such_dir",
        ),
    )
    result = runner.invoke(
        app,
        [
            "audit",
            "--ontology", str(ontology),
            "--reports-dir", str(tmp_path / "reports"),
            "--neo4j-uri", "bolt://127.0.0.1:1",
            "--dry-run",
        ],
    )
    assert result.exit_code == 2, result.stdout
    assert "CC-MISSING1" in result.stdout


def test_dry_run_strict_builtins_ignores_user_cc_with_missing_query(
    runner: CliRunner, tmp_path: Path
) -> None:
    """--strict-builtins skips user CCs entirely, even broken ones."""
    ontology = _stage_minimal_ontology(tmp_path)
    register_criterion(
        CriterionDefinition(
            criterion_id="CC-MISSING2",
            name="missing",
            query_file="does_not_exist.cypher",
            aggregator_role="advisory",
            severity_for=lambda _rows: Severity.LOW,
            message_for=lambda rows: f"{len(rows)} row(s)",
            query_dir=tmp_path / "no_such_dir",
        ),
    )
    result = runner.invoke(
        app,
        [
            "audit",
            "--ontology", str(ontology),
            "--reports-dir", str(tmp_path / "reports"),
            "--neo4j-uri", "bolt://127.0.0.1:1",
            "--dry-run",
            "--strict-builtins",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "strict-builtins" in result.stdout
    assert "CC-MISSING2" not in result.stdout
