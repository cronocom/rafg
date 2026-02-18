"""
RAGF Benchmark — Scale Query Comparison
Mismas queries pero sobre el grafo grande (500 verbos, 200 regs)
Compara degradación de latencia Neo4j vs PostgreSQL al escalar
"""
import asyncio
import time
import statistics
import json
from datetime import datetime

import asyncpg
from neo4j import AsyncGraphDatabase

NEO4J_URI  = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "ragf2026")
PG_DSN     = "postgresql://ragf:ragf_benchmark_2026@127.0.0.1:5433/ragf_ontology"

ITERATIONS = 1000

# Cargar verbos de prueba generados (seed=42, reproducible)
with open("benchmark/results/scale_test_verbs.json") as f:
    SCALE_VERBS = json.load(f)

# Añadir caso de alucinación
SCALE_VERBS.append({
    "name": "hallucinated_verb_xyz",
    "min_amm_level": 5,
    "regulations": [],
    "constraints": []
})

# ── Neo4j query sobre tablas SC_ ──────────────────────────────────────────────
NEO4J_SCALE_Q = """
MATCH (v:SC_Verb {name: $verb_name})
WHERE v.min_amm_level <= $amm_level
OPTIONAL MATCH (v)-[:SC_MUST_SATISFY]->(r:SC_Regulation)
OPTIONAL MATCH (v)-[:SC_REQUIRES_CONSTRAINT]->(c:SC_Constraint)
WITH v,
     collect(DISTINCT r.code) AS regulations,
     collect(DISTINCT c.predicate) AS constraints
RETURN
  v.name          AS verb,
  v.min_amm_level AS required_level,
  regulations,
  constraints,
  size(regulations) AS reg_count,
  CASE WHEN size(regulations) > 0 THEN 1.0 ELSE 0.0 END AS coverage
"""

# ── PostgreSQL query sobre tablas SC_ ─────────────────────────────────────────
PG_SCALE_Q = """
SELECT
    v.name                              AS verb,
    v.min_amm_level                     AS required_level,
    $2::integer                         AS agent_level,
    array_agg(DISTINCT r.code)          AS regulations,
    array_agg(DISTINCT c.predicate)     AS constraints,
    count(DISTINCT r.id)::integer       AS reg_count,
    CASE WHEN count(DISTINCT r.id) > 0
         THEN 1.0 ELSE 0.0 END          AS coverage
FROM sc_verbs v
LEFT JOIN sc_verb_regulations vr ON v.id = vr.verb_id
LEFT JOIN sc_regulations r       ON vr.reg_id = r.id
LEFT JOIN sc_verb_constraints vc ON v.id = vc.verb_id
LEFT JOIN sc_constraints c       ON vc.constraint_id = c.id
WHERE v.name = $1::text
  AND v.min_amm_level <= $2::integer
GROUP BY v.name, v.min_amm_level
"""


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


async def bench_neo4j_scale():
    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    results = {}

    async with driver.session() as session:
        for verb in SCALE_VERBS:
            name = verb["name"]
            amm  = verb["min_amm_level"]
            latencies = []

            # warmup
            for _ in range(20):
                await session.run(NEO4J_SCALE_Q, verb_name=name, amm_level=amm)

            for _ in range(ITERATIONS):
                t0 = time.perf_counter()
                result = await session.run(
                    NEO4J_SCALE_Q, verb_name=name, amm_level=amm
                )
                records = await result.data()
                latencies.append((time.perf_counter() - t0) * 1000)

            n_regs = len(verb.get("regulations", []))
            results[name] = {
                "verdict":  "ALLOW" if records else "DENY",
                "n_regs":   n_regs,
                **stats(latencies)
            }
            print(f"  Neo4j [{n_regs} regs] {name[:35]:35s} "
                  f"→ {results[name]['verdict']:5s} "
                  f"p50={results[name]['p50']:.3f}ms "
                  f"p95={results[name]['p95']:.3f}ms")

    await driver.close()
    return results


async def bench_postgres_scale():
    conn = await asyncpg.connect(PG_DSN)
    stmt = await conn.prepare(PG_SCALE_Q)
    results = {}

    for verb in SCALE_VERBS:
        name = verb["name"]
        amm  = verb["min_amm_level"]
        latencies = []

        # warmup
        for _ in range(20):
            await stmt.fetch(name, int(amm))

        for _ in range(ITERATIONS):
            t0 = time.perf_counter()
            records = await stmt.fetch(name, int(amm))
            latencies.append((time.perf_counter() - t0) * 1000)

        n_regs = len(verb.get("regulations", []))
        results[name] = {
            "verdict":  "ALLOW" if records else "DENY",
            "n_regs":   n_regs,
            **stats(latencies)
        }
        print(f"  PG    [{n_regs} regs] {name[:35]:35s} "
              f"→ {results[name]['verdict']:5s} "
              f"p50={results[name]['p50']:.3f}ms "
              f"p95={results[name]['p95']:.3f}ms")

    await conn.close()
    return results


async def main():
    print(f"\n{'='*65}")
    print(f"  RAGF Scale Benchmark — 500 verbos, 200 regulaciones")
    print(f"  Iteraciones: {ITERATIONS} por query | Timestamp: "
          f"{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"{'='*65}\n")

    print("► Neo4j scale benchmark...")
    neo4j_results = await bench_neo4j_scale()

    print("\n► PostgreSQL scale benchmark...")
    pg_results = await bench_postgres_scale()

    # ── Tabla comparativa ─────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  COMPARATIVA DE ESCALA")
    print(f"{'='*65}")
    print(f"{'Verbo':<38} {'Regs':>4}  "
          f"{'Neo4j p50':>10} {'Neo4j p95':>10}  "
          f"{'PG p50':>8} {'PG p95':>8}  {'Ratio p50':>10}")
    print("-" * 95)

    for verb in SCALE_VERBS:
        name = verb["name"]
        nr   = neo4j_results[name]
        pg   = pg_results[name]
        ratio = round(nr["p50"] / pg["p50"], 1) if pg["p50"] > 0 else 0
        print(f"{name[:38]:<38} {nr['n_regs']:>4}  "
              f"{nr['p50']:>10} {nr['p95']:>10}  "
              f"{pg['p50']:>8} {pg['p95']:>8}  "
              f"{'Neo4j '+str(ratio)+'x':>10}")

    # ── Guardar resultados ────────────────────────────────────────────────
    output = {
        "timestamp":  datetime.utcnow().isoformat() + "Z",
        "scale":      {"verbs": 500, "regulations": 200, "constraints": 50},
        "iterations": ITERATIONS,
        "neo4j":      neo4j_results,
        "postgres":   pg_results,
    }
    with open("benchmark/results/scale_benchmark_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n✓ Resultados guardados en "
          f"benchmark/results/scale_benchmark_results.json")


if __name__ == "__main__":
    asyncio.run(main())
