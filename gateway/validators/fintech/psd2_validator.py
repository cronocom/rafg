"""
RAGF Fintech Module - PSD2 Validator
=====================================
Validates Strong Customer Authentication requirements under PSD2/PSD3.

References:
- Directive (EU) 2015/2366 (PSD2)
- Commission Delegated Regulation (EU) 2018/389 (RTS on SCA)

Author: Reflexio Studio
License: Apache 2.0
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, List


class Decision(Enum):
    """Validation decision outcomes."""
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"


@dataclass
class ValidationResult:
    """
    Result of a validation check.
    
    Attributes:
        decision: Allow, deny, or escalate
        reason: Human-readable explanation
        regulatory_ref: Legal reference (directive, article)
        remediation: Suggested action if not allowed
        metadata: Additional context for audit trail
    """
    decision: Decision
    reason: str
    regulatory_ref: str
    remediation: str = ""
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "regulatory_ref": self.regulatory_ref,
            "remediation": self.remediation,
            "metadata": self.metadata or {}
        }


class PSD2SCAValidator:
    """
    Strong Customer Authentication (SCA) validator.
    
    PSD2 RTS Article 97 requires SCA for:
    - Remote electronic payments
    - Transactions exceeding EUR 30
    
    Attributes:
        threshold_eur: Amount threshold for SCA requirement (default 30.0)
    """
    
    DEFAULT_THRESHOLD_EUR = 30.0
    
    def __init__(self, threshold_eur: float = DEFAULT_THRESHOLD_EUR):
        self.threshold_eur = threshold_eur
    
    def validate(self, action: Dict[str, Any]) -> ValidationResult:
        """Validate if Strong Customer Authentication is required."""
        amount = action.get("amount", 0.0)
        sca_completed = action.get("sca_completed", False)
        tx_type = action.get("transaction_type", "payment")
        
        # SCA not applicable to certain transaction types
        exempt_types = {"inquiry", "balance_check", "card_validation"}
        if tx_type in exempt_types:
            return ValidationResult(
                decision=Decision.ALLOW,
                reason=f"SCA exemption: {tx_type} transactions",
                regulatory_ref="PSD2 RTS (EU) 2018/389 Art. 97"
            )
        
        # Check amount threshold
        if amount > self.threshold_eur:
            if not sca_completed:
                return ValidationResult(
                    decision=Decision.ESCALATE,
                    reason=f"SCA required for amounts >EUR {self.threshold_eur}",
                    regulatory_ref="PSD2 RTS (EU) 2018/389 Art. 97",
                    remediation="Prompt user for two-factor authentication (2FA)",
                    metadata={
                        "threshold": self.threshold_eur,
                        "actual_amount": amount,
                        "sca_methods": ["SMS OTP", "Biometric", "Hardware token"]
                    }
                )
        
        return ValidationResult(
            decision=Decision.ALLOW,
            reason="PSD2 SCA compliance verified",
            regulatory_ref="PSD2 RTS (EU) 2018/389 Art. 97"
        )


class PSD2LimitValidator:
    """Payment initiation limit validator."""
    
    DEFAULT_LIMIT_EUR = 1000.0
    
    def __init__(self, limit_eur: float = DEFAULT_LIMIT_EUR):
        self.limit_eur = limit_eur
    
    def validate(self, action: Dict[str, Any]) -> ValidationResult:
        """Validate transaction amount against configured limit."""
        amount = action.get("amount", 0.0)
        
        if amount > self.limit_eur:
            return ValidationResult(
                decision=Decision.ESCALATE,
                reason=f"Amount exceeds autonomous limit (EUR {self.limit_eur})",
                regulatory_ref="Internal Policy - Autonomous Operation Limits",
                remediation="Human approval required",
                metadata={
                    "limit": self.limit_eur,
                    "actual_amount": amount,
                    "excess": amount - self.limit_eur
                }
            )
        
        return ValidationResult(
            decision=Decision.ALLOW,
            reason="Amount within autonomous operation limits",
            regulatory_ref="Internal Policy"
        )


class PSD2BeneficiaryValidator:
    """Beneficiary whitelist validator."""
    
    def __init__(self, whitelist: Optional[List[str]] = None):
        self.whitelist = set(whitelist) if whitelist else set()
    
    def validate(self, action: Dict[str, Any]) -> ValidationResult:
        """Validate beneficiary against whitelist."""
        if action.get("beneficiary_whitelisted", False):
            return ValidationResult(
                decision=Decision.ALLOW,
                reason="Beneficiary is pre-approved (whitelisted)",
                regulatory_ref="Internal Policy - Fraud Prevention"
            )
        
        beneficiary_iban = action.get("beneficiary_iban", "")
        
        if not beneficiary_iban:
            return ValidationResult(
                decision=Decision.DENY,
                reason="Beneficiary IBAN not provided",
                regulatory_ref="PSD2 - Payment Order Requirements",
                remediation="Provide valid beneficiary IBAN"
            )
        
        if len(self.whitelist) > 0 and beneficiary_iban not in self.whitelist:
            return ValidationResult(
                decision=Decision.ESCALATE,
                reason="Beneficiary not in approved whitelist",
                regulatory_ref="Internal Policy - Fraud Prevention",
                remediation="Add beneficiary to whitelist or obtain manual approval"
            )
        
        return ValidationResult(
            decision=Decision.ALLOW,
            reason="Beneficiary validation passed",
            regulatory_ref="Internal Policy"
        )
