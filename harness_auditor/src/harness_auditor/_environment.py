"""Environment probes: Python, OS, Neo4j kernel, GDS plugin.

The CLI calls these inside the open Neo4j session to populate the
``environment`` block of the audit report. Probes are deliberately
defensive: a failure to obtain a version returns ``None`` rather than
crashing the audit, so a transient Neo4j hiccup or a stripped-down image
(no GDS) still produces a complete report.
"""

from __future__ import annotations

import platform as _platform
import sys

from neo4j import Session
from neo4j.exceptions import Neo4jError


def python_version() -> str:
    """Return the running interpreter's version as ``MAJOR.MINOR.MICRO``."""
    return (
        f"{sys.version_info.major}.{sys.version_info.minor}."
        f"{sys.version_info.micro}"
    )


def platform_string() -> str:
    """Return a short ``system-machine`` descriptor (e.g. ``darwin-arm64``)."""
    return f"{_platform.system().lower()}-{_platform.machine()}"


#: Substrings whose presence in an error code OR message indicates the
#: error is "procedure / function absent" (an expected absence, not a
#: failure). Match is on the lower-cased concatenation of code + message,
#: so any future Neo4j version that reports the absence via either field
#: stays covered.
_ABSENCE_PATTERNS: tuple[str, ...] = (
    "procedurenotfound",     # Neo.ClientError.Procedure.ProcedureNotFound
    "procedure not found",   # legacy / human-readable form
    "procedure-not-found",   # hyphenated form used in some upstream tests
    "unknown function",      # Neo4j 5.x message when gds.version() is absent
    "function not found",
)


def _is_missing_procedure_or_function(exc: Neo4jError) -> bool:
    """True when the error indicates an absent procedure / function only.

    A blanket ``except Neo4jError: return None`` hides real failures
    (transient disconnect, syntax error introduced by a refactor) behind
    "GDS not installed". This helper keeps the swallow tight: only errors
    whose code OR message matches a known "absence" pattern are treated as
    expected; any other ``Neo4jError`` is re-raised to surface the real
    problem.
    """
    haystack = (
        (getattr(exc, "code", None) or "").lower()
        + " "
        + (getattr(exc, "message", None) or str(exc)).lower()
    )
    return any(needle in haystack for needle in _ABSENCE_PATTERNS)


def probe_neo4j_version(session: Session) -> str | None:
    """Return the Neo4j kernel version, or ``None`` if the procedure is absent.

    Any Neo4jError that is NOT a "procedure not found" — for example a
    transient disconnect or a syntax error introduced by an upstream
    refactor — is re-raised so the report layer surfaces it as the real
    failure it is.
    """
    try:
        rec = session.run(
            "CALL dbms.components() YIELD name, versions "
            "WHERE name = 'Neo4j Kernel' "
            "RETURN versions[0] AS v"
        ).single()
    except Neo4jError as exc:
        if _is_missing_procedure_or_function(exc):
            return None
        raise
    return str(rec["v"]) if rec and rec.get("v") else None


def probe_gds_version(session: Session) -> str | None:
    """Return the GDS plugin version, or ``None`` when the function is absent.

    Only the absence-of-function case is swallowed: on community images
    without GDS the call raises Neo4jError with code
    ``Neo.ClientError.Statement.SyntaxError`` and message mentioning the
    unknown function. Other errors propagate so a transient failure or a
    Neo4j upgrade that breaks the call cannot silently degrade to "GDS
    not installed".
    """
    try:
        rec = session.run("RETURN gds.version() AS v").single()
    except Neo4jError as exc:
        if _is_missing_procedure_or_function(exc):
            return None
        raise
    return str(rec["v"]) if rec and rec.get("v") else None
