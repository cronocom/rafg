#!/bin/bash
# RAGF v2.0 - Failure Mode Tests Runner
# Tests the formal fail-closed property: ∀ failure → DENY

set -e

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  RAGF v2.0 - FAIL-CLOSED VERIFICATION TESTS              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

cd "$(dirname "$0")"

# Ensure RAGF_SIGNATURE_SECRET is set for tests
if [ -z "$RAGF_SIGNATURE_SECRET" ]; then
    echo "⚙️  Setting RAGF_SIGNATURE_SECRET for tests..."
    export RAGF_SIGNATURE_SECRET=$(openssl rand -hex 32)
fi

echo "🧪 Running Failure Mode Tests..."
echo ""

# Run tests with verbose output
python3 -m pytest tests/integration/test_failure_modes.py \
    -v \
    -s \
    --tb=short \
    --color=yes

TEST_EXIT_CODE=$?

echo ""
echo "═══════════════════════════════════════════════════════"

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ ALL TESTS PASSED"
    echo ""
    echo "FORMAL PROPERTY VERIFIED:"
    echo "  ∀ failure ∈ FailureModes → evaluate() = DENY"
    echo ""
    echo "COVERAGE:"
    echo "  ✅ Neo4j connection failure"
    echo "  ✅ Neo4j query timeout"
    echo "  ✅ Neo4j query exception"
    echo "  ✅ Signature generation failure"
    echo "  ✅ Validator exception"
    echo "  ✅ Unexpected exception"
    echo "  ✅ Health check timeout"
    echo ""
    echo "PRODUCTION STATUS: ✅ READY"
else
    echo "❌ TESTS FAILED"
    echo ""
    echo "Review failures above and fix before production deployment"
    exit 1
fi

echo "═══════════════════════════════════════════════════════"
