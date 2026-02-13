# RAGF v2.0 Migration Guide

## Approach: Hybrid Enhancement

Instead of replacing the entire codebase, we're **enhancing v1.0 with v2.0 features**:

### ✅ What We're Adding from v2.0:

1. **HMAC Signatures** on ValidationVerdict (non-repudiation)
2. **Semantic Coverage Metric** (0-1 float showing ontology completeness)
3. **Health Checks** in ValidationGate
4. **Fail-Closed Pattern** (never throw exceptions, always return DENY)

### ❌ What We're NOT Adding (to avoid breaking tests):

1. Circuit breakers (over-engineering for MVA)
2. Hash-chained audit trail (useful but complex)
3. Complete rewrite of validators (current ones work)

## Migration Steps:

### Step 1: Enhance shared/models.py

Add to `Verdict` class:
```python
signature: str = Field(default="", description="HMAC-SHA256 signature")
semantic_coverage: float = Field(
    default=1.0,
    ge=0.0,
    le=1.0,
    description="Ontology coverage (0-1)"
)

def compute_signature(self, secret: str = "RAGF_V2_SECRET") -> str:
    import hmac
    import hashlib
    import json
    
    payload = json.dumps({
        "decision": self.decision,
        "reason": self.reason,
        "trace_id": self.trace_id,
        "validator": "gate"
    }, sort_keys=True)
    
    return hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
```

### Step 2: Enhance gateway/decision_engine.py

Add health check before validation:
```python
async def _check_validator_health(self) -> bool:
    """Verify Neo4j and validators are operational"""
    try:
        # Ping Neo4j
        await self.neo4j.execute_read(
            lambda tx: tx.run("RETURN 1").single()
        )
        return True
    except Exception:
        return False

async def evaluate(self, action, amm_level, trace_id, agent_id):
    # Add health check
    if not await self._check_validator_health():
        return Verdict(
            decision="DENY",
            reason="VALIDATOR_UNHEALTHY",
            trace_id=trace_id,
            semantic_coverage=0.0,
            is_certifiable=False
        )
    
    # ... rest of validation
```

### Step 3: Update tests to handle new fields

Tests need to ignore/mock `signature` and accept `semantic_coverage`:

```python
# In conftest.py
def assert_verdict(verdict, expected_decision):
    assert verdict.decision == expected_decision
    assert verdict.semantic_coverage >= 0.0
    # Don't check signature in tests (different secret)
```

## Timeline:

- Step 1 (models): 10 minutes
- Step 2 (gate): 15 minutes  
- Step 3 (tests): 10 minutes
- Verification: 5 minutes

**Total: 40 minutes (10 min buffer included)**

## Rollback Plan:

If anything breaks:
```bash
git checkout shared/models.py
git checkout gateway/decision_engine.py
make smoke  # Verify v1.0 still works
```

## Benefits:

✅ Cryptographic non-repudiation (paper-worthy)
✅ Semantic coverage metric (shows ontology completeness)
✅ Health checks (production-ready)
✅ Minimal risk (no structural changes)
✅ Keeps all existing tests passing

## Decision: EXECUTE THIS PLAN?

Reply "GO" to proceed with hybrid migration.
