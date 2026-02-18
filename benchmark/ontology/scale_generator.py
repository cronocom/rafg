"""
RAGF Benchmark — Scale Data Generator
Genera ontología sintética grande para test de escalabilidad
500 verbos, 200 regulaciones, 500 constraints
Simula un entorno multi-jurisdicción real (EU + US + UK + APAC)
"""
import random
import asyncio
import asyncpg
from neo4j import AsyncGraphDatabase

NEO4J_URI  = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "ragf2026")
PG_DSN     = "postgresql://ragf:ragf_benchmark_2026@127.0.0.1:5433/ragf_ontology"

JURISDICTIONS = ["EU", "US", "UK", "APAC", "LATAM"]
AUTHORITIES   = ["EBA", "FCA", "SEC", "MAS", "FATF", "EDPB", "OCC", "FINMA"]
DOMAINS       = ["fintech", "banking", "insurance", "capital_markets", "crypto"]

VERB_PREFIXES = [
    "initiate", "approve", "cancel", "review", "escalate",
    "override", "freeze", "unfreeze", "flag", "clear",
    "export", "import", "validate", "reject", "suspend",
    "restore", "audit", "report", "transfer", "query"
]
VERB_SUFFIXES = [
    "payment", "transaction", "account", "transfer", "alert",
    "position", "order", "limit", "mandate", "contract",
    "report", "record", "profile", "session", "credential",
    "balance", "threshold", "policy", "exemption", "flag"
]

random.seed(42)  # reproducible


def generate_scale_data(n_verbs=500, n_regs=200, n_constraints=50):
    # Regulaciones
    regulations = []
    for i in range(n_regs):
        auth = random.choice(AUTHORITIES)
        jur  = random.choice(JURISDICTIONS)
        regulations.append({
            "code":      f"SCALE-{auth}-{jur}-{i:04d}",
            "title":     f"Regulation {i} ({auth}/{jur})",
            "authority": auth,
        })

    # Constraints
    constraints = []
    for i in range(n_constraints):
        constraints.append({
            "id":        f"sc{i}",
            "predicate": f"param_{i} <= {random.randint(100, 100000)}",
            "unit":      random.choice(["EUR", "USD", "boolean", "float", "integer"]),
        })

    # Verbos — combinaciones únicas
    verb_names = set()
    while len(verb_names) < n_verbs:
        name = f"{random.choice(VERB_PREFIXES)}_{random.choice(VERB_SUFFIXES)}_{len(verb_names):03d}"
        verb_names.add(name)

    verbs = []
    for name in verb_names:
        n_regs_for_verb = random.choices([1, 2, 3, 4], weights=[40, 35, 20, 5])[0]
        n_cons_for_verb = random.choices([0, 1, 2, 3], weights=[30, 40, 20, 10])[0]
        verbs.append({
            "name":          name,
            "description":   f"Scale test verb: {name}",
            "min_amm_level": random.randint(1, 5),
            "domain":        random.choice(DOMAINS),
            "regulations":   [r["code"] for r in random.sample(regulations, n_regs_for_verb)],
            "constraints":   [c["id"]   for c in random.sample(constraints, n_cons_for_verb)],
        })

    return verbs, regulations, constraints


async def load_scale_neo4j(verbs, regulations, constraints):
    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    async with driver.session() as s:
        # Limpiar datos de escala previos
        await s.run("MATCH (n:SC_Verb) DETACH DELETE n")
        await s.run("MATCH (n:SC_Regulation) DETACH DELETE n")
        await s.run("MATCH (n:SC_Constraint) DETACH DELETE n")

        # Índices
        await s.run("CREATE INDEX sc_verb_name IF NOT EXISTS FOR (v:SC_Verb) ON (v.name)")
        await s.run("CREATE INDEX sc_reg_code  IF NOT EXISTS FOR (r:SC_Regulation) ON (r.code)")

        # Regulaciones en batch
        await s.run("""
            UNWIND $regs AS r
            CREATE (:SC_Regulation {code: r.code, title: r.title, authority: r.authority})
        """, regs=regulations)

        # Constraints en batch
        await s.run("""
            UNWIND $cons AS c
            CREATE (:SC_Constraint {cid: c.id, predicate: c.predicate, unit: c.unit})
        """, cons=constraints)

        # Verbos en batch
        await s.run("""
            UNWIND $verbs AS v
            CREATE (:SC_Verb {
                name: v.name,
                description: v.description,
                min_amm_level: v.min_amm_level,
                domain: v.domain
            })
        """, verbs=verbs)

        # Relaciones verbo → regulación
        for verb in verbs:
            if verb["regulations"]:
                await s.run("""
                    MATCH (v:SC_Verb {name: $name})
                    UNWIND $regs AS code
                    MATCH (r:SC_Regulation {code: code})
                    CREATE (v)-[:SC_MUST_SATISFY]->(r)
                """, name=verb["name"], regs=verb["regulations"])

            if verb["constraints"]:
                await s.run("""
                    MATCH (v:SC_Verb {name: $name})
                    UNWIND $cons AS cid
                    MATCH (c:SC_Constraint {cid: cid})
                    CREATE (v)-[:SC_REQUIRES_CONSTRAINT]->(c)
                """, name=verb["name"], cons=verb["constraints"])

    await driver.close()
    print(f"  Neo4j scale: {len(verbs)} verbos, {len(regulations)} regs, {len(constraints)} constraints")


