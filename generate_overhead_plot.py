#!/usr/bin/env python3

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

CSV_FILE = Path("latency_comparison.csv")
OUTPUT_DIR = Path("figures")
OUTPUT_DIR.mkdir(exist_ok=True)

df = pd.read_csv(CSV_FILE, comment="#")

# Limpiar columna Overhead (%)
df["Overhead (%)"] = (
    df["Overhead (%)"]
    .str.replace("+", "", regex=False)
    .str.replace("%", "", regex=False)
    .astype(float)
)

plt.figure(figsize=(8, 4))
df.set_index("Metric")["Overhead (%)"].plot(kind="bar")

plt.title("Latency Overhead v2 vs v1")
plt.ylabel("Overhead (%)")
plt.tight_layout()

output_path = OUTPUT_DIR / "latency_overhead.png"
plt.savefig(output_path, dpi=300)

print(f"✅ Graph generated: {output_path}")
