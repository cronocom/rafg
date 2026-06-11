"""RAGF Ontology Auditor — pre-execution certification of governance harnesses.

This module's ``__all__`` is the **public, stable surface** of the package.
Anything imported from a submodule but not re-exported here is considered an
implementation detail and may change between minor versions without notice.

Stability tiers
---------------

* **Stable** — listed in ``__all__`` below. Breaking changes require a major
  version bump and an entry in ``CHANGELOG.md``.
* **Internal** — every other module attribute. Reach in at your own risk;
  pin to a patch release if you do.

See ``docs/INTEGRATION.md`` for the supported library-usage patterns
(programmatic ontology loading, custom Cypher CCs, embedding in a CI gate).
"""

#: Defined before re-exports so submodules importing ``__version__`` (notably
#: ``report.py``) do not hit a partially-initialised package circular import.
__version__ = "0.2.0"

from harness_auditor.bundle import (
    BUNDLE_FORMAT,
    BundleError,
    BundleInputs,
    CryptographyMissingError,
    build_bundle,
    verify_bundle,
)
from harness_auditor.loader import (
    LoaderMismatchError,
    load,
    load_previous,
    load_taxonomy,
)
from harness_auditor.report import (
    HMAC_DOMAIN_TAG,
    aggregate,
    build_report,
    hmac_signature,
    write_artifacts,
)
from harness_auditor.runner import (
    AGGREGATOR_ROLE,
    REGISTRY,
    CriterionDefinition,
    effective_registry,
    packaged_queries_dir,
    register_criterion,
    reset_user_criteria,
    run_all,
    unregister_criterion,
)
from harness_auditor.schemas.ontology_schema import (
    Constraint,
    Domain,
    Field,
    Ontology,
    Regulation,
    Taxonomy,
    Verb,
)
from harness_auditor.schemas.report_schema import (
    AuditReport,
    CertificationStatus,
    CriterionResult,
    CriterionStatus,
    Environment,
    Severity,
)

#: Public, stable API. See module docstring for stability semantics. Grouped
#: by topic on purpose (alphabetic order would scatter related symbols), hence
#: the ``noqa`` for ruff's RUF022.
__all__ = [  # noqa: RUF022
    # Version
    "__version__",
    # Pipeline entrypoints
    "load",
    "load_previous",
    "load_taxonomy",
    "run_all",
    "build_report",
    "aggregate",
    "write_artifacts",
    "hmac_signature",
    "HMAC_DOMAIN_TAG",
    "packaged_queries_dir",
    # Registry extension (see docs/INTEGRATION.md §"Custom Cypher CCs")
    "REGISTRY",
    "AGGREGATOR_ROLE",
    "CriterionDefinition",
    "effective_registry",
    "register_criterion",
    "unregister_criterion",
    "reset_user_criteria",
    # Schema · ontology
    "Constraint",
    "Domain",
    "Field",
    "Ontology",
    "Regulation",
    "Taxonomy",
    "Verb",
    # Schema · report
    "AuditReport",
    "CertificationStatus",
    "CriterionResult",
    "CriterionStatus",
    "Environment",
    "Severity",
    # Attestation bundles (v0.2 differentiator; needs the [bundle] extra)
    "BUNDLE_FORMAT",
    "BundleInputs",
    "build_bundle",
    "verify_bundle",
    # Errors
    "LoaderMismatchError",
    "BundleError",
    "CryptographyMissingError",
]
