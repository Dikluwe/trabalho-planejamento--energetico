# analisar_linha.py
# Analisa a linha rbt_632607 — carregamento, consumidores e horizonte

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pandas as pd
import Main as professor
from dss import dss

MASTER     = str(HERE / "Master.dss")
LINHA_ALVO = "rbt_632607"
CRESCIMENTO = 0.10
LIMITE_PCT  = 100.0
ANOS_MAX    = 10

# ---------------------------------------------------------------------------
# 1. Dados estáticos da linha via OpenDSS
# ---------------------------------------------------------------------------
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
circuit = dss.ActiveCircuit

circuit.SetActiveClass("Line")
lines = circuit.Lines
lines.Name = LINHA_ALVO
circuit.SetActiveElement(f"Line.{LINHA_ALVO}")

bus1     = lines.Bus1.split(".")[0].lower()
bus2     = lines.Bus2.split(".")[0].lower()
fases    = lines.Phases
comprimento = lines.Length
normamps = lines.NormAmps
linecode = lines.LineCode

print(f"\n{'='*60}")
print(f"ANÁLISE DA LINHA: {LINHA_ALVO.upper()}")
print(f"{'='*60}")
print(f"Bus1        : {bus1}")
print(f"Bus2        : {bus2}")
print(f"Fases       : {fases}")
print(f"Comprimento : {comprimento*1000:.1f} m")
print(f"LineCode    : {linecode}")
print(f"NormAmps    : {normamps:.1f} A")

# ---------------------------------------------------------------------------
# 2. Cargas no barramento de chegada (bus2) e downstream
# ---------------------------------------------------------------------------
# Monta adjacência
adj = {}
idx = lines.First
while idx > 0:
    if not lines.IsSwitch:
        b1 = lines.Bus1.split(".")[0].lower()
        b2 = lines.Bus2.split(".")[0].lower()
        adj.setdefault(b1, []).append(b2)
        adj.setdefault(b2, []).append(b1)
    idx = lines.Next

# BFS a partir de bus2
bus_prim_trafos = set()
trafo_names = list(circuit.Transformers.AllNames)
for tn in trafo_names:
    circuit.SetActiveElement(f"Transformer.{tn}")
    bp = circuit.ActiveCktElement.BusNames[0].split(".")[0].lower()
    bus_prim_trafos.add(bp)

visitados = set([bus2])
fila = [bus2]
while fila:
    atual = fila.pop(0)
    for viz in adj.get(atual, []):
        if viz not in visitados and viz not in bus_prim_trafos:
            visitados.add(viz)
            fila.append(viz)

# Cargas
circuit.SetActiveClass("Load")
loads = circuit.Loads
cargas = []
idx = loads.First
while idx > 0:
    bus_carga = circuit.ActiveCktElement.BusNames[0].split(".")[0].lower()
    if bus_carga in visitados:
        cargas.append({
            "nome": loads.Name,
            "bus": bus_carga,
            "kW": loads.kW,
            "kvar": loads.kvar,
            "kVA": (loads.kW**2 + loads.kvar**2)**0.5,
            "fases": loads.Phases,
        })
    idx = loads.Next

total_kw  = sum(c["kW"]  for c in cargas)
total_kva = sum(c["kVA"] for c in cargas)

print(f"\nCargas downstream:")
print(f"  Quantidade  : {len(cargas)}")
print(f"  P total     : {total_kw:.2f} kW")
print(f"  S total     : {total_kva:.2f} kVA")
print(f"  Carregamento nominal da linha: {100*total_kva/normamps:.1f}% (aprox)")

print(f"\n  {'Nome':<30} {'Bus':<15} {'kW':>8} {'kVA':>8} {'Fases':>6}")
print(f"  {'-'*70}")
for c in sorted(cargas, key=lambda x: x["kVA"], reverse=True):
    print(f"  {c['nome']:<30} {c['bus']:<15} {c['kW']:>8.2f} {c['kVA']:>8.2f} {c['fases']:>6}")

# ---------------------------------------------------------------------------
# 3. Perfil horário de carregamento — lê do CSV já gerado
# ---------------------------------------------------------------------------
csv_path = HERE / "Resultados_ano1" / "LinesLoadingByHour.csv"
if csv_path.exists():
    df_lines = pd.read_csv(csv_path)
    df_linha = df_lines[df_lines["line"] == LINHA_ALVO].sort_values("hour")
    if not df_linha.empty:
        print(f"\nPerfil horário (Ano 1 — carga nominal):")
        print(f"  {'Hora':>5} {'Corrente (A)':>14} {'NormAmps (A)':>13} {'Carregamento':>13}")
        print(f"  {'-'*50}")
        for _, row in df_linha.iterrows():
            flag = " <-- ALERTA" if row["loadingPct"] > 80 else ""
            print(f"  {int(row['hour']):>5} {row['maxCurrentA']:>14.2f} {row['normAmps']:>13.2f} {row['loadingPct']:>12.2f}%{flag}")

# ---------------------------------------------------------------------------
# 4. Horizonte de carregamento da linha
# ---------------------------------------------------------------------------
def rodar_ano_linha(fator: float) -> float:
    solution = professor.InitializeCircuit(MASTER, True)
    dss.Text.Command = f"Set LoadMult={fator}"
    (_, df_l, _, _) = professor.RunDailySimulationAndCollect(
        solution=solution, totalHours=24,
        lowVoltageLimitKv=1.0, lowerVoltageLimitPu=0.95, upperVoltageLimitPu=1.05,
    )
    df_alvo = df_l[df_l["line"] == LINHA_ALVO]
    if df_alvo.empty:
        return 0.0
    return float(df_alvo["loadingPct"].max())

print(f"\nHorizonte de carregamento:")
print(f"  {'Ano':>4} {'Fator':>6} {'Max Carregamento':>18} {'Status':>12}")
print(f"  {'-'*45}")

for ano in range(1, ANOS_MAX + 1):
    fator = 1.0 + CRESCIMENTO * (ano - 1)
    carg = rodar_ano_linha(fator)
    status = "SOBRECARGA" if carg > LIMITE_PCT else "OK"
    flag = " <--" if carg > LIMITE_PCT else ""
    print(f"  {ano:>4}  {fator:>5.2f}  {carg:>16.2f}%  {status:>12}{flag}")
    if carg > LIMITE_PCT * 1.5:
        break

print(f"\n{'='*60}\n")
