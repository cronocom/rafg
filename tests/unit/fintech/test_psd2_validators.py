"""
Unit Tests - PSD2 Validators
=============================
"""

import pytest
from gateway.validators.fintech.psd2_validator import (
    Decision,
    PSD2SCAValidator,
    PSD2LimitValidator,
    PSD2BeneficiaryValidator,
)


class TestPSD2SCAValidator:
    """Test suite for SCA validator."""
    
    def test_amount_below_threshold_no_sca(self):
        """Test: Amount <EUR 30 without SCA → ALLOW."""
        validator = PSD2SCAValidator(threshold_eur=30.0)
        action = {"amount": 25.0, "sca_completed": False}
        result = validator.validate(action)
        assert result.decision == Decision.ALLOW
    
    def test_amount_above_threshold_no_sca(self):
        """Test: Amount >EUR 30 without SCA → ESCALATE."""
        validator = PSD2SCAValidator(threshold_eur=30.0)
        action = {"amount": 50.0, "sca_completed": False}
        result = validator.validate(action)
        assert result.decision == Decision.ESCALATE
        assert "SCA required" in result.reason
    
    def test_inquiry_exempt(self):
        """Test: Inquiry transactions exempt from SCA."""
        validator = PSD2SCAValidator()
        action = {"amount": 100.0, "transaction_type": "inquiry"}
        result = validator.validate(action)
        assert result.decision == Decision.ALLOW


class TestPSD2LimitValidator:
    """Test suite for limit validator."""
    
    def test_amount_below_limit(self):
        """Test: Amount within limit → ALLOW."""
        validator = PSD2LimitValidator(limit_eur=1000.0)
        action = {"amount": 750.0}
        result = validator.validate(action)
        assert result.decision == Decision.ALLOW
    
    def test_amount_exceeds_limit(self):
        """Test: Amount exceeds limit → ESCALATE."""
        validator = PSD2LimitValidator(limit_eur=1000.0)
        action = {"amount": 1500.0}
        result = validator.validate(action)
        assert result.decision == Decision.ESCALATE


class TestPSD2BeneficiaryValidator:
    """Test suite for beneficiary validator."""
    
    def test_whitelisted_beneficiary(self):
        """Test: Whitelisted IBAN → ALLOW."""
        whitelist = ["ES9121000418450200051332"]
        validator = PSD2BeneficiaryValidator(whitelist=whitelist)
        action = {"beneficiary_iban": "ES9121000418450200051332"}
        result = validator.validate(action)
        assert result.decision == Decision.ALLOW
    
    def test_missing_iban(self):
        """Test: Missing IBAN → DENY."""
        validator = PSD2BeneficiaryValidator()
        action = {}
        result = validator.validate(action)
        assert result.decision == Decision.DENY


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
