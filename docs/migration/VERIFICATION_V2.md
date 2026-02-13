# RAGF v2.0 Migration - Verification Steps

## ✅ Changes Completed

### 1. Enhanced `shared/models.py`
- ✅ Added HMAC-SHA256 signatures to `Verdict` class
- ✅ Added `compute_signature()` method
- ✅ Added `verify_signature()` method  
- ✅ Added `semantic_coverage` property (alias)
- ✅ Imported `hmac`, `hashlib`, `json`

### 2. Enhanced `gateway/decision_engine.py`
- ✅ Added `_check_validator_health()` method with caching
- ✅ Added health check before validation (fail-closed pattern)
- ✅ Auto-generate HMAC signature on every verdict
- ✅ Log signature (first 16 chars) for audit trail

## 🧪 Verification Commands

Run these commands to verify the migration succeeded:

### Step 1: Run Smoke Tests
```bash
cd /Users/ianmont/Dev/rafg
make smoke
```

**Expected Output**:
```
test_scenario_allow PASSED
test_scenario_deny_fuel PASSED
test_scenario_deny_unknown_verb PASSED
test_scenario_deny_amm_violation PASSED
test_summary PASSED

========================= 5 passed in 0.25s =========================
```

### Step 2: Run Benchmarks
```bash
make benchmark
```

**Expected Output**:
```
Safety Rate: 100.0% ✅
False Positive Rate: 0.0% ✅
Latency p50: ~5ms ✅
Latency p95: ~27ms ✅ (may be slightly higher due to health checks)
```

### Step 3: Test New Features

#### A. Verify HMAC Signatures
```bash
docker compose exec api python3 <<EOF
from shared.models import Verdict, SemanticVerdict, ActionPrimitive, AMMLevel

# Create a verdict
verdict = Verdict(
    trace_id="test-001",
    decision="ALLOW",
    reason="Test",
    amm_level=AMMLevel.ACTIONABLE_AGENCY,
    semantic_verdict=SemanticVerdict(
        decision="ALLOW",
        reason="OK",
        ontology_match=True,
        amm_authorized=True,
        coverage=1.0
    ),
    validator_results=[],
    total_latency_ms=10.5,
    action=ActionPrimitive(
        verb="read",
        resource="test",
        parameters={},
        domain="aviation"
    )
)

# Compute signature
sig = verdict.compute_signature()
print(f"✅ Signature generated: {sig[:16]}...")
print(f"   Length: {len(sig)} chars (expected: 64)")

# Verify signature
verdict.signature = sig
is_valid = verdict.verify_signature()
print(f"✅ Signature valid: {is_valid}")

# Test tampering detection
verdict.decision = "DENY"  # Change decision
tampered_valid = verdict.verify_signature()
print(f"✅ Tampering detected: {not tampered_valid}")
EOF
```

**Expected Output**:
```
✅ Signature generated: a1b2c3d4e5f6g7h8...
   Length: 64 chars (expected: 64)
✅ Signature valid: True
✅ Tampering detected: True
```

#### B. Verify Health Checks
```bash
# Healthy case
docker compose exec api python3 <<EOF
import asyncio
from gateway.decision_engine import DecisionEngine
from gateway.neo4j_client import Neo4jClient

async def test_health():
    neo4j = Neo4jClient(
        uri="bolt://neo4j:7687",
        user="neo4j",
        password="ragf_secure_2026"
    )
    await neo4j.connect()
    
    engine = DecisionEngine(neo4j)
    healthy = await engine._check_validator_health()
    
    print(f"✅ Health check: {healthy}")
    
    await neo4j.close()

asyncio.run(test_health())
EOF
```

**Expected Output**:
```
✅ Health check: True
```

### Step 4: Check Logs for v2.0 Features
```bash
docker compose logs api | grep -E "signature|health_check|semantic_coverage" | tail -20
```

**Expected**: Should see log entries with signature hashes and health check results.

## ✅ Success Criteria

- [ ] All 5 smoke tests pass
- [ ] Benchmark shows 100% safety rate, 0% false positives
- [ ] HMAC signatures generate correctly (64 char hex)
- [ ] Signature verification detects tampering
- [ ] Health checks return True when Neo4j is up
- [ ] Logs show signature field (e.g., `signature=a1b2c3d4...`)
- [ ] Latency p95 still <50ms (health check adds ~2-5ms)

## 🚨 Rollback if Needed

If any tests fail:
```bash
git checkout backup-v1.0
git checkout shared/models.py
git checkout gateway/decision_engine.py
make smoke  # Verify v1.0 works
```

## 📊 Expected Improvements

### Before (v1.0):
```python
verdict = Verdict(...)
# No signature
# No health checks
# No tampering detection
```

### After (v2.0):
```python
verdict = Verdict(...)
verdict.signature = "a1b2c3d4..."  # Auto-generated
verdict.verify_signature()  # Returns True
verdict.semantic_coverage  # Returns 0-1 float

# Health check runs before validation
# Fail-closed pattern: unhealthy validators → DENY
```

## 🎯 Next Steps After Verification

1. ✅ Commit v2.0 changes
2. ✅ Update README with v2.0 features
3. ✅ Add signature verification to paper (ACM)
4. ✅ Benchmark with signature overhead (should be <0.5ms)

---

**Execute these verification steps and paste the results.**
