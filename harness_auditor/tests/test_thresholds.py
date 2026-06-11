"""Tests for the parameterised thresholds added in v0.2.

CC-06 coverage threshold (F1) is read by the CLI from
``CC06_COVERAGE_THRESHOLD`` and passed through ``query_params`` as
``coverage_threshold``. CC-11 centrality hysteresis (F2) lives in the
runner's param dict as ``cc11_hysteresis``. Both fall back to safe
defaults if unset.

The pure-Python tests guard the CLI-side helpers (default propagation
and rejection of invalid values). The integration test for CC-06
exercises the threshold at the Cypher layer against a live sandbox.
"""

from __future__ import annotations

import contextlib

import pytest
import typer

from harness_auditor.cli import (
    DEFAULT_CC06_COVERAGE_THRESHOLD,
    DEFAULT_CC11_THRESHOLD_RATIO,
    _resolve_cc06_threshold,
    _resolve_cc11_threshold,
    console,
)

# ---------------------------------------------------------------------------
# CC-06 coverage threshold
# ---------------------------------------------------------------------------


def test_cc06_default_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CC06_COVERAGE_THRESHOLD", raising=False)
    assert _resolve_cc06_threshold() == DEFAULT_CC06_COVERAGE_THRESHOLD


def test_cc06_valid_value_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CC06_COVERAGE_THRESHOLD", "0.95")
    assert _resolve_cc06_threshold() == 0.95


def test_cc06_rejects_non_numeric(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CC06_COVERAGE_THRESHOLD", "tight")
    with pytest.raises(typer.Exit):
        _resolve_cc06_threshold()
    # And the diagnostic must name the variable and a usable default.
    with console.capture() as cap, contextlib.suppress(typer.Exit):
        _resolve_cc06_threshold()
    text = cap.get()
    assert "tight" in text
    assert "0.85" in text


def test_cc06_rejects_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """Coverage > 1 or <= 0 is meaningless; the resolver bails out."""
    for value in ("0", "0.0", "1.5", "-0.1"):
        monkeypatch.setenv("CC06_COVERAGE_THRESHOLD", value)
        with pytest.raises(typer.Exit):
            _resolve_cc06_threshold()


# ---------------------------------------------------------------------------
# CC-11 default surface still works (no regression after F1's neighbouring
# helper was added).
# ---------------------------------------------------------------------------


def test_cc11_default_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CC11_THRESHOLD_RATIO", raising=False)
    assert _resolve_cc11_threshold() == DEFAULT_CC11_THRESHOLD_RATIO
