#!/usr/bin/env python3

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

CSV_FILE = Path("latency_comparison.csv")
OUTPUT_DIR = Path("figures")
OUTPUT_DIR.mkdir(exist_ok=True)

# Leer CSV ignorando metadata (#)
df = pd.read_csv(CSV_FILE, comment="#")

# Convertir columnas numéricas (quitar "+" y "%")
df["v1.0 (ms)"] = df["v1.0 (ms)"].astype(float)
df["v2.0 (ms)"] = df["v2.0 (ms)"].astype(float)

# Crear gráfico
plt.figure(figsize=(8, 5))
df.set_index("Metric")[["v1.0 (ms)", "v2.0 (ms)"]].plot(kind="bar")

plt.title("RAGF Latency Comparison")
plt.ylabel("Latency (ms)")
plt.xlabel("Percentile")
plt.xticks(rotation=0)
plt.tight_layout()

output_path = OUTPUT_DIR / "latency_comparison.png"
plt.savefig(output_path, dpi=300)

print(f"✅ Graph generated: {output_path}")
