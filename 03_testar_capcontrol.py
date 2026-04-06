# 03_testar_capcontrol.py
# Testa o capacitor automático isoladamente e verifica se o CapControl atua

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dss import dss

import json
with open(HERE / "parametros.json", "r") as f:
    config = json.load(f)
MASTER = str(HERE / config["caminhos"]["dss_file"])

print("\n" + "="*60)
print("[03.04] TESTE DO CAPACITOR AUTOMÁTICO — barra 9051")
print("="*60)

# ---------------------------------------------------------------------------
# Caso base sem capacitor
# ---------------------------------------------------------------------------
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=24"
dss.Text.Command = "Reset Meters"
dss.ActiveCircuit.Solution.Solve()

circuit = dss.ActiveCircuit
perdas_base = circuit.Losses[0] / 1000.0
energia_base = sum(circuit.Meters.RegisterValues[:1]) if circuit.Meters.First > 0 else 0.0

# Lê reativo na linha smt_14449 hora a hora
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"
dss.Text.Command = "Reset Meters"

print("\nPerfil de potência reativa — Line.smt_14449 (sem capacitor):")
print(f"  {'Hora':>4} {'P (kW)':>10} {'Q (kvar)':>10} {'S (kVA)':>10}")
print(f"  {'-'*40}")

q_max_base = 0.0
for h in range(24):
    circuit.Solution.Solve()
    if not circuit.Solution.Converged:
        print(f"Erro: O fluxo de carga não convergiu na hora {h}.")
        sys.exit(1)
    circuit.SetActiveElement("Line.smt_14449")
    powers = circuit.ActiveCktElement.Powers
    n = circuit.ActiveCktElement.NumPhases
    p = sum(powers[0:n*2:2])
    q = sum(powers[1:n*2+1:2])
    s = (p**2 + q**2)**0.5
    q_max_base = max(q_max_base, abs(q))
    if abs(q) > 50 or h in [6,7,8,17,18,19]:
        print(f"  {h+1:>4} {p:>10.1f} {q:>10.1f} {s:>10.1f}")

print(f"\n  Q máximo observado: {q_max_base:.1f} kvar")
print(f"  onsetting configurado: 200 kvar")
if q_max_base < 200:
    print(f"  >>> O Q máximo é MENOR que o onsetting — o capacitor NUNCA liga!")
    print(f"  >>> Ajuste o onsetting para {q_max_base*0.6:.0f} kvar (60% do máximo)")
else:
    print(f"  >>> O Q máximo é MAIOR que o onsetting — o capacitor DEVE ligar")

# ---------------------------------------------------------------------------
# Testa com CapControl ajustado
# ---------------------------------------------------------------------------
onsetting = max(50, int(q_max_base * 0.6))
offsetting = max(30, int(q_max_base * 0.4))

print(f"\n{'='*60}")
print(f"[03.05] RETESTANDO com onsetting={onsetting} offsetting={offsetting}")
print(f"{'='*60}")

dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"
dss.Text.Command = "Set maxcontroliter=100"
dss.Text.Command = "New Capacitor.CAP2 bus1=9051 phases=3 kvar=1200 kv=23.1"
dss.Text.Command = f"New CapControl.CC2 element=Line.smt_14449 terminal=1 capacitor=CAP2 type=kvar onsetting={onsetting} offsetting={offsetting}"
dss.Text.Command = "Reset Meters"

print(f"\nPerfil com CapControl (onsetting={onsetting}, offsetting={offsetting}):")
print(f"  {'Hora':>4} {'Q sem (kvar)':>13} {'Q com (kvar)':>13} {'Cap ligado':>12}")
print(f"  {'-'*50}")

# Primeiro roda sem capacitor para ter referência hora a hora
q_sem = {}
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"
for h in range(24):
    circuit.Solution.Solve()
    if not circuit.Solution.Converged:
        print(f"Erro: O fluxo de carga não convergiu na hora {h}.")
        sys.exit(1)
    circuit.SetActiveElement("Line.smt_14449")
    powers = circuit.ActiveCktElement.Powers
    n = circuit.ActiveCktElement.NumPhases
    q_sem[h] = sum(powers[1:n*2+1:2])

# Agora com capacitor
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"
dss.Text.Command = "Set maxcontroliter=100"
dss.Text.Command = "New Capacitor.CAP2 bus1=9051 phases=3 kvar=1200 kv=23.1"
dss.Text.Command = f"New CapControl.CC2 element=Line.smt_14449 terminal=1 capacitor=CAP2 type=kvar onsetting={onsetting} offsetting={offsetting}"

perdas_com = 0.0
for h in range(24):
    circuit.Solution.Solve()
    if not circuit.Solution.Converged:
        print(f"Erro: O fluxo de carga não convergiu na hora {h}.")
        sys.exit(1)
    circuit.SetActiveElement("Line.smt_14449")
    powers = circuit.ActiveCktElement.Powers
    n = circuit.ActiveCktElement.NumPhases
    q_com = sum(powers[1:n*2+1:2])

    # Verifica se capacitor está ligado
    circuit.SetActiveElement("Capacitor.CAP2")
    cap_state = "SIM" if circuit.ActiveCktElement.IsOpen(1, 0) == 0 else "NÃO"

    perdas_com += circuit.Losses[0] / 1000.0

    print(f"  {h+1:>4} {q_sem[h]:>13.1f} {q_com:>13.1f} {cap_state:>12}")

# Perdas totais
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=24"
dss.Text.Command = "Reset Meters"
circuit.Solution.Solve()
perdas_base_total = circuit.Losses[0] / 1000.0

print(f"\nPerdas totais 24h sem cap: {perdas_base_total:.2f} kW")

print(f"\nComando correto para o main_trabalho.py:")
print(f'  "New Capacitor.CAP2 bus1=9051 phases=3 kvar=1200 kv=23.1",')
print(f'  "New CapControl.CC2 element=Line.smt_14449 terminal=1 capacitor=CAP2 type=kvar onsetting={onsetting} offsetting={offsetting}",')
print(f'  "Set maxcontroliter=100",')
