#!/bin/bash
# Monitor de servicios RAGF en tiempo real

echo "🔍 RAGF Service Monitor"
echo "══════════════════════════════════════════════════════════"

while true; do
    clear
    echo "🔍 RAGF Service Monitor - $(date '+%H:%M:%S')"
    echo "══════════════════════════════════════════════════════════"
    
    # Estado de contenedores
    docker-compose ps
    
    echo ""
    echo "══════════════════════════════════════════════════════════"
    echo "Health Checks:"
    echo "══════════════════════════════════════════════════════════"
    
    # Neo4j
    if curl -s http://localhost:7474 > /dev/null 2>&1; then
        echo "✅ Neo4j UI:        http://localhost:7474"
    else
        echo "❌ Neo4j UI:        Not ready"
    fi
    
    # API
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ API:             http://localhost:8000/health"
    else
        echo "❌ API:             Not ready"
    fi
    
    # TimescaleDB
    if docker-compose exec -T timescaledb pg_isready -U ragf > /dev/null 2>&1; then
        echo "✅ TimescaleDB:     Ready"
    else
        echo "❌ TimescaleDB:     Not ready"
    fi
    
    # Redis
    if docker-compose exec -T redis redis-cli -a redis_secure_2026 ping 2>/dev/null | grep -q PONG; then
        echo "✅ Redis:           Ready"
    else
        echo "❌ Redis:           Not ready"
    fi
    
    echo ""
    echo "Press Ctrl+C to exit"
    
    sleep 3
done
