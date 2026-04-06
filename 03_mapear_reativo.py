# 03_mapear_reativo.py
# Mapeia o perfil de potência reativa em todos os barramentos MT
# para identificar onde um capacitor seria tecnicamente indicado

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

from dss import dss

import json
with open(HERE / "parametros.json", "r") as f:
    config = json.load(f)
MASTER = str(HERE / config["caminhos"]["dss_file"])

print("\n" + "="*70)
print("[03.07] MAPEAMENTO DE DEMANDA REATIVA — REDE MT CRELUZ")
print("="*70)

# Carrega e roda 24h
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"

circuit = dss.ActiveCircuit

# Acumula Q por linha ao longo de 24h
q_max_linha = {}   # {nome_linha: q_max_kvar}
q_medio_linha = {} # {nome_linha: q_medio_kvar}
p_max_linha = {}

circuit.Solution.dblHour = 0.0
for h in range(24):
    circuit.Solution.Solve()

    circuit.SetActiveClass("Line")
    lines = circuit.Lines
    idx = lines.First
    while idx > 0:
        if not lines.IsSwitch and not lines.Name.lower().startswith("resist"):
            nome = lines.Name
            circuit.SetActiveElement(f"Line.{nome}")
            powers = circuit.ActiveCktElement.Powers
            n = circuit.ActiveCktElement.NumPhases
            if len(powers) >= n * 2:
                p = abs(sum(powers[0:n*2:2]))
                q = abs(sum(powers[1:n*2+1:2]))

                if nome not in q_max_linha:
                    q_max_linha[nome]   = 0.0
                    q_medio_linha[nome] = 0.0
                    p_max_linha[nome]   = 0.0

                q_max_linha[nome]    = max(q_max_linha[nome], q)
                q_medio_linha[nome] += q / 24.0
                p_max_linha[nome]    = max(p_max_linha[nome], p)
        idx = lines.Next

# Filtra linhas com Q médio relevante (> 10 kvar) e que não são ramais BT
print(f"\nLinhas MT com demanda reativa significativa (Q médio > 10 kvar):")
print(f"  {'Linha':<25} {'Q médio':>10} {'Q máx':>10} {'P máx':>10} {'Bus1':<15} {'Bus2':<15}")
print(f"  {'-'*90}")

candidatos = []
circuit.SetActiveClass("Line")
lines = circuit.Lines
idx = lines.First
linha_info = {}
while idx > 0:
    nome = lines.Name
    # Só linhas MT (prefixo smt_ ou sbt_ com kV > 1)
    b1 = lines.Bus1.split(".")[0]
    circuit.SetActiveBus(b1)
    kv = circuit.ActiveBus.kVBase
    if kv > 1.0 and nome in q_medio_linha:
        linha_info[nome] = {"bus1": b1, "bus2": lines.Bus2.split(".")[0], "kv": kv}
    idx = lines.Next

for nome, q_med in sorted(q_medio_linha.items(), key=lambda x: x[1], reverse=True):
    if q_med > 10 and nome in linha_info:
        info = linha_info[nome]
        candidatos.append({
            "nome": nome,
            "bus1": info["bus1"],
            "bus2": info["bus2"],
            "q_medio": q_med,
            "q_max": q_max_linha[nome],
            "p_max": p_max_linha[nome],
        })
        print(f"  {nome:<25} {q_med:>10.1f} {q_max_linha[nome]:>10.1f} {p_max_linha[nome]:>10.1f} {info['bus1']:<15} {info['bus2']:<15}")

if not candidatos:
    print("  Nenhuma linha MT com Q médio > 10 kvar encontrada.")
    print("\n  Verificando com limiar menor (> 2 kvar):")
    for nome, q_med in sorted(q_medio_linha.items(), key=lambda x: x[1], reverse=True)[:15]:
        if nome in linha_info:
            info = linha_info[nome]
            print(f"  {nome:<25} Q_med={q_med:>8.2f} Q_max={q_max_linha[nome]:>8.2f} kvar")

print(f"\n{'='*70}")
print("[03.08] ANÁLISE DO FATOR DE POTÊNCIA GLOBAL DA REDE")
print(f"{'='*70}")

# Roda 24h completo e verifica fp global
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=24"
circuit.Solution.Solve()

p_total = circuit.Losses[0] / 1000.0
losses_q = circuit.Losses[1] / 1000.0

# Lê do medidor principal
meters = circuit.Meters
idx = meters.First
while idx > 0:
    if "segmmt" in meters.Name.lower() or idx == 1:
        regs = list(meters.RegisterValues)
        if len(regs) > 1:
            e_kwh  = regs[0]
            e_kvarh = regs[1]
            fp_medio = e_kwh / (e_kwh**2 + e_kvarh**2)**0.5 if (e_kwh**2 + e_kvarh**2) > 0 else 0
            print(f"\nMedidor: {meters.Name}")
            print(f"  Energia ativa  : {e_kwh:.1f} kWh/dia")
            print(f"  Energia reativa: {e_kvarh:.1f} kvarh/dia")
            print(f"  FP médio       : {fp_medio:.4f}")
            if fp_medio > 0.95:
                print(f"  >>> FP > 0,95 — rede bem compensada, capacitor não indicado globalmente")
            elif fp_medio > 0.92:
                print(f"  >>> FP entre 0,92 e 0,95 — compensação marginal pode ser benéfica")
            else:
                print(f"  >>> FP < 0,92 — compensação reativa INDICADA")
    idx = meters.Next

print(f"\n{'='*70}")
print("CONCLUSÃO")
print(f"{'='*70}")
if candidatos:
    melhor = candidatos[0]
    print(f"\nBarramento mais indicado para capacitor: {melhor['bus2']}")
    print(f"  Via linha: {melhor['nome']}")
    print(f"  Q médio na linha: {melhor['q_medio']:.1f} kvar")
    print(f"  Q máximo na linha: {melhor['q_max']:.1f} kvar")
    print(f"  Capacitor sugerido: {int(melhor['q_medio']*0.8/100)*100} kvar (80% da demanda média)")
else:
    print("\nNenhum ponto da rede MT apresenta déficit reativo significativo.")
    print("A presença de GD fotovoltaica (521 kW, fp=0,92) já compensa")
    print("a demanda reativa do alimentador. Capacitores não são indicados.")
