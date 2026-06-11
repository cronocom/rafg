"""
Example-ontology regression — end-to-end pipeline against a live Neo4j sandbox.

Each bundled example is paired with the documented expectation from
``examples/README.md``. The test parametrises over those expectations and
asserts that the full pipeline (loader → runner → aggregator) returns the
right verdict and trips the right per-CC failures.

Additional focused tests exercise the four criteria that cannot be expressed
purely at the YAML layer:

  * **CC-07** (Drift Delta) — requires a previous-version ontology projected
    with ``load_previous``.
  * **CC-09** (Fail-Closed Defaults) — Pydantic rejects ``ALLOW`` at YAML
    load, so the only way to trip CC-09 is to inject the drifted constraint
    via direct Cypher after the loader has run. This is the realistic
    threat model documented in ``docs/CRITERIA.md``.
  * **CC-10** (Hallucinated Verbs) — requires a verb taxonomy projected
    with ``load_taxonomy``.
  * **CC-11** (Constraint Centrality) — requires a graph with at least one
    SUPERSEDES edge to be applicable; uses the concentrated fixture for a
    positive-result test.

All tests in this file are marked ``requires_neo4j`` and skipped
automatically when the sandbox is not reachable.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml
from neo4j import Driver, GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

from harness_auditor.loader import load, load_previous, load_taxonomy
from harness_auditor.report import build_report
from harness_auditor.runner import run_all
from harness_auditor.schemas.ontology_schema import Ontology, Taxonomy
from harness_auditor.schemas.report_schema import (
    CertificationStatus,
    CriterionResult,
    CriterionStatus,
)

_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687")
_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "auditor_local_only")
_SHA = "0" * 64
#: Query parameter dict that mirrors what the production CLI passes to
#: ``run_all``. Updated whenever a new ``$param`` lands in a CC's Cypher
#: so the integration suite stays a single source of truth for the bundle
#: of values every audit needs to run cleanly.
_CC11_DEFAULT_PARAMS = {
    "threshold_ratio": 1.3,
    "coverage_threshold": 0.85,
    "cc11_hysteresis": 0.05,
}


@dataclass(frozen=True)
class ExampleSpec:
    filename: str
    expected_verdict: CertificationStatus
    expected_failed_criteria: frozenset[str] = field(default_factory=frozenset)


EXAMPLES: tuple[ExampleSpec, ...] = (
    ExampleSpec(
        filename="fintech_minimal.yaml",
        expected_verdict=CertificationStatus.PASSED,
    ),
    ExampleSpec(
        filename="fintech_seeded_faults.yaml",
        expected_verdict=CertificationStatus.FAILED,
        # CC-01/02/03/04/05/06/08 are tripped by their dedicated faults.
        # CC-11 (Constraint Centrality) also fires as a *consequence* of
        # the CC-04 SUPERSEDES cycle: the three cyclic constraints
        # accumulate identical PageRank scores (~1.93x the graph mean),
        # all above the default 1.3x threshold. Removing CC-11 would
        # require restructuring the cycle fixture; the cleaner contract
        # is to expect it.
        # CC-07/09/10 are exercised by the dedicated tests below.
        expected_failed_criteria=frozenset({
            "CC-01", "CC-02", "CC-03", "CC-04", "CC-05", "CC-06", "CC-08",
            "CC-11",
        }),
    ),
)


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


def _load_taxonomy(path: Path) -> Taxonomy:
    return Taxonomy.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _wipe_and_load(session, ontology: Ontology) -> None:
    session.run("MATCH (n) DETACH DELETE n")
    load(session, ontology)


def _by_id(results: list[CriterionResult]) -> dict[str, CriterionResult]:
    return {c.criterion_id: c for c in results}


# ---------------------------------------------------------------------------
# Verdict regression — fintech_minimal & fintech_seeded_faults
# ---------------------------------------------------------------------------


@pytest.mark.requires_neo4j
@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: e.filename)
def test_example_verdict_matches_expectation(
    example: ExampleSpec,
    neo4j_driver: Driver,
    examples_dir: Path,
    queries_dir: Path,
) -> None:
    ontology = _load_ontology(examples_dir / example.filename)

    with neo4j_driver.session() as session:
        _wipe_and_load(session, ontology)
        results = run_all(session, queries_dir, query_params=_CC11_DEFAULT_PARAMS)

    report = build_report(
        ontology_sha256=_SHA,
        domain=ontology.domain.name,
        domain_version=ontology.domain.version,
        criteria=results,
        hmac_key_present=True,
    )

    assert report.certification_status == example.expected_verdict, (
        f"{example.filename}: expected {example.expected_verdict.value}, "
        f"got {report.certification_status.value}; "
        f"criteria={[(c.criterion_id, c.status.value, c.message) for c in results]}"
    )

    actual_failed = frozenset(
        c.criterion_id
        for c in results
        if c.status in (CriterionStatus.FAIL, CriterionStatus.ERROR)
    )
    assert actual_failed == example.expected_failed_criteria, (
        f"{example.filename}: expected failed {set(example.expected_failed_criteria)}, "
        f"got {set(actual_failed)}"
    )


@pytest.mark.requires_neo4j
def test_seeded_faults_cycle_members_are_complete(
    neo4j_driver: Driver,
    examples_dir: Path,
    queries_dir: Path,
) -> None:
    """CC-04's evidence MUST include the canonical 3-member SUPERSEDES cycle."""
    ontology = _load_ontology(examples_dir / "fintech_seeded_faults.yaml")
    with neo4j_driver.session() as session:
        _wipe_and_load(session, ontology)
        results = run_all(session, queries_dir, query_params=_CC11_DEFAULT_PARAMS)

    cc04 = _by_id(results)["CC-04"]
    expected_members = {
        "pep_overrides_threshold",
        "threshold_baseline_rule",
        "high_amount_emergency_rule",
    }
    assert any(
        set(row["members"]) == expected_members for row in cc04.evidence_rows
    ), cc04.evidence_rows


