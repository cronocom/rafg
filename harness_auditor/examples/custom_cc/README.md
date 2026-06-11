# Custom certification criteria · Worked example

This directory shows how to extend the auditor with domain-specific
certification criteria without forking the package. The reference policy
shipped here is **CC-X1 · Critical-severity must DENY**: a constraint
tagged `severity: critical` whose `decision_if_violated` is anything other
than `DENY` is flagged for review.

## Files

| Path | Purpose |
|---|---|
| `queries/ccx_critical_must_deny.cypher` | The CC's single-statement Cypher query. |
| `register.py` | Builds the `CriterionDefinition`, calls `register_criterion`, re-exports the CLI. |

## Running

The custom CC is wired into the runner the moment its `CriterionDefinition`
is registered. Two ways to fire it:

### A. Through the script's CLI

```bash
python -m examples.custom_cc.register audit \
  --ontology examples/fintech_seeded_faults.yaml
```

The script imports the package, registers `CC-X1`, then hands control to
the standard Typer app. The output now shows 12 rows: the built-in 11 plus
`CC-X1`. (The seeded-faults file's
`high_amount_emergency_rule` is `severity: critical` + `decision: DENY`, so
CC-X1 passes on that fixture — the negative case lives in the unit test
under `tests/test_examples.py::test_custom_cc_extends_registry`.)

### B. From your own Python code

```python
import examples.custom_cc.register  # side-effect: CC-X1 registered

from harness_auditor import load, run_all
# ... open a session, load(), run_all() — CC-X1 appears in the result list.
```

`register_criterion` is process-wide. Re-importing the module is idempotent.

## What `query_dir` does

The custom CC's `.cypher` lives outside the package
(`examples/custom_cc/queries/`). The `CriterionDefinition` sets

```python
query_dir=Path(__file__).resolve().parent / "queries"
```

so the runner resolves `ccx_critical_must_deny.cypher` from there even when
the user does not pass `--queries-dir`. Built-in CCs leave `query_dir=None`
and fall back to the directory passed to `run_all` (the bundled set by
default).

## Constraints on the `criterion_id`

* Must match the regex `^CC-[A-Z0-9_-]+$` (validated by the
  `CriterionResult` schema's `criterion_id: str = Field(pattern=...)`).
* Must not collide with a built-in CC id (`CC-01` … `CC-11`). Use a prefix
  like `CC-X1`, `CC-FOO`, `CC-INTERNAL_3` for custom ones.

`register_criterion` validates both at registration time and raises
`ValueError` with the offending id, so a typo or accidental collision
surfaces immediately, not at audit time.
