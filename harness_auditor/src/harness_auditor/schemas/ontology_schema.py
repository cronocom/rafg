"""
Pydantic models for the YAML ontology input.

The schema mirrors the RAGF Semantic Authority Layer as documented in the v2.4
paper: a Domain root, a set of Verbs (governed actions), Regulations (normative
references), Constraints (executable rules) and Fields (payload attributes that
constraints evaluate). The auditor consumes this structure, projects it into
Neo4j, and evaluates each certification criterion against the resulting graph.

Schema versioning is explicit. Breaking changes to this schema bump the major
version of the auditor package and are documented in CHANGELOG.md.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints
from pydantic import Field as PydField

# ---------------------------------------------------------------------------
# Primitive types
# ---------------------------------------------------------------------------

#: Identifiers are lowercase snake_case, between 2 and 80 chars.
Identifier = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,79}$", strip_whitespace=True),
]

#: Regulation codes follow the convention used in the AgentSave dictionary
#: (e.g. ``PSD2_ART97_SCA``, ``5AMLD_ART18_EDD``). Upper-case, underscored.
RegulationCode = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9_]{1,79}$", strip_whitespace=True),
]


class Decision(StrEnum):
    """Verdict that a constraint emits when its condition is violated.

    ``ALLOW`` is intentionally absent: a constraint that resolves to ALLOW
    inverts the governance semantics and is rejected by CC-09.
    """

    ESCALATE = "ESCALATE"
    DENY = "DENY"


class ConstraintType(StrEnum):
    """The six declarative constraint types understood by the evaluator."""

    THRESHOLD = "threshold"
    CONDITIONAL_THRESHOLD = "conditional_threshold"
    VERB_TAXONOMY_CHECK = "verb_taxonomy_check"
    AMM_LEVEL_CHECK = "amm_level_check"
    REQUIRED_FIELD = "required_field"
    SUPERSEDES_CONDITION = "supersedes_condition"


class Operator(StrEnum):
    """Comparison operators allowed in threshold constraints."""

    GTE = "gte"
    GT = "gt"
    LTE = "lte"
    LT = "lt"
    EQ = "eq"
    NEQ = "neq"
    IN = "in"
    NOT_IN = "not_in"


class RiskLevel(StrEnum):
    """Risk level associated with a verb, used by CC-08 (Authority gradient)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FieldType(StrEnum):
    """Primitive types for payload fields."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    OBJECT = "object"


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


class Domain(BaseModel):
    """Root of the ontology graph."""

    model_config = ConfigDict(extra="forbid")

    name: Identifier
    version: str = PydField(pattern=r"^\d+\.\d+\.\d+$")
    description: str | None = None


class Regulation(BaseModel):
    """A regulatory framework or specific article."""

    model_config = ConfigDict(extra="forbid")

    code: RegulationCode
    name: str
    description: str | None = None
    celex: str | None = PydField(default=None, description="EUR-Lex CELEX reference")
    informational: bool = PydField(
        default=False,
        description=(
            "If true, the regulation may exist without being REFERENCED by any "
            "constraint without triggering CC-03."
        ),
    )


class Field(BaseModel):
    """A payload field that constraints may CHECK."""

    model_config = ConfigDict(extra="forbid")

    name: Identifier
    type: FieldType
    description: str | None = None
    required: bool = False


class Verb(BaseModel):
    """A governed action."""

    model_config = ConfigDict(extra="forbid")

    name: Identifier
    description: str | None = None
    risk_level: RiskLevel
    min_amm_level: int = PydField(ge=1, le=5)
    requires_human_approval: bool = False
    must_satisfy: list[RegulationCode] = PydField(default_factory=list)
    payload_schema: list[Field] = PydField(default_factory=list)


class Constraint(BaseModel):
    """An executable rule attached to a verb."""

    model_config = ConfigDict(extra="forbid")

    name: Identifier
    type: ConstraintType
    verb: Identifier
    decision_if_violated: Decision
    regulation: RegulationCode
    reason: str
    severity: RiskLevel
    precedence_level: int = PydField(ge=0, le=1000)

    # Threshold / conditional_threshold parameters
    parameter: Identifier | None = None
    operator: Operator | None = None
    value: float | int | str | bool | list[Any] | None = None

    # conditional_threshold extras
    condition_field: Identifier | None = None
    condition_value: float | int | str | bool | None = None

    # supersedes_condition extras
    supersedes: Identifier | None = PydField(
        default=None,
        description="Name of the constraint that this one overrides when triggered.",
    )


# ---------------------------------------------------------------------------
# Root document
# ---------------------------------------------------------------------------


class Ontology(BaseModel):
    """Top-level YAML document consumed by the auditor.

    The ontology is hashed (SHA-256) on load; the digest accompanies the report
    and provides an immutable reference for downstream attestation.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = PydField(default="1.0", pattern=r"^\d+\.\d+$")
    domain: Domain
    regulations: list[Regulation]
    verbs: list[Verb]
    constraints: list[Constraint]


class Taxonomy(BaseModel):
    """Registered verb taxonomy for a domain (consumed by CC-10).

    A taxonomy lists the verbs *ever accepted* by any auditor-recognised
    registry for the given domain. CC-10 flags any verb in the ontology that
    is not present in the taxonomy as a hallucinated verb — an unauthorised
    expansion of the governance surface area.
    """

    model_config = ConfigDict(extra="forbid")

    domain: Identifier
    verbs: list[Identifier]
