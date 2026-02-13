#!/bin/bash
# ═══════════════════════════════════════════════════════════
# RAGF Pre-flight Check
# Verifica que todo está listo antes del deployment
# ═══════════════════════════════════════════════════════════

echo "🔍 RAGF Pre-flight Checklist"
echo "═══════════════════════════════════════════════════════════"

# Check 1: .env exists
if [ -f ".env" ]; then
    echo "✅ .env file exists"
    
    # Check if API key is set
    if grep -q "ANTHROPIC_API_KEY=sk-ant" .env; then
        echo "✅ Anthropic API key configured"
    else
        echo "❌ Anthropic API key NOT configured"
        exit 1
    fi
else
    echo "❌ .env file missing"
    exit 1
fi

# Check 2: Docker installed
if command -v docker &> /dev/null; then
    echo "✅ Docker installed"
else
    echo "❌ Docker NOT installed"
    exit 1
fi

# Check 3: Docker Compose installed
if command -v docker-compose &> /dev/null; then
    echo "✅ Docker Compose installed"
else
    echo "❌ Docker Compose NOT installed"
    exit 1
fi

# Check 4: Key files exist
echo ""
echo "📂 Checking key files..."

files=(
    "docker-compose.yml"
    "Dockerfile"
    "Makefile"
    "requirements.txt"
    "gateway/main.py"
    "gateway/neo4j_client.py"
    "gateway/decision_engine.py"
    "gateway/intent_normalizer.py"
    "gateway/ontologies/aviation_seed.cypher"
    "shared/models.py"
    "audit/schema.sql"
    "tests/smoke_test.py"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file"
    else
        echo "❌ $file MISSING"
        exit 1
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "🎉 All checks passed! Ready to deploy."
echo ""
echo "Next steps:"
echo "  1. git add . && git commit -m 'Initial commit'"
echo "  2. git push"
echo "  3. make build"
echo "  4. make up"
echo "  5. make seed"
echo "  6. make smoke"
echo "═══════════════════════════════════════════════════════════"
