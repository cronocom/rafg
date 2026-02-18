# RAGF Fintech Validators

Production-ready validators for autonomous payment agents under PSD2/PSD3 and EU AML regulations.

## Quick Start
```python
from gateway.validators.fintech import FintechValidationEngine

engine = FintechValidationEngine()

action = {
    "amount": 350.0,
    "currency": "EUR",
    "sca_completed": False,
    "customer_risk_level": "standard"
}

result = engine.validate(action)
print(f"Decision: {result.decision.value}")
print(f"Reason: {result.reason}")
```

## Validators

### PSD2 Validators
- **PSD2SCAValidator**: Strong Customer Authentication (RTS 2018/389)
- **PSD2LimitValidator**: Autonomous operation limits  
- **PSD2BeneficiaryValidator**: Whitelist verification

### AML Validators
- **AMLThresholdValidator**: Transaction thresholds (5AMLD Art. 11)
- **AMLRiskScoreValidator**: Risk-based validation

## Features

✅ Fail-closed design (<200ms latency)  
✅ Regulatory references on every decision  
✅ Comprehensive audit trail  
✅ Sequential validation with fail-fast  

## Testing
```bash
pytest tests/unit/fintech/ -v
```

## License

Apache 2.0
