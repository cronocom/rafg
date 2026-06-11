"""Regression tests for actionable error formatting.

These guard the human-readable diagnostic shape of the four most common
failure paths: loader mismatch, YAML parse, Pydantic validation, and
CC11_THRESHOLD_RATIO misconfiguration. We do NOT assert against literal
strings (those are documentation, not API) — we assert that each diagnostic
names the offending kind and provides a hint section, so the *intent*
("explain probable cause, suggest fix") cannot regress silently.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from harness_auditor.loader import LoaderMismatchError

# ---------------------------------------------------------------------------
# LoaderMismatchError
# ---------------------------------------------------------------------------


def test_loader_mismatch_lists_each_offending_kind() -> None:
    exc = LoaderMismatchError({
        "MUST_SATISFY": (5, 4),
        "REFERENCES": (3, 2),
    })
    text = str(exc)
    assert "MUST_SATISFY" in text
    assert "REFERENCES" in text
    assert "expected 5, observed 4" in text
    assert "expected 3, observed 2" in text


def test_loader_mismatch_includes_probable_cause_per_kind() -> None:
    exc = LoaderMismatchError({"MUST_SATISFY": (5, 4)})
    text = str(exc)
    assert "Probable cause" in text
    # The MUST_SATISFY hint explicitly names must_satisfy[] and regulations[].
    assert "must_satisfy" in text.lower()
    assert "regulations[]" in text.lower() or "regulation" in text.lower()


def test_loader_mismatch_handles_prev_subgraph() -> None:
    exc = LoaderMismatchError({"VerbPrev": (3, 2)}, label_suffix="Prev")
    text = str(exc)
    assert "Prev subgraph" in text
    # The hint should still apply (we strip the Prev suffix when looking up).
    assert "Probable cause" in text
    assert "verbs[]" in text.lower() or "verb" in text.lower()


def test_loader_mismatch_carries_structured_data() -> None:
    exc = LoaderMismatchError({"SUPERSEDES": (2, 1)})
    assert exc.mismatches == {"SUPERSEDES": (2, 1)}
    assert exc.label_suffix == ""


def test_loader_mismatch_unknown_kind_still_renders() -> None:
    """An unknown key (future CC adds a new edge) renders without the hint."""
    exc = LoaderMismatchError({"FUTURE_REL": (10, 5)})
    text = str(exc)
    assert "FUTURE_REL" in text
    # No hint for unknown kinds — but the structural diagnostic is there.
    assert "expected 10, observed 5" in text


# ---------------------------------------------------------------------------
# CLI helpers (yaml + validation + neo4j + cc11 threshold)
# ---------------------------------------------------------------------------


def test_yaml_error_message_names_file_and_hint(tmp_path: Path) -> None:
    from harness_auditor.cli import _format_yaml_error

    bad = tmp_path / "broken.yaml"
    bad.write_text("foo:\n  - bar\n  baz\n")  # invalid YAML
    try:
        yaml.safe_load(bad.read_text())
    except yaml.YAMLError as e:
        msg = _format_yaml_error(bad, e)
        assert "broken.yaml" in msg
        assert "yamllint" in msg
        # Mark info is present when the parser exposed it.
        assert "line" in msg.lower()
    else:
        pytest.fail("expected YAMLError")


def test_validation_error_lists_each_field(tmp_path: Path) -> None:
    from pydantic import ValidationError

    from harness_auditor.cli import _format_validation_error
    from harness_auditor.schemas.ontology_schema import Ontology

    bad_path = tmp_path / "bad.yaml"
    bad_path.write_text("dummy")
    try:
        Ontology.model_validate({
            "schema_version": "999.0",
            "domain": {"name": "Bad", "version": "1.0"},  # bad case AND bad version
            "regulations": [],
            "verbs": [],
            "constraints": [],
        })
    except ValidationError as e:
        msg = _format_validation_error(bad_path, e, kind="ontology")
        assert "bad.yaml" in msg
        assert "schema validation" in msg
        # Each offending field path is named.
        assert "domain.name" in msg or "domain" in msg
        # The diagnostic must point users at the schema docs.
        assert "docs/" in msg
    else:
        pytest.fail("expected ValidationError")


def test_neo4j_unreachable_hint_suggests_make_up() -> None:
    from harness_auditor.cli import _format_neo4j_unreachable

    msg = _format_neo4j_unreachable("bolt://127.0.0.1:7687", RuntimeError("conn refused"))
    assert "bolt://127.0.0.1:7687" in msg
    assert "make up" in msg
    assert "make wait" in msg


def test_neo4j_auth_hint_names_env_vars() -> None:
    from harness_auditor.cli import _format_neo4j_auth

    msg = _format_neo4j_auth("bolt://x", RuntimeError("invalid"))
    assert "NEO4J_USER" in msg
    assert "NEO4J_PASSWORD" in msg
    # Sandbox default credentials are spelt out.
    assert "auditor_local_only" in msg


def test_cc11_threshold_rejects_non_numeric(monkeypatch: pytest.MonkeyPatch) -> None:
    import contextlib

    import typer

    from harness_auditor.cli import _resolve_cc11_threshold, console

    monkeypatch.setenv("CC11_THRESHOLD_RATIO", "not_a_number")
    with pytest.raises(typer.Exit) as ei:
        _resolve_cc11_threshold()
    assert ei.value.exit_code == 2

    # Spot-check the rendered output.
    with console.capture() as cap, contextlib.suppress(typer.Exit):
        _resolve_cc11_threshold()
    text = cap.get()
    assert "not_a_number" in text
    assert re.search(r"> 1\.0", text)


def test_cc11_threshold_rejects_at_or_below_one(monkeypatch: pytest.MonkeyPatch) -> None:
    import typer

    from harness_auditor.cli import _resolve_cc11_threshold, console

    monkeypatch.setenv("CC11_THRESHOLD_RATIO", "1.0")
    with console.capture() as cap, pytest.raises(typer.Exit):
        _resolve_cc11_threshold()
    text = cap.get()
    assert "1.0" in text
    # The diagnostic should suggest a reasonable alternative value.
    assert "1.3" in text or "default" in text.lower()


def test_cc11_threshold_unset_returns_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from harness_auditor.cli import DEFAULT_CC11_THRESHOLD_RATIO, _resolve_cc11_threshold

    monkeypatch.delenv("CC11_THRESHOLD_RATIO", raising=False)
    assert _resolve_cc11_threshold() == DEFAULT_CC11_THRESHOLD_RATIO


def test_cc11_threshold_valid_value_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    from harness_auditor.cli import _resolve_cc11_threshold

    monkeypatch.setenv("CC11_THRESHOLD_RATIO", "2.5")
    assert _resolve_cc11_threshold() == 2.5
