"""Worked example: register a user-defined certification criterion.

This script is the reference for adding domain-specific CCs without forking
the auditor. It does two things:

  1. Builds a ``CriterionDefinition`` for a custom policy (CC-X1) and
     registers it via ``register_criterion``. From that point on, any
     subsequent call to ``run_all`` includes CC-X1 in the iteration.

  2. Re-exposes the ``harness-audit`` Typer app, so the registered CC is
     visible when the user invokes the CLI through *this* module instead
     of the package entrypoint.

Run it like the built-in CLI:

    python -m examples.custom_cc.register audit \\
      --ontology examples/fintech_seeded_faults.yaml

Or, alternatively, just import the module from your own code before
calling ``run_all`` — the registration is process-wide and idempotent
against re-imports.

The Cypher file for this CC lives next to the script (``queries/``); the
``CriterionDefinition`` sets ``query_dir`` so the runner resolves the
file from there without the user having to pass ``--queries-dir``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_auditor import (
    CriterionDefinition,
    Severity,
    register_criterion,
)
from harness_auditor.cli import app

QUERIES_DIR = Path(__file__).resolve().parent / "queries"


def _ccx1_severity(_rows: list[dict[str, Any]]) -> Severity:
    return Severity.HIGH


def _ccx1_message(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "every critical-severity constraint resolves to DENY"
    items = ", ".join(
        f"{r['constraint']}@{r['verb']}={r['decision']}" for r in rows
    )
    return f"{len(rows)} critical constraint(s) not set to DENY: {items}"


CCX1: CriterionDefinition = CriterionDefinition(
    criterion_id="CC-X1",
    name="Critical-severity must DENY",
    query_file="ccx_critical_must_deny.cypher",
    aggregator_role="advisory",
    severity_for=_ccx1_severity,
    message_for=_ccx1_message,
    query_dir=QUERIES_DIR,
)


# Side-effect on import: register the custom CC. Wrap in try/except so that
# re-importing the module (e.g. in a test that resets state) does not error.
try:
    register_criterion(CCX1)
except ValueError:
    # Already registered (idempotent re-import).
    pass


if __name__ == "__main__":
    app()