@pytest.mark.requires_neo4j
def test_optional_criteria_skip_without_inputs(
    neo4j_driver: Driver,
    examples_dir: Path,
    queries_dir: Path,
) -> None:
    """CC-07, CC-10 and CC-11 SKIP cleanly when their preconditions are absent.

    fintech_minimal has no previous-version load, no taxonomy load, and
    contains no SUPERSEDES edges — so all three optional CCs must SKIP.
    """
    ontology = _load_ontology(examples_dir / "fintech_minimal.yaml")
    with neo4j_driver.session() as session:
        _wipe_and_load(session, ontology)
        results = run_all(session, queries_dir, query_params=_CC11_DEFAULT_PARAMS)

    by_id = _by_id(results)
    assert by_id["CC-07"].status == CriterionStatus.SKIP
    assert by_id["CC-10"].status == CriterionStatus.SKIP
    assert by_id["CC-11"].status == CriterionStatus.SKIP


# ---------------------------------------------------------------------------
# CC-07 · Drift Delta
# ---------------------------------------------------------------------------


@pytest.mark.requires_neo4j
def test_cc07_reports_removed_constraint(
    neo4j_driver: Driver,
    examples_dir: Path,
    fixtures_dir: Path,
    queries_dir: Path,
) -> None:
    current = _load_ontology(examples_dir / "fintech_minimal.yaml")
    previous = _load_ontology(fixtures_dir / "fintech_minimal_v0_9.yaml")
    with neo4j_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        load(session, current)
        load_previous(session, previous)
        results = run_all(session, queries_dir, query_params=_CC11_DEFAULT_PARAMS)

    cc07 = _by_id(results)["CC-07"]
    assert cc07.status == CriterionStatus.FAIL, cc07.message
    removed = {row["removed_constraint"] for row in cc07.evidence_rows}
    assert removed == {"legacy_high_amount_deny"}, removed
    # The dropped constraint was DENY → severity escalates to CRITICAL.
    assert cc07.severity.value == "critical", cc07.severity


