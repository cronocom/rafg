# Contributing

This is the operational guide for working on `harness-auditor`. Keep it
short, keep it honest: the conventions below exist so that your future
self (or whoever inherits this code) can read a commit history and a PR
queue without archaeology.

---

## Local setup

```bash
git clone https://github.com/cronocom/ragf
cd ragf/harness_auditor
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# Optional: pull in jupyter/pandas if you want to work on the demo notebook
# (also required by `make notebook-test`):
#   pip install -e ".[dev,notebook]"
make up                                   # start the Neo4j sandbox
export AUDITOR_HMAC_KEY="dev-only"        # otherwise the verdict is always REQUIRES_REVIEW
```

You should now be able to run:

```bash
make test                                 # full suite (84+ tests)
make lint                                 # ruff + mypy strict
make audit ONTOLOGY=examples/fintech_minimal.yaml
make notebook-test                        # headless-execute notebooks/01_quickstart.ipynb
                                          #   (needs the [notebook] extra installed)
make down                                 # tear down the sandbox
```

The Makefile defaults to `python3`. Override with `PYTHON=/path/to/python`
on every target if you need a different interpreter (e.g. venv-relative).

---

## Before opening a PR

In this order:

1. **Tests pass locally** — `make test` exits 0. Integration tests that
   need Neo4j skip cleanly when the sandbox is down; CI runs the full
   matrix.
2. **Lint passes** — `make lint` exits 0. `ruff` formatting is
   strict; `mypy --strict` for the package.
3. **Public API stays stable** — if you touched anything re-exported
   from `harness_auditor.__all__`, add a CHANGELOG entry under
   `[Unreleased]` describing the change as added / changed / deprecated /
   removed. Breaking changes require a major bump.
4. **Docs match behaviour** — new flags need a row in the README
   configuration table; new CCs need a section in `docs/CRITERIA.md` and
   an entry in `docs/GRAPH_MODEL.md` if they read a new relationship.
5. **Tests cover the change** — if you can't write a regression test
   for it, say so in the PR description.

---

## Commit messages

[Conventional Commits 1.0](https://www.conventionalcommits.org/en/v1.0.0/)
with scoped subjects. Format:

```
<type>(<scope>): <short imperative summary>

<optional body explaining the why, not the what>

<optional footer with breaking-change notes or issue refs>
```

### Types

| Type | When to use |
|---|---|
| `feat` | A new user-visible capability (CC, CLI flag, library function in `__all__`). |
| `fix` | A bug fix that changes observable behaviour. |
| `refactor` | Internal restructuring that does NOT change observable behaviour. |
| `docs` | Documentation only (README, docs/, docstrings without behaviour change). |
| `test` | Adding or fixing tests. |
| `chore` | Build, deps, CI, anything not user-facing. |
| `perf` | Performance change with a measurable improvement. |

### Scopes

Match the affected area:

| Scope | Examples |
|---|---|
| `cli` | `harness-audit audit`, `verify`, flags |
| `loader` | YAML projection, sanity check |
| `runner` | CC registry, query execution |
| `report` | aggregation, render, HMAC, environment |
| `schema` | Pydantic models |
| `cc-NN` | A specific certification criterion (e.g. `cc-07`, `cc-11`) |
| `docs` | `docs/`, `README.md` |
| `tests` | `tests/` |
| `build` | `pyproject.toml`, `Makefile`, `docker-compose.yml` |

### Examples

```
feat(cc-11): scope GDS to CC-11 and add SUPERSEDES-edge skip_if

CC-11 uses gds.pageRank.stream over the SUPERSEDES subgraph. GDS cannot
project a relationship type that has zero instances, so the runner now
inspects db.relationshipTypes() before firing CC-11 and SKIPs cleanly when
absent. The other ten CCs remain pure Cypher.

Closes #42.
```

```
fix(loader): name the offending kind in LoaderMismatchError

The previous message dumped the mismatches dict and left the user to
reverse-engineer the cause. Now each kind is paired with a probable-cause
hint pointing at the YAML section to inspect.
```

```
refactor(runner): hoist _split_cypher_statements into its own module

No behaviour change.
```

### Breaking changes

A breaking change MUST appear in the footer:

```
feat(report)!: drop top-level auditor_version (moved to environment)

BREAKING CHANGE: AuditReport no longer exposes auditor_version at the
root; read it from environment.auditor_version instead. Existing
report.json files remain valid; consumers must update their parser.
```

The `!` after the scope is the marker the changelog generator looks for.

---

## Adding a new certification criterion

The minimum useful PR for a new CC:

1. **`.cypher` file** under `src/harness_auditor/queries/`. Header
   comment must include: mechanism, severity defaults, expected pass /
   fail output. Single statement preferred; multi-statement queries
   declare so up front.
2. **Registry entry** in `runner.py` with `_ccXX_severity` and
   `_ccXX_message` helpers, and a `_ccXX_skip` if the CC has a
   precondition.
3. **Aggregator role** decision documented in the CC's section of
   `docs/CRITERIA.md` (blocking vs advisory).
4. **Graph model update** in `docs/GRAPH_MODEL.md` if the CC reads a new
   relationship type or label.
5. **Tests** in `tests/test_examples.py`: a positive case using
   `fintech_minimal.yaml` and a negative case (extend
   `fintech_seeded_faults.yaml` or add a dedicated fixture under
   `tests/fixtures/`).
6. **CHANGELOG entry** under `[Unreleased]`.

User-defined CCs (CCs that don't ship in the package) follow a different
path — see `docs/INTEGRATION.md §6` and the worked example under
`examples/custom_cc/`. Do NOT add a custom CC to the package's `REGISTRY`;
register it via `register_criterion`.

---

## Reporting bugs

Open an issue with:

* The exact command that reproduces it, including environment variables
  set.
* The full output of the failing command (the actionable-error work in
  v0.1.0 means the diagnostic should be informative enough; if it isn't,
  that's a documentation bug too).
* `harness-audit --version` (or the install hash).
* Output of `make lint` and `make test` to confirm your tree is clean.
