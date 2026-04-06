# comparar_capcontrol.py
# Compara duas estratégias de controle do capacitor automático:
# Opção 2: Loadshape fixo no capacitor (estados hora a hora)
# Opção 3: Controle manual por hora no loop Python

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

from dss import dss

HORAS_NOTURNAS = list(range(0, 6)) + list(range(19, 24))

import json

config_file = HERE / "parametros.json"
if not config_file.exists():
    print("Execute 03_melhor_ponto_capacitor.py primeiro para gerar config no JSON.")
    sys.exit(1)

with open(config_file, "r") as f:
    config = json.load(f)

MASTER = str(HERE / config["caminhos"]["dss_file"])

c_alvo = config.get("capacitor_alvo", {})
MELHOR_BUS  = c_alvo.get("barramento", "181")
MELHOR_NOME = c_alvo.get("linha_referencia", "smt_6350")
CAP_KVAR    = c_alvo.get("kvar_calculado", 50)
ONSETTING   = c_alvo.get("onsetting_sugerido", 37)
OFFSETTING  = c_alvo.get("offsetting_sugerido", 15)

PRECO_MWH   = config.get("economico", {}).get("preco_compra_usd_mwh", 35.0)
# Custo estimado simples para a avaliação: custo base + custo por kvar
CUSTO_CAP   = 800 + (10 * CAP_KVAR)

# ---------------------------------------------------------------------------
# PASSO 1 — Referência sem capacitor
# ---------------------------------------------------------------------------
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"

circuit = dss.ActiveCircuit

q_ref      = {}
perdas_ref = {}
circuit.Solution.dblHour = 0.0
for h in range(24):
    circuit.Solution.Solve()
    perdas_ref[h] = circuit.Losses[0] / 1000.0
    circuit.SetActiveElement(f"Line.{MELHOR_NOME}")
    powers = circuit.ActiveCktElement.Powers
    n = circuit.ActiveCktElement.NumPhases
    q_ref[h] = abs(sum(powers[1:n*2+1:2]))

# ---------------------------------------------------------------------------
# PASSO 2 — Loadshape fixo (liga 6h-21h independente de Q)
# ---------------------------------------------------------------------------
# Estado: desligado 0-5h, ligado 6h-21h, desligado 22-24h
states_op2 = [0,0,0,0,0,0, 1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1, 0,0]
states_str = "[" + ",".join(str(s) for s in states_op2) + "]"

dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"
dss.Text.Command = f"New Capacitor.CAPX bus1={MELHOR_BUS} phases=3 kvar={CAP_KVAR} kv=23.1 states={states_str}"
dss.Text.Command = f"New Loadshape.CAP_HORARIO npts=24 interval=1 mult={states_str}"

q_op2      = {}
perdas_op2 = {}
ligado_op2 = {}

circuit.Solution.dblHour = 0.0
for h in range(24):
    # Força o estado conforme o loadshape antes de resolver
    estado = states_op2[h]
    dss.Text.Command = f"Edit Capacitor.CAPX states=[{estado}]"
    circuit.Solution.Solve()
    if not circuit.Solution.Converged:
        print(f"Erro: O fluxo de carga não convergiu na hora {h}.")
        sys.exit(1)
    perdas_op2[h] = circuit.Losses[0] / 1000.0
    circuit.SetActiveElement(f"Line.{MELHOR_NOME}")
    powers = circuit.ActiveCktElement.Powers
    n = circuit.ActiveCktElement.NumPhases
    q_op2[h] = abs(sum(powers[1:n*2+1:2]))
    ligado_op2[h] = "SIM" if estado == 1 else "NAO"

# ---------------------------------------------------------------------------
# PASSO 3 — Controle manual por Q e horário no loop Python
# Liga apenas se Q > onsetting E está no período noturno/crepuscular
# Desliga se Q < offsetting OU está fora da janela de controle
# ---------------------------------------------------------------------------
# Janela: horas onde há Q real das cargas (sem GD dominante)
# GD fotovoltaica: ativa das 7h-18h → fora dessa janela o Q é real
HORAS_CONTROLE = list(range(0, 7)) + list(range(19, 24))  # sem GD

dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"
dss.Text.Command = f"New Capacitor.CAPX bus1={MELHOR_BUS} phases=3 kvar={CAP_KVAR} kv=23.1"

