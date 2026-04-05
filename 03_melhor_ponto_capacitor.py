# 03_melhor_ponto_capacitor.py
# Identifica o barramento com maior déficit reativo noturno
# onde um capacitor automático teria benefício mínimo real

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dss import dss

import json
with open(HERE / "parametros.json", "r") as f:
    config = json.load(f)
MASTER = str(HERE / config["caminhos"]["dss_file"])

print("\n" + "="*70)
print("[03.01] ANÁLISE NOTURNA DE REATIVO — MELHOR PONTO PARA CAPACITOR AUTOMÁTICO")
print("="*70)

HORAS_NOTURNAS = list(range(0, 6)) + list(range(19, 24))

# ---------------------------------------------------------------------------
# PASSO 1 — Mapeamento de Q noturno/diurno por linha MT
# ---------------------------------------------------------------------------
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"

circuit = dss.ActiveCircuit

q_noturno = {}
q_diurno  = {}
q_max_noc = {}
bus2_linha = {}

for h in range(24):
    circuit.Solution.Solve()
    circuit.SetActiveClass("Line")
    lines = circuit.Lines
    idx = lines.First
    while idx > 0:
        if not lines.IsSwitch and not lines.Name.lower().startswith("resist"):
            nome = lines.Name
            b1 = lines.Bus1.split(".")[0]
            b2 = lines.Bus2.split(".")[0]
            circuit.SetActiveBus(b1)
            kv = circuit.ActiveBus.kVBase
            if kv > 1.0:
                circuit.SetActiveElement(f"Line.{nome}")
                powers = circuit.ActiveCktElement.Powers
                n = circuit.ActiveCktElement.NumPhases
                if len(powers) >= n * 2:
                    q = abs(sum(powers[1:n*2+1:2]))
                    if nome not in q_noturno:
                        q_noturno[nome] = 0.0
                        q_diurno[nome]  = 0.0
                        q_max_noc[nome] = 0.0
                        bus2_linha[nome] = b2
                    if h in HORAS_NOTURNAS:
                        q_noturno[nome] += q / len(HORAS_NOTURNAS)
                        q_max_noc[nome]  = max(q_max_noc[nome], q)
                    else:
                        q_diurno[nome]  += q / (24 - len(HORAS_NOTURNAS))
        idx = lines.Next

print(f"\nTop 15 linhas MT por Q médio noturno (GD desligada):")
print(f"  {'Linha':<20} {'Q noc médio':>12} {'Q noc máx':>10} {'Q diurno':>10} {'Barramento':>12}")
print(f"  {'-'*70}")

top15 = sorted(q_noturno.items(), key=lambda x: x[1], reverse=True)[:15]
for nome, q_noc in top15:
    print(f"  {nome:<20} {q_noc:>12.1f} {q_max_noc[nome]:>10.1f} {q_diurno.get(nome,0):>10.1f} {bus2_linha.get(nome,'?'):>12}")

melhor_nome  = top15[0][0]
melhor_q     = top15[0][1]
melhor_bus   = bus2_linha[melhor_nome]
melhor_q_max = q_max_noc[melhor_nome]

# Dimensionamento: 40% do Q maximo noturno para evitar overshooting
# Margem ampla de histerese: liga em 60% do Q max, desliga em 25%
cap_kvar   = max(50, int(melhor_q_max * 0.4 / 50) * 50)
cap_kvar   = min(cap_kvar, 600)
onsetting  = int(melhor_q_max * 0.60)
offsetting = int(melhor_q_max * 0.25)

print(f"\n{'='*70}")
print(f"MELHOR CANDIDATO: barramento {melhor_bus} via {melhor_nome}")
print(f"  Q noturno medio : {melhor_q:.1f} kvar")
print(f"  Q noturno maximo: {melhor_q_max:.1f} kvar")
print(f"  Q diurno medio  : {q_diurno[melhor_nome]:.1f} kvar")
print(f"\nDimensionamento (40% do Q max noturno, histerese ampla):")
print(f"  Capacitor  : {cap_kvar} kvar em 23,1 kV")
print(f"  onsetting  : {onsetting} kvar  (liga acima de 60% do Q max noturno)")
print(f"  offsetting : {offsetting} kvar  (desliga abaixo de 25% do Q max noturno)")