async def load_scale_postgres(verbs, regulations, constraints):
    conn = await asyncpg.connect(PG_DSN)

    await conn.execute("""
        DROP TABLE IF EXISTS sc_verb_constraints CASCADE;
        DROP TABLE IF EXISTS sc_verb_regulations CASCADE;
        DROP TABLE IF EXISTS sc_verbs CASCADE;
        DROP TABLE IF EXISTS sc_regulations CASCADE;
        DROP TABLE IF EXISTS sc_constraints CASCADE;
    """)

    await conn.execute("""
        CREATE TABLE sc_regulations (
            id        SERIAL PRIMARY KEY,
            code      TEXT NOT NULL UNIQUE,
            title     TEXT,
            authority TEXT
        );
        CREATE TABLE sc_constraints (
            id        SERIAL PRIMARY KEY,
            cid       TEXT NOT NULL UNIQUE,
            predicate TEXT,
            unit      TEXT
        );
        CREATE TABLE sc_verbs (
            id            SERIAL PRIMARY KEY,
            name          TEXT NOT NULL UNIQUE,
            description   TEXT,
            min_amm_level INTEGER NOT NULL,
            domain        TEXT
        );
        CREATE TABLE sc_verb_regulations (
            verb_id INTEGER REFERENCES sc_verbs(id),
            reg_id  INTEGER REFERENCES sc_regulations(id),
            PRIMARY KEY (verb_id, reg_id)
        );
        CREATE TABLE sc_verb_constraints (
            verb_id       INTEGER REFERENCES sc_verbs(id),
            constraint_id INTEGER REFERENCES sc_constraints(id),
            PRIMARY KEY (verb_id, constraint_id)
        );
        CREATE INDEX idx_sc_verb_name  ON sc_verbs(name);
        CREATE INDEX idx_sc_verb_amm   ON sc_verbs(min_amm_level);
        CREATE INDEX idx_sc_reg_code   ON sc_regulations(code);
        CREATE INDEX idx_sc_vr_verb    ON sc_verb_regulations(verb_id);
        CREATE INDEX idx_sc_vc_verb    ON sc_verb_constraints(verb_id);
    """)

    # Insertar regulaciones
    await conn.executemany(
        "INSERT INTO sc_regulations(code, title, authority) VALUES($1,$2,$3)",
        [(r["code"], r["title"], r["authority"]) for r in regulations]
    )

    # Insertar constraints
    await conn.executemany(
        "INSERT INTO sc_constraints(cid, predicate, unit) VALUES($1,$2,$3)",
        [(c["id"], c["predicate"], c["unit"]) for c in constraints]
    )

    # Insertar verbos y relaciones
    for verb in verbs:
        verb_id = await conn.fetchval(
            "INSERT INTO sc_verbs(name, description, min_amm_level, domain) "
            "VALUES($1,$2,$3,$4) RETURNING id",
            verb["name"], verb["description"], verb["min_amm_level"], verb["domain"]
        )
        for reg_code in verb["regulations"]:
            await conn.execute(
                "INSERT INTO sc_verb_regulations(verb_id, reg_id) "
                "VALUES($1,(SELECT id FROM sc_regulations WHERE code=$2))",
                verb_id, reg_code
            )
        for cid in verb["constraints"]:
            await conn.execute(
                "INSERT INTO sc_verb_constraints(verb_id, constraint_id) "
                "VALUES($1,(SELECT id FROM sc_constraints WHERE cid=$2))",
                verb_id, cid
            )

    await conn.close()
    print(f"  PG scale:    {len(verbs)} verbos, {len(regulations)} regs, {len(constraints)} constraints")


async def main():
    print("► Generando datos de escala (seed=42, reproducible)...")
    verbs, regs, cons = generate_scale_data(500, 200, 50)
    print(f"  Generados: {len(verbs)} verbos, {len(regs)} regs, {len(cons)} constraints")

    print("\n► Cargando en Neo4j...")
    await load_scale_neo4j(verbs, regs, cons)

    print("\n► Cargando en PostgreSQL...")
    await load_scale_postgres(verbs, regs, cons)

    print("\n✓ Datos de escala listos en ambas bases")
    # Guardar algunos verbos de prueba para el benchmark
    import json, random
    sample = random.sample(verbs, 5)
    with open("benchmark/results/scale_test_verbs.json", "w") as f:
        json.dump(sample, f, indent=2)
    print(f"  Verbos de prueba guardados en benchmark/results/scale_test_verbs.json")


if __name__ == "__main__":
    asyncio.run(main())
