"""Unit tests for the runner's ``skip_if`` hooks.

These tests exercise the hooks in isolation by stubbing ``neo4j.Session``,
so they do NOT require a live Neo4j sandbox and run on every invocation
of the test suite. The integration paths against a real Neo4j are covered
by ``tests/test_examples.py``.

The hooks under test:

  * ``_cc07_skip``   — SKIPs when no ``ConstraintPrev`` label is present.
  * ``_cc10_skip``   — SKIPs when no ``TaxonomyEntry`` label is present.
  * ``_cc11_skip``   — SKIPs when no ``SUPERSEDES`` relationship exists or
                       when the GDS plugin is absent.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

from neo4j.exceptions import Neo4jError

from harness_auditor.runner import _cc07_skip, _cc10_skip, _cc11_skip


def _stub_session(handlers: dict[str, Callable[[dict[str, Any]], Any]]) -> MagicMock:
    """Return a MagicMock Session whose ``run`` dispatches by substring.

    Each entry in ``handlers`` maps a substring of the Cypher query to a
    callable that returns the desired Record (or raises Neo4jError). The
    first matching key wins; an unmatched query raises AssertionError so
    test drift is caught immediately.
    """
    session = MagicMock()

    def fake_run(query: str, **params: Any) -> Any:
        for needle, handler in handlers.items():
            if needle in query:
                return handler(params)
        raise AssertionError(f"unexpected query in test stub: {query!r}")

    session.run.side_effect = fake_run
    return session


def _present(record: dict[str, Any]) -> MagicMock:
    result = MagicMock()
    result.single.return_value = record
    return result


def _absent() -> MagicMock:
    """Return a Record-shaped object reporting a zero count."""
    return _present({"n": 0})


# ---------------------------------------------------------------------------
# CC-07
# ---------------------------------------------------------------------------


def test_cc07_skips_when_constraint_prev_label_absent() -> None:
    session = _stub_session({
        "db.labels()": lambda p: _absent(),
    })
    should_skip, reason = _cc07_skip(session)
    assert should_skip
    assert "previous ontology" in reason
    assert "--previous" in reason


def test_cc07_runs_when_constraint_prev_label_present() -> None:
    session = _stub_session({
        "db.labels()": lambda p: _present({"n": 1}),
    })
    should_skip, reason = _cc07_skip(session)
    assert not should_skip
    assert reason == ""


# ---------------------------------------------------------------------------
# CC-10
# ---------------------------------------------------------------------------


def test_cc10_skips_when_taxonomy_label_absent() -> None:
    session = _stub_session({
        "db.labels()": lambda p: _absent(),
    })
    should_skip, reason = _cc10_skip(session)
    assert should_skip
    assert "taxonomy" in reason
    assert "--taxonomy" in reason


def test_cc10_runs_when_taxonomy_label_present() -> None:
    session = _stub_session({
        "db.labels()": lambda p: _present({"n": 1}),
    })
    should_skip, reason = _cc10_skip(session)
    assert not should_skip
    assert reason == ""


# ---------------------------------------------------------------------------
# CC-11 (the multi-precondition one — both SUPERSEDES and GDS)
# ---------------------------------------------------------------------------


def test_cc11_skips_when_no_supersedes() -> None:
    """GDS present, but no SUPERSEDES edges → SKIP on the second precondition."""
    session = _stub_session({
        "gds.version()": lambda p: _present({"v": "2.13.4"}),
        "db.relationshipTypes()": lambda p: _absent(),
    })
    should_skip, reason = _cc11_skip(session)
    assert should_skip
    assert "SUPERSEDES" in reason


def test_cc11_skips_when_gds_missing_short_circuits_first() -> None:
    """GDS missing → SKIP immediately, the SUPERSEDES probe is never reached.

    Order matters: pre-A6 the runner stubbed all queries blindly. Now the
    GDS probe is the first gate so the SUPERSEDES stub MUST not be hit;
    if it were, the dispatcher's no-match path would AssertionError and
    expose the order regression.
    """
    def gds_missing(_params: dict[str, Any]) -> Any:
        raise Neo4jError(
            "Unknown function 'gds.version'",
            "Neo.ClientError.Statement.SyntaxError",
        )

    session = _stub_session({
        "gds.version()": gds_missing,
        # No db.relationshipTypes() entry on purpose: reaching it is a bug.
    })
    should_skip, reason = _cc11_skip(session)
    assert should_skip
    assert "GDS plugin not available" in reason


def test_cc11_runs_when_supersedes_present_and_gds_loaded() -> None:
    session = _stub_session({
        "gds.version()": lambda p: _present({"v": "2.13.4"}),
        "db.relationshipTypes()": lambda p: _present({"n": 5}),
    })
    should_skip, reason = _cc11_skip(session)
    assert not should_skip
    assert reason == ""
