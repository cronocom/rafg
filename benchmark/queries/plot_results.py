"""
RAGF Benchmark — Visualizaciones
Genera 3 gráficas publicables desde los resultados JSON
"""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Colores AgentSafe ─────────────────────────────────────────────────────────
NAVY  = "#0D1B6E"
RED   = "#C0001A"
GRAY  = "#888888"
LGRAY = "#F4F4F6"

# ── Cargar datos ──────────────────────────────────────────────────────────────
with open("benchmark/results/benchmark_results.json") as f:
    base = json.load(f)

with open("benchmark/results/scale_benchmark_results.json") as f:
    scale = json.load(f)

# ── Figura 1: Latencia baseline p50/p95 por query ────────────────────────────
fig, ax = plt.subplots(figsize=(11, 5.5))
fig.patch.set_facecolor('white')

queries   = ["q1_simple", "q2_medium", "q3_complex", "q4_deny", "q5_hallucin"]
labels    = ["Q1\nExistence\n(1 reg)", "Q2\nPayment\n(1 reg+2c)", 
             "Q3\nFraud Override\n(3 regs+2c)", "Q4\nAMM Deny\n(level insuf.)", 
             "Q5\nHallucination\n(verb ∉ ontology)"]

x     = np.arange(len(queries))
width = 0.18

neo4j_p50 = [base["neo4j"][q]["p50"] for q in queries]
neo4j_p95 = [base["neo4j"][q]["p95"] for q in queries]
pg_p50    = [base["postgres"][q]["p50"] for q in queries]
pg_p95    = [base["postgres"][q]["p95"] for q in queries]

b1 = ax.bar(x - width*1.5, neo4j_p50, width, color=NAVY,  label="Neo4j p50",  zorder=3)
b2 = ax.bar(x - width*0.5, neo4j_p95, width, color=NAVY,  label="Neo4j p95",  alpha=0.5, zorder=3)
b3 = ax.bar(x + width*0.5, pg_p50,    width, color=RED,   label="PG p50",     zorder=3)
b4 = ax.bar(x + width*1.5, pg_p95,    width, color=RED,   label="PG p95",     alpha=0.5, zorder=3)

# Línea límite RAGF (200ms)
ax.axhline(y=30, color="orange", linestyle="--", linewidth=1.2,
           label="RAGF gate limit (30ms)", zorder=4)

ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=9)
ax.set_ylabel("Latency (ms)", fontsize=11)
ax.set_title("Figure 1 — Semantic Validation Latency: Neo4j vs PostgreSQL\n"
             "PSD2 Ontology baseline (17 verbs, 7 regulations) | 1,000 iterations",
             fontsize=11, fontweight='bold', pad=12)
ax.set_ylim(0, 12)
ax.legend(fontsize=9, loc="upper left")
ax.yaxis.grid(True, alpha=0.3, zorder=0)
ax.set_facecolor(LGRAY)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

# Anotar ratios
for i, q in enumerate(queries):
    ratio = round(base["neo4j"][q]["p50"] / base["postgres"][q]["p50"], 1)
    ax.annotate(f"{ratio}x", xy=(x[i], max(neo4j_p50[i], pg_p50[i]) + 0.3),
                ha='center', fontsize=8, color=GRAY, fontweight='bold')

plt.tight_layout()
plt.savefig("benchmark/results/fig1_baseline_latency.png", dpi=150, bbox_inches='tight')
plt.close()
print("✓ fig1_baseline_latency.png")


# ── Figura 2: Escala — Neo4j vs PG p50 por número de regulaciones ────────────
fig, ax = plt.subplots(figsize=(10, 5.5))
fig.patch.set_facecolor('white')

# Datos combinados baseline + escala organizados por n_regs
data_points = []

# Baseline — n_regs hardcoded por diseño de la ontología
baseline_regs = {"q1_simple": 1, "q2_medium": 1,
                 "q3_complex": 3, "q4_deny": 1, "q5_hallucin": 0}
for q in queries:
    data_points.append({
        "n_regs":    baseline_regs[q],
        "neo4j_p50": base["neo4j"][q]["p50"],
        "pg_p50":    base["postgres"][q]["p50"],
        "dataset":   "baseline"
    })

# Escala
for verb_name, nr in scale["neo4j"].items():
    if verb_name in scale["postgres"]:
        data_points.append({
            "n_regs":    nr["n_regs"],
            "neo4j_p50": nr["p50"],
            "pg_p50":    scale["postgres"][verb_name]["p50"],
            "dataset":   "scale"
        })