@pytest.mark.requires_neo4j
def test_cc07_passes_when_constraints_identical(
    neo4j_driver: Driver,
    examples_dir: Path,
    queries_dir: Path,
) -> None:
    ontology = _load_ontology(examples_dir / "fintech_minimal.yaml")
    with neo4j_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        load(session, ontology)
        # Project the same ontology again as "previous" — every constraint
        # exists in both, so no drift.
        load_previous(session, ontology)
        results = run_all(session, queries_dir, query_params=_CC11_DEFAULT_PARAMS)

    cc07 = _by_id(results)["CC-07"]
    assert cc07.status == CriterionStatus.PASS, cc07.message


# ---------------------------------------------------------------------------
# CC-09 · Fail-Closed Defaults (drift via direct Cypher)
# ---------------------------------------------------------------------------


@pytest.mark.requires_neo4j
def test_cc09_catches_post_load_allow_drift(
    neo4j_driver: Driver,
    examples_dir: Path,
    queries_dir: Path,
) -> None:
    """CC-09's reason for existing: drift that bypasses the Pydantic schema."""
    ontology = _load_ontology(examples_dir / "fintech_minimal.yaml")
    with neo4j_driver.session() as session:
        _wipe_and_load(session, ontology)
        # Direct write — the operational threat model: a CI job that writes
        # straight to Bolt without going through Loader/Pydantic.
        session.run(
            """
            MATCH (v:Verb {name: 'transfer_funds'})
            MATCH (r:Regulation {code: 'PSD2_ART97_SCA'})
            CREATE (drift:Constraint {
                name: 'rogue_allow_constraint',
                type: 'threshold',
                decision_if_violated: 'ALLOW',
                regulation: 'PSD2_ART97_SCA',
                reason: 'drift via direct cypher',
                severity: 'low',
                precedence_level: 1
            })
            CREATE (drift)-[:HAS_CONSTRAINT_OF]->(v)
            CREATE (drift)-[:REFERENCES]->(r)
            """
        )
        results = run_all(session, queries_dir, query_params=_CC11_DEFAULT_PARAMS)

    cc09 = _by_id(results)["CC-09"]
    assert cc09.status == CriterionStatus.FAIL, cc09.message
    drifted = {row["constraint"] for row in cc09.evidence_rows}
    assert "rogue_allow_constraint" in drifted, drifted
    assert cc09.severity.value == "critical"


# ---------------------------------------------------------------------------
# CC-10 · Hallucinated Verbs
# ---------------------------------------------------------------------------


@pytest.mark.requires_neo4j
def test_cc10_passes_with_complete_taxonomy(
    neo4j_driver: Driver,
    examples_dir: Path,
    fixtures_dir: Path,
    queries_dir: Path,
) -> None:
    ontology = _load_ontology(examples_dir / "fintech_minimal.yaml")
    taxonomy = _load_taxonomy(fixtures_dir / "fintech_taxonomy_complete.yaml")
    with neo4j_driver.session() as session:
        _wipe_and_load(session, ontology)
        load_taxonomy(session, taxonomy)
        results = run_all(session, queries_dir, query_params=_CC11_DEFAULT_PARAMS)

    cc10 = _by_id(results)["CC-10"]
    assert cc10.status == CriterionStatus.PASS, cc10.message


@pytest.mark.requires_neo4j
def test_cc10_reports_verb_missing_from_taxonomy(
    neo4j_driver: Driver,
    examples_dir: Path,
    fixtures_dir: Path,
    queries_dir: Path,
) -> None:
    ontology = _load_ontology(examples_dir / "fintech_minimal.yaml")
    taxonomy = _load_taxonomy(fixtures_dir / "fintech_taxonomy_partial.yaml")
    with neo4j_driver.session() as session:
        _wipe_and_load(session, ontology)
        load_taxonomy(session, taxonomy)
        results = run_all(session, queries_dir, query_params=_CC11_DEFAULT_PARAMS)

    cc10 = _by_id(results)["CC-10"]
    assert cc10.status == CriterionStatus.FAIL, cc10.message
    hallucinated = {row["verb"] for row in cc10.evidence_rows}
    assert hallucinated == {"verify_identity"}, hallucinated
    assert cc10.severity.value == "critical"


