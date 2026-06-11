# Examples

Two ontologies ship with the auditor for self-validation and demos:

| File | Expected verdict | Purpose |
|---|---|---|
| `fintech_minimal.yaml` | `PASSED` | Reference clean ontology — passes all applicable CCs |
| `fintech_seeded_faults.yaml` | `FAILED` | Deliberate defects that trip eight of the eleven CCs |

`fintech_minimal.yaml` is intentionally narrow: it does not exercise CC-07
(needs `--previous`), CC-10 (needs `--taxonomy`), or CC-11 (needs at least
one `SUPERSEDES` edge), so those CCs SKIP cleanly. The remaining eight
shipped CCs all PASS, producing verdict `PASSED`.

`fintech_seeded_faults.yaml` is the canonical regression fixture. Its
header comment documents each planted defect. The current fixture trips
eight CCs at once:

- CC-01 (a verb with no `MUST_SATISFY`)
- CC-02 (a constraint with a `parameter` not in its verb's payload schema)
- CC-03 (an orphan regulation)
- CC-04 (a three-cycle in `SUPERSEDES`)
- CC-05 (two constraints sharing `(verb, precedence_level)`)
- CC-06 (a verb below the configured coverage threshold; default `0.85`,
  configurable via `CC06_COVERAGE_THRESHOLD`)
- CC-08 (a verb with `risk_level: critical` and `min_amm_level` too low)
- CC-11 (fires as a side-effect of the CC-04 cycle — see `docs/CRITERIA.md`
  § CC-11 *Behaviour on cyclic SUPERSEDES graphs*)

CC-07 SKIPs (no `--previous`) and CC-10 SKIPs (no `--taxonomy`). CC-09
PASSes because the Pydantic schema rejects `ALLOW` at YAML load time, so
the fixture cannot express that defect at this layer.

Any time a new CC is added to the auditor this fixture should be extended
with a fault that trips it, and the per-CC expectation in
`tests/test_examples.py::EXAMPLES` (specifically the
`expected_failed_criteria` set for the seeded-faults `ExampleSpec`)
updated accordingly. A regression that lets the seeded-faults file pass
is a release blocker.

## Running them locally

```bash
make up
make audit ONTOLOGY=examples/fintech_minimal.yaml         # verdict PASSED
make audit ONTOLOGY=examples/fintech_seeded_faults.yaml   # verdict FAILED
make down
```

## Adding a new example

1. Place the YAML under `examples/`.
2. Document in this README which CC(s) it is meant to exercise and the
   expected verdict.
3. Add an `ExampleSpec` entry to `tests/test_examples.py::EXAMPLES` that
   asserts the verdict and the failing-CC set match.