q_op3      = {}
perdas_op3 = {}
ligado_op3 = {}
estado_atual = 0  # começa desligado

circuit.Solution.dblHour = 0.0
for h in range(24):
    # Lógica de controle manual:
    # - Dentro da janela sem GD: usa histerese de Q
    # - Durante geração solar (7h-18h): força desligado
    if h in HORAS_CONTROLE:
        if estado_atual == 0 and q_ref[h] > ONSETTING:
            estado_atual = 1
        elif estado_atual == 1 and q_ref[h] < OFFSETTING:
            estado_atual = 0
    else:
        estado_atual = 0  # força desligado durante GD

    dss.Text.Command = f"Edit Capacitor.CAPX states=[{estado_atual}]"
    circuit.Solution.Solve()
    if not circuit.Solution.Converged:
        print(f"Erro: O fluxo de carga não convergiu na hora {h}.")
        sys.exit(1)
    perdas_op3[h] = circuit.Losses[0] / 1000.0
    circuit.SetActiveElement(f"Line.{MELHOR_NOME}")
    powers = circuit.ActiveCktElement.Powers
    n = circuit.ActiveCktElement.NumPhases
    q_op3[h] = abs(sum(powers[1:n*2+1:2]))
    ligado_op3[h] = "SIM" if estado_atual == 1 else "NAO"

# ---------------------------------------------------------------------------
# RESULTADO COMPARATIVO
# ---------------------------------------------------------------------------
print("\n" + "="*90)
print("[03.06] COMPARAÇÃO DE ESTRATÉGIAS — CAPACITOR 50 kvar NO BARRAMENTO 181")
print("="*90)
print(f"  {'':5} {'Q sem':>7}  {'--- Opção 2: Loadshape fixo ---':^33}  {'--- Opção 3: Controle manual ---':^33}")
print(f"  {'Hora':>4} {'(kvar)':>7}  {'Q com':>7} {'Cap':>5} {'Perdas':>8} {'Delta':>7}  {'Q com':>7} {'Cap':>5} {'Perdas':>8} {'Delta':>7}")
print(f"  {'-'*88}")

delta2 = delta3 = 0.0
lig2 = lig3 = 0

circuit.Solution.dblHour = 0.0
for h in range(24):
    d2 = perdas_ref[h] - perdas_op2[h]
    d3 = perdas_ref[h] - perdas_op3[h]
    delta2 += d2
    delta3 += d3
    if ligado_op2[h] == "SIM": lig2 += 1
    if ligado_op3[h] == "SIM": lig3 += 1
    noite = "*" if h in HORAS_NOTURNAS else " "
    print(f"  {h+1:>4}{noite} {q_ref[h]:>7.1f}  "
          f"{q_op2[h]:>7.1f} {ligado_op2[h]:>5} {perdas_op2[h]:>8.2f} {d2:>7.3f}  "
          f"{q_op3[h]:>7.1f} {ligado_op3[h]:>5} {perdas_op3[h]:>8.2f} {d3:>7.3f}")

print(f"  {'-'*88}")

eco2 = delta2 * 365 / 1000 * PRECO_MWH
eco3 = delta3 * 365 / 1000 * PRECO_MWH

print(f"\n  {'':30} {'Opção 2':>15} {'Opção 3':>15}")
print(f"  {'Horas ligado/dia':<30} {lig2:>15} {lig3:>15}")
print(f"  {'Redução perdas/dia (kW)':<30} {delta2:>15.3f} {delta3:>15.3f}")
print(f"  {'Redução perdas/ano (MWh)':<30} {delta2*365/1000:>15.4f} {delta3*365/1000:>15.4f}")
print(f"  {'Economia anual (USD)':<30} {eco2:>15.2f} {eco3:>15.2f}  (@ {PRECO_MWH} USD/MWh)")
if eco2 > 0:
    print(f"  {'Payback (anos)':<30} {CUSTO_CAP/eco2:>15.1f} {CUSTO_CAP/eco3 if eco3>0 else 'inviavel':>15}")
print(f"\n  Opção 2: capacitor ligado das 6h-21h fixo (sem lógica de Q)")
print(f"  Opção 3: capacitor ligado só fora do horário de GD, com histerese de Q")
print(f"           onsetting={ONSETTING} kvar / offsetting={OFFSETTING} kvar")
print("="*90)