# ---------------------------------------------------------------------------
# CC-11 · Constraint Centrality
# ---------------------------------------------------------------------------


@pytest.mark.requires_neo4j
def test_cc11_reports_central_constraint(
    neo4j_driver: Driver,
    fixtures_dir: Path,
    queries_dir: Path,
) -> None:
    """Concentrated fixture: `base_rule` dominates PageRank → CC-11 FAIL."""
    ontology = _load_ontology(fixtures_dir / "fintech_centrality_concentrated.yaml")
    with neo4j_driver.session() as session:
        _wipe_and_load(session, ontology)
        results = run_all(session, queries_dir, query_params=_CC11_DEFAULT_PARAMS)

    cc11 = _by_id(results)["CC-11"]
    assert cc11.status == CriterionStatus.FAIL, cc11.message
    central = {row["constraint"] for row in cc11.evidence_rows}
    assert "base_rule" in central, central
    base_row = next(r for r in cc11.evidence_rows if r["constraint"] == "base_rule")
    # The concentrated fixture produces ratio ~2.6x the mean — verify the
    # threshold filter actually fires above 1.3x (the default).
    assert float(base_row["ratio_to_mean"]) > 1.3
    assert cc11.severity.value == "high"


@pytest.mark.requires_neo4j
def test_cc11_advisory_does_not_block_passed(
    neo4j_driver: Driver,
    fixtures_dir: Path,
    queries_dir: Path,
) -> None:
    """A CC-11 failure alone produces REQUIRES_REVIEW, not FAILED.

    The concentrated fixture is constructed so every blocking criterion
    PASSes; only CC-11 (advisory) flags. The verdict must therefore be
    REQUIRES_REVIEW, demonstrating that advisory criteria do not block
    releases on their own.
    """
    ontology = _load_ontology(fixtures_dir / "fintech_centrality_concentrated.yaml")
    with neo4j_driver.session() as session:
        _wipe_and_load(session, ontology)
        results = run_all(session, queries_dir, query_params=_CC11_DEFAULT_PARAMS)

    by_id = _by_id(results)
    # All blocking CCs must PASS for this contract to hold. If a blocking
    # CC fails, the fixture has drifted and needs to be fixed before this
    # assertion makes sense.
    for cid, c in by_id.items():
        if cid == "CC-11":
            continue
        if c.status in (CriterionStatus.SKIP, CriterionStatus.PASS):
            continue
        pytest.fail(
            f"fixture drifted — blocking {cid} failed: {c.status.value} "
            f"({c.message})"
        )

    report = build_report(
        ontology_sha256=_SHA,
        domain=ontology.domain.name,
        domain_version=ontology.domain.version,
        criteria=results,
        hmac_key_present=True,
    )
    assert report.certification_status == CertificationStatus.REQUIRES_REVIEW, (
        f"verdict={report.certification_status.value}; "
        f"CC-11 status={by_id['CC-11'].status.value}"
    )


@pytest.mark.requires_neo4j
def test_cc11_skips_when_no_supersedes(
    neo4j_driver: Driver,
    examples_dir: Path,
    queries_dir: Path,
) -> None:
    """An ontology without SUPERSEDES edges SKIPs CC-11 cleanly."""
    ontology = _load_ontology(examples_dir / "fintech_minimal.yaml")
    with neo4j_driver.session() as session:
        _wipe_and_load(session, ontology)
        results = run_all(session, queries_dir, query_params=_CC11_DEFAULT_PARAMS)

    cc11 = _by_id(results)["CC-11"]
    assert cc11.status == CriterionStatus.SKIP, cc11.message
    assert "no SUPERSEDES edges" in cc11.message
