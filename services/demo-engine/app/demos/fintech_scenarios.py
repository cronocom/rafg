"""
RAGF Demo Engine - Fintech PSD2 Scenarios
==========================================
6 interactive scenarios for fintech validation demos.
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class DemoScenario:
    """Demo scenario definition."""
    id: str
    title: str
    description: str
    action: Dict[str, Any]
    expected_outcome: str
    teaching_point: str


FINTECH_SCENARIOS = [
    DemoScenario(
        id="ft_001",
        title="✅ Normal Payment - EUR 25",
        description="Small payment to whitelisted beneficiary without SCA",
        action={
            "amount": 25.0,  # FIXED: Below EUR 30 threshold
            "currency": "EUR",
            "sca_completed": False,
            "customer_risk_level": "standard",
            "beneficiary_whitelisted": True,
            "beneficiary_iban": "ES9121000418450200051332"  # Added IBAN
        },
        expected_outcome="ALLOW",
        teaching_point="Amount below SCA threshold (EUR 30) and beneficiary approved"
    ),
    
    DemoScenario(
        id="ft_002",
        title="⚠️ SCA Required - EUR 350",
        description="Payment exceeds EUR 30 threshold without 2FA",
        action={
            "amount": 350.0,
            "currency": "EUR",
            "sca_completed": False,
            "customer_risk_level": "standard",
            "beneficiary_whitelisted": True,
            "beneficiary_iban": "ES9121000418450200051332"
        },
        expected_outcome="ESCALATE",
        teaching_point="PSD2 requires Strong Customer Authentication for amounts >EUR 30"
    ),
    
    DemoScenario(
        id="ft_003",
        title="🚨 High Amount - EUR 5,000",
        description="Payment exceeds autonomous operation limit",
        action={
            "amount": 5000.0,
            "currency": "EUR",
            "sca_completed": True,
            "customer_risk_level": "standard",
            "beneficiary_whitelisted": False,
            "beneficiary_iban": "FR7630006000011234567890189"  # Non-whitelisted
        },
        expected_outcome="ESCALATE",
        teaching_point="Amount exceeds EUR 1,000 limit - requires human approval"
    ),
    
    DemoScenario(
        id="ft_004",
        title="💰 AML Threshold - EUR 12,000",
        description="Transaction triggers AML enhanced due diligence",
        action={
            "amount": 12000.0,
            "currency": "EUR",
            "sca_completed": True,
            "customer_risk_level": "standard",
            "beneficiary_whitelisted": True,
            "beneficiary_iban": "ES9121000418450200051332"
        },
        expected_outcome="ESCALATE",
        teaching_point="5AMLD Article 11: Amounts ≥EUR 10,000 require enhanced due diligence"
    ),
    
    DemoScenario(
        id="ft_005",
        title="⚡ High Risk Score - 0.85",
        description="AML risk scoring flags suspicious transaction",
        action={
            "amount": 500.0,
            "currency": "EUR",
            "sca_completed": True,
            "risk_score": 0.85,
            "customer_risk_level": "standard",
            "beneficiary_whitelisted": True,
            "beneficiary_iban": "ES9121000418450200051332"
        },
        expected_outcome="ESCALATE",
        teaching_point="Risk score >0.8 triggers manual review per 5AMLD Article 18"
    ),
    
    DemoScenario(
        id="ft_006",
        title="❌ Missing Beneficiary",
        description="Payment without required beneficiary information",
        action={
            "amount": 100.0,
            "currency": "EUR",
            "sca_completed": True,
            "customer_risk_level": "standard"
            # Missing: beneficiary_iban (intentional for DENY scenario)
        },
        expected_outcome="DENY",
        teaching_point="PSD2 requires valid beneficiary IBAN - transaction denied"
    ),
]


def get_scenario(scenario_id: str) -> DemoScenario:
    """Get scenario by ID."""
    for scenario in FINTECH_SCENARIOS:
        if scenario.id == scenario_id:
            return scenario
    raise ValueError(f"Scenario {scenario_id} not found")
