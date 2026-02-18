"""
RAGF Fintech Module - Composite Validator
==========================================
Orchestrates multiple validators for comprehensive fintech compliance.

Author: Reflexio Studio
License: Apache 2.0
"""

import time
from typing import Dict, Any, Optional
from .psd2_validator import (
    Decision,
    ValidationResult,
    PSD2SCAValidator,
    PSD2LimitValidator,
    PSD2BeneficiaryValidator,
)
from .aml_validator import (
    AMLThresholdValidator,
    AMLRiskScoreValidator,
)


class FintechValidationEngine:
    """
    Composite validation engine for fintech compliance.
    
    Orchestrates multiple validators in sequence with fail-fast behavior.
    """
    
    DEFAULT_MAX_LATENCY_MS = 200.0
    
    def __init__(
        self,
        max_latency_ms: float = DEFAULT_MAX_LATENCY_MS,
        enable_circuit_breaker: bool = True,
        custom_config: Optional[Dict[str, Any]] = None
    ):
        self.max_latency_ms = max_latency_ms
        self.enable_circuit_breaker = enable_circuit_breaker
        self.config = custom_config or {}
        
        # Initialize validators
        self.psd2_limit = PSD2LimitValidator(
            limit_eur=self.config.get("psd2_limit_eur", 1000.0)
        )
        self.psd2_sca = PSD2SCAValidator(
            threshold_eur=self.config.get("psd2_sca_threshold_eur", 30.0)
        )
        self.psd2_beneficiary = PSD2BeneficiaryValidator(
            whitelist=self.config.get("beneficiary_whitelist", [])
        )
        self.aml_threshold = AMLThresholdValidator()
        self.aml_risk_score = AMLRiskScoreValidator()
        
        # Validator execution order
        self.validators = [
            ("psd2_limit", self.psd2_limit),
            ("psd2_sca", self.psd2_sca),
            ("aml_threshold", self.aml_threshold),
            ("aml_risk_score", self.aml_risk_score),
            ("psd2_beneficiary", self.psd2_beneficiary),
        ]
    
    def validate(self, action: Dict[str, Any]) -> ValidationResult:
        """
        Validate action through all configured validators.
        
        Executes validators sequentially with fail-fast behavior.
        """
        start_time = time.time()
        
        try:
            # Execute validators in sequence
            for validator_name, validator in self.validators:
                result = validator.validate(action)
                
                # Fail-fast on deny or escalate
                if result.decision != Decision.ALLOW:
                    if result.metadata is None:
                        result.metadata = {}
                    result.metadata["failed_validator"] = validator_name
                    return self._finalize_result(result, start_time)
                
                # Check latency budget
                elapsed_ms = (time.time() - start_time) * 1000
                if self.enable_circuit_breaker and elapsed_ms > self.max_latency_ms:
                    return self._handle_timeout(elapsed_ms)
            
            # All validators passed
            return self._create_allow_result(start_time)
        
        except Exception as e:
            return self._handle_error(e, start_time)
    
    def _finalize_result(self, result: ValidationResult, start_time: float) -> ValidationResult:
        """Add performance metrics to result."""
        latency_ms = (time.time() - start_time) * 1000
        if result.metadata is None:
            result.metadata = {}
        result.metadata["latency_ms"] = round(latency_ms, 2)
        return result
    
    def _create_allow_result(self, start_time: float) -> ValidationResult:
        """Create final ALLOW result."""
        latency_ms = (time.time() - start_time) * 1000
        return ValidationResult(
            decision=Decision.ALLOW,
            reason="All fintech compliance checks passed",
            regulatory_ref="PSD2 (EU) 2015/2366, 5AMLD (EU) 2018/843",
            metadata={"latency_ms": round(latency_ms, 2)}
        )
    
    def _handle_timeout(self, elapsed_ms: float) -> ValidationResult:
        """Handle validation timeout (circuit breaker)."""
        return ValidationResult(
            decision=Decision.DENY,
            reason=f"Validation timeout: {elapsed_ms:.2f}ms exceeds limit",
            regulatory_ref="RAGF Fail-Closed Design",
            remediation="Retry transaction.",
            metadata={"timeout": True, "elapsed_ms": round(elapsed_ms, 2)}
        )
    
    def _handle_error(self, error: Exception, start_time: float) -> ValidationResult:
        """Handle unexpected validation errors."""
        latency_ms = (time.time() - start_time) * 1000
        return ValidationResult(
            decision=Decision.DENY,
            reason=f"Validation error: {type(error).__name__}",
            regulatory_ref="RAGF Fail-Closed Design",
            remediation="Contact support.",
            metadata={"error": True, "latency_ms": round(latency_ms, 2)}
        )
