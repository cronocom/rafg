"""
RAGF Benchmark — Neo4j Ontology Loader
Carga la ontología PSD2 como grafo de propiedades
Usa prefijo BM_ en labels para no pisar datos existentes
"""
import asyncio
import time
from neo4j import AsyncGraphDatabase
from .psd2_data import VERBS, REGULATIONS, CONSTRAINTS

NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "ragf2026"


async def load_ontology() -> dict:
    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    stats = {"nodes": 0, "relationships": 0, "duration_ms": 0}
    t0 = time.perf_counter()

    async with driver.session() as session:

        # 1. Limpiar datos previos del benchmark (prefijo BM_)
        await session.run("MATCH (n:BM_Verb) DETACH DELETE n")
        await session.run("MATCH (n:BM_Regulation) DETACH DELETE n")
        await session.run("MATCH (n:BM_Constraint) DETACH DELETE n")
        await session.run("MATCH (n:BM_Domain) DETACH DELETE n")

        # 2. Crear índices para lookup eficiente
        await session.run(
            "CREATE INDEX bm_verb_name IF NOT EXISTS "
            "FOR (v:BM_Verb) ON (v.name)"
        )
        await session.run(
            "CREATE INDEX bm_reg_code IF NOT EXISTS "
            "FOR (r:BM_Regulation) ON (r.code)"
        )

        # 3. Crear dominio
        await session.run(
            "CREATE (:BM_Domain {name: 'fintech', version: '1.0', jurisdiction: 'EU'})"
        )
        stats["nodes"] += 1

        # 4. Crear regulaciones
        for reg in REGULATIONS:
            await session.run(
                "CREATE (:BM_Regulation {code: $code, title: $title, authority: $authority})",
                code=reg["code"], title=reg["title"], authority=reg["authority"]
            )
            stats["nodes"] += 1

        # 5. Crear constraints
        for c in CONSTRAINTS:
            await session.run(
                "CREATE (:BM_Constraint {cid: $cid, predicate: $predicate, unit: $unit})",
                cid=c["id"], predicate=c["predicate"], unit=c["unit"]
            )
            stats["nodes"] += 1

        # 6. Crear verbos + relaciones
        for verb in VERBS:
            await session.run(
                """
                CREATE (v:BM_Verb {
                    name: $name,
                    description: $description,
                    min_amm_level: $min_amm_level
                })
                """,
                name=verb["name"],
                description=verb["description"],
                min_amm_level=verb["min_amm_level"]
            )
            stats["nodes"] += 1

            # BELONGS_TO domain
            await session.run(
                """
                MATCH (v:BM_Verb {name: $name}), (d:BM_Domain {name: 'fintech'})
                CREATE (v)-[:BM_BELONGS_TO]->(d)
                """,
                name=verb["name"]
            )
            stats["relationships"] += 1

            # MUST_SATISFY regulations
            for reg_code in verb["regulations"]:
                await session.run(
                    """
                    MATCH (v:BM_Verb {name: $name}), (r:BM_Regulation {code: $code})
                    CREATE (v)-[:BM_MUST_SATISFY]->(r)
                    """,
                    name=verb["name"], code=reg_code
                )
                stats["relationships"] += 1

            # REQUIRES_CONSTRAINT
            for cid in verb["constraints"]:
                await session.run(
                    """
                    MATCH (v:BM_Verb {name: $name}), (c:BM_Constraint {cid: $cid})
                    CREATE (v)-[:BM_REQUIRES_CONSTRAINT]->(c)
                    """,
                    name=verb["name"], cid=cid
                )
                stats["relationships"] += 1

    stats["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    await driver.close()
    return stats


if __name__ == "__main__":
    result = asyncio.run(load_ontology())
    print(f"✓ Ontología cargada en Neo4j")
    print(f"  Nodos:         {result['nodes']}")
    print(f"  Relaciones:    {result['relationships']}")
    print(f"  Tiempo:        {result['duration_ms']} ms")
