"""
RAGF Benchmark — Query Latency Comparison
Neo4j vs PostgreSQL para validación semántica de ontología PSD2

3 patrones de query que representan casos reales del Validation Gate:
  Q1 — Existence check (1-hop): ¿existe este verbo?
  Q2 — Full validation (3-hop): verbo → dominio → regulaciones → constraints
  Q3 — AMM gate check: validación completa con filtro de nivel de madurez
"""
import asyncio
import time
import statistics
import json
from datetime import datetime

import asyncpg
from neo4j import AsyncGraphDatabase

# ── Conexiones ────────────────────────────────────────────────────────────────
NEO4J_URI  = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "ragf2026")
PG_DSN     = "postgresql://ragf:ragf_benchmark_2026@127.0.0.1:5433/ragf_ontology"

ITERATIONS = 1000

# Verbos representativos de cada nivel de complejidad
TEST_CASES = {
    "q1_simple":   {"verb": "query_account_balance", "amm": 1},   # 1 regulación
    "q2_medium":   {"verb": "initiate_payment",      "amm": 2},   # 1 reg + 2 constraints
    "q3_complex":  {"verb": "override_fraud_flag",   "amm": 5},   # 3 regs + 2 constraints
    "q4_deny":     {"verb": "override_fraud_flag",   "amm": 2},   # mismo verbo, AMM insuficiente
    "q5_hallucin": {"verb": "delete_all_accounts",   "amm": 5},   # verbo que no existe
}


# ── Neo4j Queries ─────────────────────────────────────────────────────────────
NEO4J_Q = """
MATCH (v:BM_Verb {name: $verb_name})
WHERE v.min_amm_level <= $amm_level
OPTIONAL MATCH (v)-[:BM_MUST_SATISFY]->(r:BM_Regulation)
OPTIONAL MATCH (v)-[:BM_REQUIRES_CONSTRAINT]->(c:BM_Constraint)
WITH v,
     collect(DISTINCT r.code) AS regulations,
     collect(DISTINCT c.predicate) AS constraints
RETURN
  v.name            AS verb,
  v.min_amm_level   AS required_level,
  $amm_level        AS agent_level,
  regulations,
  constraints,
  size(regulations) AS reg_count,
  CASE WHEN size(regulations) > 0 THEN 1.0 ELSE 0.0 END AS coverage
"""

NEO4J_EXIST_Q = """
MATCH (v:BM_Verb {name: $verb_name})
RETURN v.name AS verb, v.min_amm_level AS amm_level
LIMIT 1
"""


# ── PostgreSQL Queries ────────────────────────────────────────────────────────
PG_Q = """
SELECT
    v.name                              AS verb,
    v.min_amm_level                     AS required_level,
    $2::integer                         AS agent_level,
    array_agg(DISTINCT r.code)          AS regulations,
    array_agg(DISTINCT c.predicate)     AS constraints,
    count(DISTINCT r.id)::integer       AS reg_count,
    CASE WHEN count(DISTINCT r.id) > 0 THEN 1.0 ELSE 0.0 END AS coverage
FROM bm_verbs v
LEFT JOIN bm_verb_regulations vr ON v.id = vr.verb_id
LEFT JOIN bm_regulations r       ON vr.reg_id = r.id
LEFT JOIN bm_verb_constraints vc ON v.id = vc.verb_id
LEFT JOIN bm_constraints c       ON vc.constraint_id = c.id
WHERE v.name = $1::text
  AND v.min_amm_level <= $2::integer
GROUP BY v.name, v.min_amm_level
"""

PG_EXIST_Q = """
SELECT name, min_amm_level
FROM bm_verbs
WHERE name = $1
LIMIT 1
"""


