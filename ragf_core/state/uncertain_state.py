# ragf_core/state/uncertain_state.py

"""
State Uncertainty Management
Addresses Section 7.6.2 limitations
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional
from enum import Enum


class StateConfidence(Enum):
    HIGH = 3  # < 5 min old, authoritative source
    MEDIUM = 2  # < 1 hour, reliable source
    LOW = 1  # > 1 hour or secondary source
    UNKNOWN = 0  # No freshness metadata


@dataclass
class StateValue:
    """Value with confidence metadata"""

    value: Any
    source: str
    timestamp: datetime
    base_confidence: StateConfidence

    # Freshness decay parameters
    high_confidence_ttl: timedelta = timedelta(minutes=5)
    medium_confidence_ttl: timedelta = timedelta(hours=1)

    @property
    def age(self) -> timedelta:
        return datetime.utcnow() - self.timestamp

    @property
    def current_confidence(self) -> StateConfidence:
        """Confidence degrades with age"""

        if self.age < self.high_confidence_ttl:
            return StateConfidence.HIGH
        elif self.age < self.medium_confidence_ttl:
            return StateConfidence.MEDIUM
        else:
            return StateConfidence.LOW

    @property
    def is_acceptable(self) -> bool:
        """Is this value still usable?"""
        return self.current_confidence != StateConfidence.UNKNOWN


# Extend HealthcareValidator with uncertainty awareness
class UncertaintyAwareHealthcareValidator:
    """
    Example: Medication dosage with state freshness requirements
    """

    REQUIRED_CONFIDENCE = {
        "patient_weight": StateConfidence.HIGH,  # < 5 min for dosage calc
        "lab_results": StateConfidence.MEDIUM,  # < 1 hour acceptable
        "medical_history": StateConfidence.LOW  # Can be older
    }

    async def validate_with_uncertainty(
            self,
            action: Dict,
            state: Dict[str, StateValue]
    ) -> Dict:
        """
        Validate action, DENY if required state is too stale
        """

        # Check all required state values
        for key, required_conf in self.REQUIRED_CONFIDENCE.items():
            if key not in state:
                return {
                    "decision": "DENY",
                    "reason": f"Required state '{key}' not available"
                }

            state_val = state[key]
            current_conf = state_val.current_confidence

            if current_conf.value < required_conf.value:
                return {
                    "decision": "DENY",
                    "reason": (
                        f"State '{key}' too stale for this action. "
                        f"Required: {required_conf.name}, "
                        f"Actual: {current_conf.name} "
                        f"(age: {state_val.age.total_seconds():.0f}s)"
                    ),
                    "metadata": {
                        "stale_field": key,
                        "age_seconds": state_val.age.total_seconds(),
                        "required_confidence": required_conf.name,
                        "actual_confidence": current_conf.name
                    }
                }

        # All state fresh enough - proceed with standard validation
        return await self._standard_validation(action, state)