# Scatter plot
for dp in data_points:
    color   = NAVY if dp["dataset"] == "scale" else "cyan"
    pg_col  = RED  if dp["dataset"] == "scale" else "salmon"
    marker  = "o"  if dp["dataset"] == "scale" else "s"
    ax.scatter(dp["n_regs"], dp["neo4j_p50"], color=NAVY, marker=marker,
               s=80, alpha=0.8, zorder=3)
    ax.scatter(dp["n_regs"], dp["pg_p50"],    color=RED,  marker=marker,
               s=80, alpha=0.8, zorder=3)

ax.axhline(y=30, color="orange", linestyle="--", linewidth=1.2,
           label="RAGF gate limit (30ms)")

neo4j_patch = mpatches.Patch(color=NAVY, label="Neo4j p50")
pg_patch    = mpatches.Patch(color=RED,  label="PostgreSQL p50")
ax.legend(handles=[neo4j_patch, pg_patch], fontsize=10)

ax.set_xlabel("Number of regulations per verb", fontsize=11)
ax.set_ylabel("Latency p50 (ms)", fontsize=11)
ax.set_title("Figure 2 — Latency vs Regulatory Complexity\n"
             "Baseline (17 verbs) + Scale (500 verbs, 200 regs) | both databases sub-30ms",
             fontsize=11, fontweight='bold', pad=12)
ax.set_ylim(0, 10)
ax.set_xlim(-0.3, 5)
ax.yaxis.grid(True, alpha=0.3)
ax.set_facecolor(LGRAY)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

plt.tight_layout()
plt.savefig("benchmark/results/fig2_scale_complexity.png", dpi=150, bbox_inches='tight')
plt.close()
print("✓ fig2_scale_complexity.png")


# ── Figura 3: Tabla resumen — la más publicable ───────────────────────────────
fig, ax = plt.subplots(figsize=(12, 4.5))
fig.patch.set_facecolor('white')
ax.axis('off')

table_data = [
    ["Query", "Description", "Neo4j p50", "Neo4j p95", "PG p50", "PG p95", "Ratio\n(PG/Neo4j)", "Verdict"],
]

descs = {
    "q1_simple":   "Existence check (1 reg)",
    "q2_medium":   "Payment init (1 reg + 2c)",
    "q3_complex":  "Fraud override (3 regs + 2c)",
    "q4_deny":     "Insufficient AMM → DENY",
    "q5_hallucin": "Hallucinated verb → DENY",
}

for q in queries:
    nr    = base["neo4j"][q]
    pg    = base["postgres"][q]
    ratio = round(nr["p50"] / pg["p50"], 1)
    table_data.append([
        q,
        descs[q],
        f"{nr['p50']} ms",
        f"{nr['p95']} ms",
        f"{pg['p50']} ms",
        f"{pg['p95']} ms",
        f"PG {ratio}x faster",
        nr["verdict"],
    ])

table = ax.table(
    cellText=table_data[1:],
    colLabels=table_data[0],
    cellLoc='center',
    loc='center',
    bbox=[0, 0, 1, 1]
)

table.auto_set_font_size(False)
table.set_fontsize(9)

# Header styling
for j in range(len(table_data[0])):
    table[0, j].set_facecolor(NAVY)
    table[0, j].set_text_props(color='white', fontweight='bold')

# Row styling
for i in range(1, len(table_data)):
    for j in range(len(table_data[0])):
        table[i, j].set_facecolor(LGRAY if i % 2 == 0 else 'white')
        # Colorear veredictos
        if j == 7:
            verdict = table_data[i][j]
            table[i, j].set_text_props(
                color='green' if verdict == "ALLOW" else RED,
                fontweight='bold'
            )

ax.set_title("Figure 3 — Summary Table: RAGF Validation Gate Latency Benchmark\n"
             "Neo4j vs PostgreSQL | PSD2 Ontology | 1,000 iterations | Local MacBook",
             fontsize=11, fontweight='bold', pad=20)

plt.tight_layout()
plt.savefig("benchmark/results/fig3_summary_table.png", dpi=150, bbox_inches='tight')
plt.close()
print("✓ fig3_summary_table.png")

print("\n✓ Todas las figuras generadas en benchmark/results/")
