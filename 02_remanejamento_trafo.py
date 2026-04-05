# remanejamento_trafo.py
# Identifica transformadores subutilizados que poderiam ser substituídos
# por unidades menores, liberando um trafo maior para o trf_6_4910a

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pandas as pd

# Lê o summary já gerado pelo caso base ano 1
csv_path = HERE / "Resultados_ano1" / "TransformerSummary.csv"

if not csv_path.exists():
    print(f"Arquivo não encontrado: {csv_path}")
    print("Rode main_trabalho.py primeiro para gerar os CSVs.")
    sys.exit(1)

df = pd.read_csv(csv_path)

print(f"\n{'='*70}")
print("TRANSFORMADORES DISPONÍVEIS PARA REMANEJAMENTO")
print(f"{'='*70}")

# Transformadores de 45 kVA
df45 = df[df["ratedKva"] == 45.0].sort_values("maxLoadingPct")
print(f"\nTrafos de 45 kVA na rede: {len(df45)}")
if not df45.empty:
    print(df45[["transformer","ratedKva","maxLoadingPct","meanLoadingPct","overloadHours"]].to_string(index=False))

# Transformadores de 30 kVA (mesma classe do problema)
df30 = df[df["ratedKva"] == 30.0].sort_values("maxLoadingPct")
print(f"\nTrafos de 30 kVA na rede: {len(df30)}")
print(df30[["transformer","ratedKva","maxLoadingPct","meanLoadingPct","overloadHours"]].to_string(index=False))

# Todos os trafos ordenados por potência nominal
print(f"\n{'='*70}")
print("INVENTÁRIO COMPLETO POR POTÊNCIA NOMINAL")
print(f"{'='*70}")
resumo = df.groupby("ratedKva").agg(
    quantidade=("transformer","count"),
    max_carregamento_max=("maxLoadingPct","max"),
    media_carregamento_medio=("meanLoadingPct","mean"),
).reset_index().sort_values("ratedKva")
print(resumo.to_string(index=False))

# Candidatos a remanejamento: trafos com carregamento médio < 30%
# e potência >= 45 kVA — poderiam ser substituídos por um menor
print(f"\n{'='*70}")
print("CANDIDATOS A REMANEJAMENTO (meanLoadingPct < 30% e ratedKva >= 45)")
print(f"{'='*70}")
candidatos = df[
    (df["meanLoadingPct"] < 30.0) &
    (df["ratedKva"] >= 45.0)
].sort_values(["ratedKva","meanLoadingPct"])

if candidatos.empty:
    print("Nenhum trafo de 45+ kVA com carregamento médio abaixo de 30%.")
else:
    print(candidatos[["transformer","ratedKva","maxLoadingPct","meanLoadingPct"]].to_string(index=False))