# --- ATUALIZAÇÃO DO JSON ---
json_file = HERE / "parametros.json"
with open(json_file, 'r', encoding='utf-8') as f:
    config_data = json.load(f)
config_data["capacitor_alvo"] = {
    "barramento": melhor_bus,
    "linha_referencia": melhor_nome,
    "kvar_calculado": cap_kvar,
    "onsetting_sugerido": onsetting,
    "offsetting_sugerido": offsetting
}
with open(json_file, 'w', encoding='utf-8') as f:
    json.dump(config_data, f, indent=2, ensure_ascii=False)
print(f"\n[✓] Melhor capacitor ('{melhor_bus}', {cap_kvar} kvar) salvo em parametros.json")

# ---------------------------------------------------------------------------
# PASSO 2 — Referencia sem capacitor
# ---------------------------------------------------------------------------
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"

q_ref      = {}
perdas_ref = {}
for h in range(24):
    circuit.Solution.Solve()
    # Perdas ANTES de qualquer SetActiveElement
    perdas_ref[h] = circuit.Losses[0] / 1000.0
    circuit.SetActiveElement(f"Line.{melhor_nome}")
    powers = circuit.ActiveCktElement.Powers
    n = circuit.ActiveCktElement.NumPhases
    q_ref[h] = abs(sum(powers[1:n*2+1:2]))

# ---------------------------------------------------------------------------
# PASSO 3 — Com capacitor automatico
# ---------------------------------------------------------------------------
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"
dss.Text.Command = "Set maxcontroliter=100"
dss.Text.Command = f"New Capacitor.CAPX bus1={melhor_bus} phases=3 kvar={cap_kvar} kv=23.1"
dss.Text.Command = f"New CapControl.CCX element=Line.{melhor_nome} terminal=1 capacitor=CAPX type=kvar onsetting={onsetting} offsetting={offsetting}"

print(f"\n{'='*70}")
print(f"TESTE HORA A HORA — barramento {melhor_bus}")
print(f"  {'Hora':>4} {'Q sem':>9} {'Q com':>9} {'Cap':>5} {'Perd sem':>10} {'Perd com':>10} {'Delta kW':>9}")
print(f"  {'-'*63}")

delta_total      = 0.0
cap_ligado_horas = 0

for h in range(24):
    try:
        circuit.Solution.Solve()
    except Exception:
        pass

    # Perdas totais ANTES de qualquer SetActiveElement
    perdas_com = circuit.Losses[0] / 1000.0

    # Q na linha de referencia
    circuit.SetActiveElement(f"Line.{melhor_nome}")
    powers = circuit.ActiveCktElement.Powers
    n = circuit.ActiveCktElement.NumPhases
    q_com = abs(sum(powers[1:n*2+1:2]))

    # Estado do capacitor por ultimo
    circuit.SetActiveElement("Capacitor.CAPX")
    ligado = "SIM" if not circuit.ActiveCktElement.IsOpen(1, 0) else "NAO"
    if ligado == "SIM":
        cap_ligado_horas += 1

    delta = perdas_ref[h] - perdas_com
    delta_total += delta
    noite = "*" if h in HORAS_NOTURNAS else " "
    print(f"  {h+1:>4}{noite} {q_ref[h]:>9.1f} {q_com:>9.1f} {ligado:>5} {perdas_ref[h]:>10.2f} {perdas_com:>10.2f} {delta:>9.3f}")

economia_anual = delta_total * 365 / 1000 * 35

print(f"\n  Horas com capacitor ligado : {cap_ligado_horas}/24")
print(f"  Reducao de perdas/dia      : {delta_total:.3f} kW")
print(f"  Reducao de perdas/ano      : {delta_total*365/1000:.4f} MWh/ano")
print(f"  Economia anual             : USD {economia_anual:.2f}/ano  (35 USD/MWh)")
if economia_anual > 0:
    print(f"  Payback simples            : {7031/economia_anual:.0f} anos")
else:
    print(f"  Payback                    : inviavel (capacitor aumenta perdas)")
print(f"{'='*70}")
