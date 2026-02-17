# ragf_core/governance/bias_detector.py

"""
Ontology Bias Detection System
Implements proportionality testing for Section 7.5
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum


class BiasType(Enum):
    PROPORTIONALITY = "proportionality_violation"
    DEMOGRAPHIC = "demographic_disparity"
    TEMPORAL = "temporal_inconsistency"


@dataclass
class BiasAlert:
    rule_id: str
    bias_type: BiasType
    severity: float  # 0-1
    affected_population: str
    evidence: Dict
    recommendation: str


class ProportionalityTester:
    """
    Tests if a rule's restrictiveness is proportional to actual risk

    Implements test described in Section 7.5 of paper
    """

    def __init__(self, historical_data: List[Dict]):
        """
        Args:
            historical_data: Past actions with outcomes (approved/denied/incident)
        """
        self.data = historical_data

    def test_rule(self, proposed_rule: Dict) -> Optional[BiasAlert]:
        """
        Apply rule to historical data and check proportionality

        Returns:
            BiasAlert if rule is disproportionate, None otherwise
        """

        # Simulate rule on historical data
        would_deny = [
            action for action in self.data
            if self._rule_matches(proposed_rule, action)
        ]

        # Calculate actual incident rate in that population
        incidents_in_denied = [
            action for action in would_deny
            if action.get("resulted_in_incident", False)
        ]

        denial_rate = len(would_deny) / len(self.data) if self.data else 0
        incident_rate = (
            len(incidents_in_denied) / len(would_deny)
            if would_deny else 0
        )

        # Proportionality ratio
        if incident_rate > 0:
            proportionality_ratio = denial_rate / incident_rate
        else:
            proportionality_ratio = float('inf')

        # Alert if rule denies >>10x more than actual risk
        if proportionality_ratio > 10:
            return BiasAlert(
                rule_id=proposed_rule.get("id", "unknown"),
                bias_type=BiasType.PROPORTIONALITY,
                severity=min(proportionality_ratio / 100, 1.0),
                affected_population=f"{denial_rate:.1%} of actions",
                evidence={
                    "denial_rate": denial_rate,
                    "incident_rate": incident_rate,
                    "proportionality_ratio": proportionality_ratio,
                    "would_deny_count": len(would_deny),
                    "actual_incidents": len(incidents_in_denied)
                },
                recommendation=(
                    f"Rule may be overly restrictive. "
                    f"Denies {proportionality_ratio:.1f}x more actions than incident rate justifies. "
                    f"Consider relaxing constraints or requiring additional evidence."
                )
            )

        return None

    def _rule_matches(self, rule: Dict, action: Dict) -> bool:
        """Check if rule would deny this action"""

        # Simple implementation - extend based on your rule structure
        conditions = rule.get("conditions", [])

        for condition in conditions:
            field = condition.get("field")
            operator = condition.get("operator")  # e.g., ">", "<", "=="
            threshold = condition.get("threshold")

            action_value = action.get(field)

            if operator == ">" and action_value > threshold:
                return True
            elif operator == "<" and action_value < threshold:
                return True
            elif operator == "==" and action_value == threshold:
                return True

        return False