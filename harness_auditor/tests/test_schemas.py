"""Schema-level regression tests for the ontology Pydantic models.

Covers two layers:

  * Positive: the bundled YAMLs (clean reference, seeded faults, tiny fixture)
    must parse and continue to carry the documented invariants.
  * Negative: a curated set of structural mutations must be rejected by the
    Pydantic models, locking in the regexes, ranges and ``extra="forbid"``
    contract of ``ontology_schema``.

The negative suite is parametrised over a base "minimum valid" ontology that
each test case mutates with a single deliberate violation. New CCs that
tighten the schema should add their counter-example here.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from harness_auditor.schemas.ontology_schema import Ontology

# ---------------------------------------------------------------------------
# Positive: bundled YAMLs
# ---------------------------------------------------------------------------


def _load(path: Path) -> Ontology:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Ontology.model_validate(data)


def test_fintech_minimal_parses(examples_dir: Path) -> None:
    ontology = _load(examples_dir / "fintech_minimal.yaml")
    assert ontology.domain.name == "fintech_minimal"
    assert ontology.domain.version == "1.0.0"
    assert len(ontology.regulations) == 2
    assert len(ontology.verbs) == 2
    assert len(ontology.constraints) == 3


def test_fintech_minimal_has_no_ungrounded_verbs(examples_dir: Path) -> None:
    """The clean reference satisfies CC-01 at the schema level."""
    ontology = _load(examples_dir / "fintech_minimal.yaml")
    assert [v.name for v in ontology.verbs if not v.must_satisfy] == []


def test_fintech_seeded_faults_parses(examples_dir: Path) -> None:
    ontology = _load(examples_dir / "fintech_seeded_faults.yaml")
    assert ontology.domain.name == "fintech_broken"


def test_fintech_seeded_faults_carries_each_documented_fault(
    examples_dir: Path,
) -> None:
    """Regression: the seeded-faults file MUST keep tripping CC-01/02/04."""
    ontology = _load(examples_dir / "fintech_seeded_faults.yaml")

    # FAULT_01 — at least one ungrounded verb (CC-01).
    assert any(not v.must_satisfy for v in ontology.verbs)

    # FAULT_02 — at least one constraint whose `parameter` is missing from
    # its verb's payload_schema (CC-02).
    fields_by_verb = {
        v.name: {f.name for f in v.payload_schema} for v in ontology.verbs
    }
    unreachable = [
        c.name
        for c in ontology.constraints
        if c.parameter
        and c.type.value in ("threshold", "conditional_threshold", "amm_level_check")
        and c.parameter not in fields_by_verb.get(c.verb, set())
    ]
    assert unreachable, "no unreachable constraints — CC-02 fault scenario broken"

    # FAULT_03 — at least one SUPERSEDES cycle (CC-04). Detected via a
    # bounded DFS in pure Python; mirrors the Cypher's reachability check.
    superseded_by = {
        c.name: c.supersedes for c in ontology.constraints if c.supersedes
    }
    assert _has_cycle(superseded_by), (
        "no SUPERSEDES cycle — CC-04 fault scenario broken"
    )


def _has_cycle(graph: dict[str, str]) -> bool:
    for start in graph:
        seen: set[str] = set()
        node: str | None = start
        depth = 0
        while node is not None and depth <= len(graph):
            if node in seen:
                return True
            seen.add(node)
            node = graph.get(node)
            depth += 1
    return False


def test_tiny_fixture_parses(fixtures_dir: Path) -> None:
    ontology = _load(fixtures_dir / "tiny_ontology.yaml")
    assert ontology.domain.name == "tiny"
    assert len(ontology.verbs) == 1
    assert len(ontology.constraints) == 1


# ---------------------------------------------------------------------------
# Negative: structural mutations the schema must reject
# ---------------------------------------------------------------------------


def _minimal_valid_ontology() -> dict[str, Any]:
    """Smallest dict that round-trips through ``Ontology.model_validate``."""
    return {
        "schema_version": "1.0",
        "domain": {"name": "demo", "version": "1.0.0"},
        "regulations": [{"code": "R1", "name": "Reg 1"}],
        "verbs": [
            {
                "name": "do_thing",
                "risk_level": "low",
                "min_amm_level": 1,
                "must_satisfy": ["R1"],
                "payload_schema": [{"name": "field_a", "type": "string"}],
            }
        ],
        "constraints": [
            {
                "name": "field_a_required",
                "type": "required_field",
                "verb": "do_thing",
                "parameter": "field_a",
                "decision_if_violated": "DENY",
                "regulation": "R1",
                "reason": "demo",
                "severity": "low",
                "precedence_level": 1,
            }
        ],
    }


def test_minimal_synthetic_ontology_validates() -> None:
    """Guard: the negative-suite base case itself must remain valid."""
    Ontology.model_validate(_minimal_valid_ontology())


Mutation = Callable[[dict[str, Any]], None]


def _set_domain_name_uppercase(d: dict[str, Any]) -> None:
    d["domain"]["name"] = "Demo"


def _set_domain_name_with_hyphen(d: dict[str, Any]) -> None:
    d["domain"]["name"] = "demo-thing"


def _set_domain_version_two_parts(d: dict[str, Any]) -> None:
    d["domain"]["version"] = "1.0"


def _set_regulation_code_lowercase(d: dict[str, Any]) -> None:
    d["regulations"][0]["code"] = "r1"
    d["verbs"][0]["must_satisfy"] = ["r1"]
    d["constraints"][0]["regulation"] = "r1"


def _set_verb_name_starts_with_digit(d: dict[str, Any]) -> None:
    d["verbs"][0]["name"] = "1do_thing"
    d["constraints"][0]["verb"] = "1do_thing"


def _set_min_amm_level_too_low(d: dict[str, Any]) -> None:
    d["verbs"][0]["min_amm_level"] = 0


def _set_min_amm_level_too_high(d: dict[str, Any]) -> None:
    d["verbs"][0]["min_amm_level"] = 6


def _set_precedence_level_negative(d: dict[str, Any]) -> None:
    d["constraints"][0]["precedence_level"] = -1


def _set_precedence_level_too_high(d: dict[str, Any]) -> None:
    d["constraints"][0]["precedence_level"] = 1001


def _set_decision_allow(d: dict[str, Any]) -> None:
    d["constraints"][0]["decision_if_violated"] = "ALLOW"


def _add_extra_top_level_field(d: dict[str, Any]) -> None:
    d["unknown_section"] = {"junk": True}


def _add_extra_verb_field(d: dict[str, Any]) -> None:
    d["verbs"][0]["weight"] = 0.5


def _set_value_mixed_list(d: dict[str, Any]) -> None:
    # B3 · constraint.value must be a homogeneous Neo4j-compatible array.
    d["constraints"][0]["operator"] = "in"
    d["constraints"][0]["value"] = [1, "two", True]


def _set_schema_version_unsupported_major(d: dict[str, Any]) -> None:
    # B5 · the auditor reads major 1.x only.
    d["schema_version"] = "2.0"


_INVALID_CASES: tuple[tuple[str, Mutation], ...] = (
    ("domain name uppercase", _set_domain_name_uppercase),
    ("domain name with hyphen", _set_domain_name_with_hyphen),
    ("domain version is two-part", _set_domain_version_two_parts),
    ("regulation code lowercase", _set_regulation_code_lowercase),
    ("verb name starts with digit", _set_verb_name_starts_with_digit),
    ("min_amm_level below range", _set_min_amm_level_too_low),
    ("min_amm_level above range", _set_min_amm_level_too_high),
    ("precedence_level negative", _set_precedence_level_negative),
    ("precedence_level above 1000", _set_precedence_level_too_high),
    ("decision_if_violated = ALLOW (CC-09 at the schema)", _set_decision_allow),
    ("extra top-level field", _add_extra_top_level_field),
    ("extra field on a verb", _add_extra_verb_field),
    ("value is a mixed-type list (B3)", _set_value_mixed_list),
    ("schema_version major != 1 (B5)", _set_schema_version_unsupported_major),
)


@pytest.mark.parametrize(
    "mutation", [m for _, m in _INVALID_CASES], ids=[label for label, _ in _INVALID_CASES]
)
def test_invariant_violations_are_rejected(mutation: Mutation) -> None:
    bad = copy.deepcopy(_minimal_valid_ontology())
    mutation(bad)
    with pytest.raises(ValidationError):
        Ontology.model_validate(bad)
