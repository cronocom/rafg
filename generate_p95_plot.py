#!/usr/bin/env python3

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

CSV_FILE = Path("latency_comparison.csv")
OUTPUT_DIR = Path("figures")
OUTPUT_DIR.mkdir(exist_ok=True)

df = pd.read_csv(CSV_FILE, comment="#")

# Filtrar p95
p95 = df[df["Metric"] == "P95"]

v1 = float(p95["v1.0 (ms)"])
v2 = float(p95["v2.0 (ms)"])

plt.figure(figsize=(6, 4))
plt.bar(["v1.0", "v2.0"], [v1, v2])

# Línea objetivo 200ms
plt.axhline(y=200, linestyle="--")

plt.title("RAGF Latency (p95)")
plt.ylabel("Latency (ms)")
plt.tight_layout()

output_path = OUTPUT_DIR / "latency_p95.png"
plt.savefig(output_path, dpi=300)

print(f"✅ Graph generated: {output_path}")
