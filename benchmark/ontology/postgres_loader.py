"""
RAGF Benchmark — PostgreSQL Ontology Loader
Schema relacional equivalente al grafo Neo4j
Índices optimizados para darle a Postgres su mejor oportunidad
"""
import asyncio
import asyncpg
import time
from .psd2_data import VERBS, REGULATIONS, CONSTRAINTS

PG_DSN = "postgresql://ragf:ragf_benchmark_2026@127.0.0.1:5433/ragf_ontology"


async def load_ontology() -> dict:
    conn = await asyncpg.connect(PG_DSN)
    stats = {"rows": 0, "duration_ms": 0}
    t0 = time.perf_counter()

    # 1. Schema
    await conn.execute("""
        DROP TABLE IF EXISTS bm_verb_constraints CASCADE;
        DROP TABLE IF EXISTS bm_verb_regulations CASCADE;
        DROP TABLE IF EXISTS bm_verbs CASCADE;
        DROP TABLE IF EXISTS bm_regulations CASCADE;
        DROP TABLE IF EXISTS bm_constraints CASCADE;
        DROP TABLE IF EXISTS bm_domains CASCADE;
    """)

    await conn.execute("""
        CREATE TABLE bm_domains (
            id      SERIAL PRIMARY KEY,
            name    TEXT NOT NULL UNIQUE,
            version TEXT,
            jurisdiction TEXT
        );

        CREATE TABLE bm_regulations (
            id        SERIAL PRIMARY KEY,
            code      TEXT NOT NULL UNIQUE,
            title     TEXT,
            authority TEXT
        );

        CREATE TABLE bm_constraints (
            id        SERIAL PRIMARY KEY,
            cid       TEXT NOT NULL UNIQUE,
            predicate TEXT,
            unit      TEXT
        );

        CREATE TABLE bm_verbs (
            id            SERIAL PRIMARY KEY,
            name          TEXT NOT NULL UNIQUE,
            description   TEXT,
            min_amm_level INTEGER NOT NULL,
            domain_id     INTEGER REFERENCES bm_domains(id)
        );

        CREATE TABLE bm_verb_regulations (
            verb_id INTEGER REFERENCES bm_verbs(id),
            reg_id  INTEGER REFERENCES bm_regulations(id),
            PRIMARY KEY (verb_id, reg_id)
        );

        CREATE TABLE bm_verb_constraints (
            verb_id        INTEGER REFERENCES bm_verbs(id),
            constraint_id  INTEGER REFERENCES bm_constraints(id),
            PRIMARY KEY (verb_id, constraint_id)
        );
    """)

    # 2. Índices — Postgres con su mejor armadura
    await conn.execute("""
        CREATE INDEX idx_bm_verbs_name        ON bm_verbs(name);
        CREATE INDEX idx_bm_verbs_amm         ON bm_verbs(min_amm_level);
        CREATE INDEX idx_bm_regs_code         ON bm_regulations(code);
        CREATE INDEX idx_bm_vr_verb_id        ON bm_verb_regulations(verb_id);
        CREATE INDEX idx_bm_vr_reg_id         ON bm_verb_regulations(reg_id);
        CREATE INDEX idx_bm_vc_verb_id        ON bm_verb_constraints(verb_id);
    """)

    # 3. Insertar datos
    await conn.execute(
        "INSERT INTO bm_domains(name, version, jurisdiction) VALUES($1,$2,$3)",
        "fintech", "1.0", "EU"
    )
    stats["rows"] += 1

    for reg in REGULATIONS:
        await conn.execute(
            "INSERT INTO bm_regulations(code, title, authority) VALUES($1,$2,$3)",
            reg["code"], reg["title"], reg["authority"]
        )
        stats["rows"] += 1

    for c in CONSTRAINTS:
        await conn.execute(
            "INSERT INTO bm_constraints(cid, predicate, unit) VALUES($1,$2,$3)",
            c["id"], c["predicate"], c["unit"]
        )
        stats["rows"] += 1

    for verb in VERBS:
        verb_id = await conn.fetchval(
            """
            INSERT INTO bm_verbs(name, description, min_amm_level, domain_id)
            VALUES($1, $2, $3, (SELECT id FROM bm_domains WHERE name='fintech'))
            RETURNING id
            """,
            verb["name"], verb["description"], verb["min_amm_level"]
        )
        stats["rows"] += 1

        for reg_code in verb["regulations"]:
            await conn.execute(
                """
                INSERT INTO bm_verb_regulations(verb_id, reg_id)
                VALUES($1, (SELECT id FROM bm_regulations WHERE code=$2))
                """,
                verb_id, reg_code
            )
            stats["rows"] += 1

        for cid in verb["constraints"]:
            await conn.execute(
                """
                INSERT INTO bm_verb_constraints(verb_id, constraint_id)
                VALUES($1, (SELECT id FROM bm_constraints WHERE cid=$2))
                """,
                verb_id, cid
            )
            stats["rows"] += 1

    stats["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    await conn.close()
    return stats


if __name__ == "__main__":
    result = asyncio.run(load_ontology())
    print(f"✓ Ontología cargada en PostgreSQL")
    print(f"  Filas totales: {result['rows']}")
    print(f"  Tiempo:        {result['duration_ms']} ms")
