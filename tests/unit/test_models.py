"""
═══════════════════════════════════════════════════════════
RAGF Unit Tests - Models
Tests para shared/models.py
═══════════════════════════════════════════════════════════
"""

import pytest
from pydantic import ValidationError
from shared.models import (
    ActionPrimitive,
    AMMLevel,
    SemanticVerdict,
    ValidatorResult,
    Verdict
)


def test_action_primitive_valid():
    """Test creación válida de ActionPrimitive"""
    action = ActionPrimitive(
        verb="reroute_flight",
        resource="flight:IB3202",
        parameters={"destination": "MAD"},
        domain="aviation",
        confidence=0.95
    )
    
    assert action.verb == "reroute_flight"
    assert action.domain == "aviation"
    assert action.confidence == 0.95


def test_action_primitive_invalid_verb():
    """Test que verb debe ser lowercase"""
    with pytest.raises(ValidationError):
        ActionPrimitive(
            verb="RerouteFlight",  # ❌ Uppercase
            resource="flight:IB3202",
            parameters={},
            domain="aviation"
        )


def test_action_primitive_confidence_range():
    """Test que confidence está entre 0-1"""
    with pytest.raises(ValidationError):
        ActionPrimitive(
            verb="reroute_flight",
            resource="flight:IB3202",
            parameters={},
            domain="aviation",
            confidence=1.5  # ❌ > 1.0
        )


def test_amm_level_values():
    """Test valores de AMMLevel enum"""
    assert AMMLevel.PASSIVE_KNOWLEDGE == 1
    assert AMMLevel.HUMAN_TEAMING == 2
    assert AMMLevel.ACTIONABLE_AGENCY == 3
    assert AMMLevel.AUTONOMOUS_ORCHESTRATION == 4
    assert AMMLevel.FULL_SYSTEMIC_AUTONOMY == 5


def test_verdict_is_certifiable_true():
    """Test Verdict.is_certifiable cuando todas las condiciones se cumplen"""
    semantic_verdict = SemanticVerdict(
        decision="ALLOW",
        reason="OK",
        ontology_match=True,
        amm_authorized=True,
        coverage=1.0
    )
    
    validator_results = [
        ValidatorResult(
            validator_name="FuelReserveValidator",
            decision="PASS",
            reason="OK",
            latency_ms=45.0
        )
    ]
    
    action = ActionPrimitive(
        verb="reroute_flight",
        resource="flight:IB3202",
        parameters={},
        domain="aviation"
    )
    
    verdict = Verdict(
        trace_id="test-001",
        decision="ALLOW",
        reason="All checks passed",
        amm_level=AMMLevel.ACTIONABLE_AGENCY,
        semantic_verdict=semantic_verdict,
        validator_results=validator_results,
        total_latency_ms=150.0,
        action=action
    )
    
    assert verdict.is_certifiable is True


def test_verdict_is_certifiable_false_high_latency():
    """Test Verdict.is_certifiable falla si latencia > 200ms"""
    semantic_verdict = SemanticVerdict(
        decision="ALLOW",
        reason="OK",
        ontology_match=True,
        amm_authorized=True,
        coverage=1.0
    )
    
    validator_results = [
        ValidatorResult(
            validator_name="FuelReserveValidator",
            decision="PASS",
            reason="OK",
            latency_ms=45.0
        )
    ]
    
    action = ActionPrimitive(
        verb="reroute_flight",
        resource="flight:IB3202",
        parameters={},
        domain="aviation"
    )
    
    verdict = Verdict(
        trace_id="test-002",
        decision="ALLOW",
        reason="All checks passed",
        amm_level=AMMLevel.ACTIONABLE_AGENCY,
        semantic_verdict=semantic_verdict,
        validator_results=validator_results,
        total_latency_ms=250.0,  # ❌ > 200ms
        action=action
    )
    
    assert verdict.is_certifiable is False


def test_verdict_is_certifiable_false_validator_fail():
    """Test Verdict.is_certifiable falla si algún validator FAIL"""
    semantic_verdict = SemanticVerdict(
        decision="ALLOW",
        reason="OK",
        ontology_match=True,
        amm_authorized=True,
        coverage=1.0
    )
    
    validator_results = [
        ValidatorResult(
            validator_name="FuelReserveValidator",
            decision="FAIL",  # ❌ FAIL
            reason="Insufficient fuel",
            latency_ms=45.0,
            rule_violated="FAA-14-CFR-91.151"
        )
    ]
    
    action = ActionPrimitive(
        verb="reroute_flight",
        resource="flight:IB3202",
        parameters={},
        domain="aviation"
    )
    
    verdict = Verdict(
        trace_id="test-003",
        decision="DENY",
        reason="Validator failed",
        amm_level=AMMLevel.ACTIONABLE_AGENCY,
        semantic_verdict=semantic_verdict,
        validator_results=validator_results,
        total_latency_ms=150.0,
        action=action
    )
    
    assert verdict.is_certifiable is False