# ── Runner ────────────────────────────────────────────────────────────────────
def stats(latencies: list) -> dict:
    if not latencies:
        return {"p50": 0, "p95": 0, "p99": 0, "mean": 0, "min": 0, "max": 0}
    s = sorted(latencies)
    n = len(s)
    return {
        "p50":  round(s[int(n * 0.50)], 3),
        "p95":  round(s[int(n * 0.95)], 3),
        "p99":  round(s[int(n * 0.99)], 3),
        "mean": round(statistics.mean(s), 3),
        "min":  round(s[0], 3),
        "max":  round(s[-1], 3),
    }


async def bench_neo4j(iterations: int) -> dict:
    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    results = {}

    async with driver.session() as session:
        for name, tc in TEST_CASES.items():
            latencies = []
            # warmup
            for _ in range(20):
                await session.run(NEO4J_Q, verb_name=tc["verb"], amm_level=tc["amm"])

            for _ in range(iterations):
                t0 = time.perf_counter()
                result = await session.run(
                    NEO4J_Q,
                    verb_name=tc["verb"],
                    amm_level=tc["amm"]
                )
                records = await result.data()
                latencies.append((time.perf_counter() - t0) * 1000)

            results[name] = {
                "verdict": "ALLOW" if records else "DENY",
                "records": len(records),
                **stats(latencies)
            }
            print(f"  Neo4j {name:15s} → {results[name]['verdict']:5s} "
                  f"p50={results[name]['p50']:.3f}ms "
                  f"p95={results[name]['p95']:.3f}ms")

    await driver.close()
    return results


async def bench_postgres(iterations: int) -> dict:
    conn = await asyncpg.connect(PG_DSN)
    results = {}

    # Preparar statements
    stmt_full  = await conn.prepare(PG_Q)
    stmt_exist = await conn.prepare(PG_EXIST_Q)

    for name, tc in TEST_CASES.items():
        latencies = []
        # warmup
        for _ in range(20):
            await stmt_full.fetch(tc["verb"], int(tc["amm"]))

        for _ in range(iterations):
            t0 = time.perf_counter()
            records = await stmt_full.fetch(tc["verb"], int(tc["amm"]))
            latencies.append((time.perf_counter() - t0) * 1000)

        results[name] = {
            "verdict": "ALLOW" if records else "DENY",
            "records": len(records),
            **stats(latencies)
        }
        print(f"  PG    {name:15s} → {results[name]['verdict']:5s} "
              f"p50={results[name]['p50']:.3f}ms "
              f"p95={results[name]['p95']:.3f}ms")

    await conn.close()
    return results


async def main():
    print(f"\n{'='*60}")
    print(f"  RAGF Benchmark — Neo4j vs PostgreSQL")
    print(f"  Iteraciones: {ITERATIONS} por query")
    print(f"  Timestamp: {datetime.utcnow().isoformat()}Z")
    print(f"{'='*60}\n")

    print("► Neo4j (warmup + benchmark)...")
    neo4j_results = await bench_neo4j(ITERATIONS)

    print("\n► PostgreSQL (warmup + benchmark)...")
    pg_results = await bench_postgres(ITERATIONS)

    # ── Tabla comparativa ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  RESULTADOS — latencia en ms")
    print(f"{'='*60}")
    print(f"{'Query':<18} {'DB':<10} {'Verdict':<8} "
          f"{'p50':>8} {'p95':>8} {'p99':>8} {'mean':>8}")
    print("-" * 70)

    for name in TEST_CASES:
        for label, res in [("Neo4j", neo4j_results[name]),
                           ("PG   ", pg_results[name])]:
            print(f"{name:<18} {label:<10} {res['verdict']:<8} "
                  f"{res['p50']:>8} {res['p95']:>8} {res['p99']:>8} "
                  f"{res['mean']:>8}")
        print()

    # ── Guardar JSON para la Sesión 4 (gráficas) ─────────────────────────
    output = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "iterations": ITERATIONS,
        "neo4j": neo4j_results,
        "postgres": pg_results,
    }
    with open("benchmark/results/benchmark_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n✓ Resultados guardados en benchmark/results/benchmark_results.json")


if __name__ == "__main__":
    asyncio.run(main())
