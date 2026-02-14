# RAGF v2.0 - Intensive Technical Audit
**Date**: February 14, 2026  
**Duration**: 6 hours  
**Objective**: Production-grade hardening + ACM documentation

---

## 🎯 MISSION

Transform RAGF v2.0 from "passes tests" to "certifiable in production" by:
1. Hardening commitment boundary
2. Fixing cryptographic vulnerabilities  
3. Proving 100% fail-closed behavior
4. Documenting performance reality

**Risk Reduction**: MEDIUM → LOW  
**Effort**: 6 hours intensive

---

## 🔍 BLOCK 1: BOUNDARY AUDIT (2h)

**Question**: Where does the system commit to a decision?

**Files**: `decision_engine.py`, `main.py`, `models.py`, `ledger.py`

**Checklist**:
- [ ] Can LLM bypass Validation Gate?
- [ ] Are there unsigned verdict paths?
- [ ] Is signature atomically linked to persistence?
- [ ] Can gate be disabled via config?

**Deliverable**: `01_boundary_analysis.md` + fixes

---

## 🔐 BLOCK 2: CRYPTO AUDIT (1.5h)

**Vulnerabilities Identified**:

❌ **V1: Hardcoded Secret** (`models.py:204`)
```python
def _compute_signature(self, secret_key: str = "RAGF_SECRET_V2"):
```

❌ **V2: No Error Handling** (`decision_engine.py:312`)
```python
verdict.signature = verdict.compute_signature()  # Can raise!
```

❌ **V3: No Key Rotation** (missing monitoring)

**Fixes Required**:
1. Move secret to `RAGF_SIGNATURE_SECRET` env var
2. Wrap signature generation in try/except → fail-closed
3. Add 90-day key age warning

**Deliverable**: Fixed code + `02_crypto_audit.md`

---

## 🛡️ BLOCK 3: FAIL-CLOSED VERIFICATION (1h)

**Failure Scenarios**:

| Scenario | Expected | Status |
|----------|----------|--------|
| Neo4j down | DENY | ✅ Health check |
| Validator exception | DENY | ❌ Not handled |
| Signature fails | DENY | ❌ Not handled |
| Timeout | DENY | ⚠️ Partial |

**Fix**: Comprehensive error handling in `evaluate()`:
```python
try:
    # All operations
except Exception as e:
    return self._fail_closed("GATE_ERROR")
```

**Deliverable**: Fixed code + `test_failure_modes.py`

---

## 📊 BLOCK 4: LATENCY TRUTH (30min)

**Add instrumentation**:
```python
timings['health_ms'] = ...
timings['semantic_ms'] = ...
timings['validators_ms'] = ...
timings['signature_ms'] = ...
```

**Generate table**: Component latencies (p50/p95/p99)

**Deliverable**: `04_latency_breakdown.md` + CSV

---

## 📄 ASSESSMENT DOCUMENT

Final output: `RAGF_v2_Technical_Assessment.md`

Sections:
1. Executive Summary
2. Boundary Analysis
3. Cryptographic Audit
4. Fail-Closed Verification
5. Performance Reality
6. Production Readiness Conclusion

---

## ⏰ SCHEDULE

```
09:00-11:00  Block 1 (Boundary)
11:00-12:30  Block 2 (Crypto)
12:30-13:00  BREAK
13:00-14:00  Block 3 (Fail-Closed)
14:00-14:30  Block 4 (Latency)
14:30-15:00  Write Assessment
15:00-15:30  Test + Commit
```

---

## ✅ SUCCESS CRITERIA

- [ ] Secrets in environment variables
- [ ] All error paths return DENY
- [ ] Latency breakdown measured
- [ ] Assessment document complete
- [ ] All tests passing
- [ ] Git: "audit: Harden v2.0 for production"

---

**Ready to make RAGF bulletproof.** 🛡️
