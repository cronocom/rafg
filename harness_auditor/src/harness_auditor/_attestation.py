"""Auditor self-attestation: SHA-256 over the package's runtime source.

The hash incorporates every file that participates in producing an audit
verdict — schemas (input validation), loader (graph projection), runner (CC
execution), report (aggregation/signing), cli (entrypoint), and the
``.cypher`` query bodies. Any change to those files alters the hash; a
report containing ``auditor_binary_sha256`` therefore lets a downstream
consumer detect post-hoc edits to the auditor itself, even if the input
ontology was identical.

Determinism rules
-----------------

* File set: every ``*.py`` and ``*.cypher`` under the package root,
  ``_attestation.py`` **included**. The previous design excluded this file
  on the rationale that "cosmetic edits to the attester should not change
  verdicts"; the audit revealed that exclusion is self-defeating — an
  attacker who modifies ``_attestation.py`` to return a fixed hash leaves
  the function looking unchanged from the outside. Including the file in
  its own hash is the only honest answer: cosmetic edits *do* change the
  attestation, and the release ritual bumps the published reference in
  ``tests/fixtures/_attestation_expected.txt`` to match.
* Excluded: ``__pycache__`` and dot-files only.
* Ordering: sorted by POSIX-style relative path.
* Line endings: normalised to ``\\n`` so the hash is identical across
  platforms.
* Encoding boundary: each file contributes ``relpath + \\0 + body + \\0``
  so renaming a file changes the hash even if its bytes are unchanged.
"""

from __future__ import annotations

import functools
import hashlib
from collections.abc import Iterator
from pathlib import Path


@functools.cache
def auditor_binary_sha256() -> str:
    """Return the 64-char hex SHA-256 of the auditor's runtime source set.

    Cached because the source set is immutable at runtime: every audit in
    the same process computes the same hash. Recomputing requires a
    process restart (which is the intended semantic — the package files
    cannot change once Python has imported them without restarting).
    """
    package_root = Path(__file__).resolve().parent
    sources = sorted(_collect_sources(package_root))
    digest = hashlib.sha256()
    for path in sources:
        rel = path.relative_to(package_root).as_posix()
        body = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(body)
        digest.update(b"\0")
    return digest.hexdigest()


def _collect_sources(root: Path) -> Iterator[Path]:
    """Yield every file the attestation hash should cover."""
    for path in root.rglob("*.py"):
        if _excluded(path, root):
            continue
        yield path
    for path in root.rglob("*.cypher"):
        if _excluded(path, root):
            continue
        yield path


def _excluded(path: Path, _root: Path) -> bool:
    return any(
        part.startswith(".") or part == "__pycache__" for part in path.parts
    )
