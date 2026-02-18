"""
RAGF Fintech Module - AML Validator
====================================
Validates Anti-Money Laundering compliance under EU 5AMLD.

References:
- Directive (EU) 2018/843 (5AMLD)

Author: Reflexio Studio
License: Apache 2.0
"""

from typing import Dict, Any
from .psd2_validator import Decision, ValidationResult


class AMLThresholdValidator:
    """
    Anti-Money Laundering threshold validator.
    
    Enforces transaction reporting thresholds per EU AML Directives:
    - EUR 10,000+ transactions require enhanced due diligence
    """
    
    STANDARD_THRESHOLD_EUR = 10000.0
    HIGH_RISK_THRESHOLD_EUR = 5000.0
    
    def __init__(
        self,
        standard_threshold: float = STANDARD_THRESHOLD_EUR,
        high_risk_threshold: float = HIGH_RISK_THRESHOLD_EUR
    ):
        self.standard_threshold = standard_threshold
        self.high_risk_threshold = high_risk_threshold
    
    def validate(self, action: Dict[str, Any]) -> ValidationResult:
        """Validate transaction against AML thresholds."""
        amount = action.get("amount", 0.0)
        customer_risk = action.get("customer_risk_level", "standard")
        
        # Determine applicable threshold
        if customer_risk in ["high_risk", "pep"]:
            threshold = self.high_risk_threshold
            risk_category = "high-risk customer or PEP"
        else:
            threshold = self.standard_threshold
            risk_category = "standard transaction"
        
        # Check if threshold exceeded
        if amount >= threshold:
            required_actions = [
                "Enhanced due diligence required",
                "Document source of funds",
            ]
            
            if customer_risk == "pep":
                required_actions.append("Senior management approval required")
            
            return ValidationResult(
                decision=Decision.ESCALATE,
                reason=f"AML threshold exceeded for {risk_category} (EUR {threshold})",
                regulatory_ref="EU Directive 2018/843 (5AMLD) Art. 11, 13",
                remediation="; ".join(required_actions),
                metadata={
                    "threshold": threshold,
                    "actual_amount": amount,
                    "customer_risk_level": customer_risk
                }
            )
        
        return ValidationResult(
            decision=Decision.ALLOW,
            reason=f"AML threshold compliant ({risk_category})",
            regulatory_ref="EU Directive 2018/843 (5AMLD) Art. 11"
        )


class AMLRiskScoreValidator:
    """AML risk score validator."""
    
    HIGH_THRESHOLD = 0.8
    
    def __init__(self, high_threshold: float = HIGH_THRESHOLD):
        self.high_threshold = high_threshold
    
    def validate(self, action: Dict[str, Any]) -> ValidationResult:
        """Validate transaction based on AML risk score."""
        risk_score = action.get("risk_score", 0.0)
        sanctions_match = action.get("sanctions_match", False)
        
        # Sanctions match = immediate escalation
        if sanctions_match:
            return ValidationResult(
                decision=Decision.DENY,
                reason="Sanctions list match detected",
                regulatory_ref="EU Regulation 269/2014, OFAC Sanctions",
                remediation="Transaction blocked. Report to compliance."
            )
        
        # High-risk score
        if risk_score >= self.high_threshold:
            return ValidationResult(
                decision=Decision.ESCALATE,
                reason=f"High AML risk score ({risk_score:.2f})",
                regulatory_ref="EU Directive 2018/843 (5AMLD) Art. 18",
                remediation="Manual review required."
            )
        
        return ValidationResult(
            decision=Decision.ALLOW,
            reason=f"Low AML risk score ({risk_score:.2f})",
            regulatory_ref="EU Directive 2018/843 (5AMLD)"
        )
