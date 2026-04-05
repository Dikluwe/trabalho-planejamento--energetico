# diagnosticar.py
# Investiga o comportamento do CapControl e do tap no OpenDSS

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dss import dss

MASTER = str(HERE / "Master.dss")

def carregar():
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{MASTER}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"

# ---------------------------------------------------------------------------
# 1. Diagnóstico do tap
# ---------------------------------------------------------------------------
print("\n" + "="*60)
print("DIAGNÓSTICO DO TAP — trf_6_4910a")
print("="*60)

carregar()
circuit = dss.ActiveCircuit

# Lê o estado nominal do trafo
circuit.Transformers.Name = "trf_6_4910a"
print(f"\nEstado nominal:")
print(f"  kVA nominal : {circuit.Transformers.kVA}")
print(f"  Num windings: {circuit.Transformers.NumWindings}")

# Lê tensão e tap por winding
for wdg in [1, 2]:
    circuit.Transformers.Wdg = wdg
    print(f"  Winding {wdg}   : kV={circuit.Transformers.kV:.4f}  tap={circuit.Transformers.Tap:.4f}")

# Resolve o caso base (hora 7 — pico de carga)
dss.Text.Command = "Set mode=daily stepsize=1h number=7"
circuit.Solution.Solve()

# Carregamento original
circuit.SetActiveElement("Transformer.trf_6_4910a")
powers = circuit.ActiveCktElement.Powers
n_fases = circuit.ActiveCktElement.NumPhases
p = sum(powers[0:n_fases*2:2])
q = sum(powers[1:n_fases*2+1:2])
s_orig = (p**2 + q**2)**0.5
print(f"\nCarregamento hora 7 (sem tap):")
print(f"  S = {s_orig:.2f} kVA  ({100*s_orig/circuit.Transformers.kVA:.1f}%)")

# Tensão no secundário
circuit.SetActiveBus("et6_4910")
v_sec_orig = circuit.ActiveBus.VMagAngle[0]
kv_base = circuit.ActiveBus.kVBase
v_pu_orig = v_sec_orig / (kv_base * 1000) if kv_base > 0 else 0
print(f"  V secundário: {v_sec_orig:.1f} V  ({v_pu_orig:.4f} pu)")

# Testa tap wdg=1 tap=1.0333 (aumenta relação → reduz corrente primário)
carregar()
dss.Text.Command = "Set mode=daily stepsize=1h number=7"
dss.Text.Command = "Edit Transformer.TRF_6_4910A wdg=1 tap=1.0333"
circuit.Solution.Solve()

circuit.SetActiveElement("Transformer.trf_6_4910a")
circuit.Transformers.Name = "trf_6_4910a"
powers = circuit.ActiveCktElement.Powers
p = sum(powers[0:n_fases*2:2])
q = sum(powers[1:n_fases*2+1:2])
s_wdg1 = (p**2 + q**2)**0.5
circuit.SetActiveBus("et6_4910")
v_sec_wdg1 = circuit.ActiveBus.VMagAngle[0]
v_pu_wdg1 = v_sec_wdg1 / (kv_base * 1000) if kv_base > 0 else 0
print(f"\nCom wdg=1 tap=1.0333 (primário +1 derivação):")
print(f"  S = {s_wdg1:.2f} kVA  ({100*s_wdg1/30:.1f}%)")
print(f"  V secundário: {v_sec_wdg1:.1f} V  ({v_pu_wdg1:.4f} pu)")

# Testa tap wdg=2 tap=0.9667 (nosso atual — abaixa secundário)
carregar()
dss.Text.Command = "Set mode=daily stepsize=1h number=7"
dss.Text.Command = "Edit Transformer.TRF_6_4910A wdg=2 tap=0.9667"
circuit.Solution.Solve()

circuit.SetActiveElement("Transformer.trf_6_4910a")
powers = circuit.ActiveCktElement.Powers
p = sum(powers[0:n_fases*2:2])
q = sum(powers[1:n_fases*2+1:2])
s_wdg2 = (p**2 + q**2)**0.5
circuit.SetActiveBus("et6_4910")
v_sec_wdg2 = circuit.ActiveBus.VMagAngle[0]
v_pu_wdg2 = v_sec_wdg2 / (kv_base * 1000) if kv_base > 0 else 0
print(f"\nCom wdg=2 tap=0.9667 (secundário -1 derivação — atual):")
print(f"  S = {s_wdg2:.2f} kVA  ({100*s_wdg2/30:.1f}%)")
print(f"  V secundário: {v_sec_wdg2:.1f} V  ({v_pu_wdg2:.4f} pu)")

print(f"\nConclusão tap:")
if s_wdg1 < s_orig:
    print(f"  wdg=1 tap=1.0333 REDUZ o carregamento ({s_orig:.1f} → {s_wdg1:.1f} kVA)")
else:
    print(f"  wdg=1 tap=1.0333 NÃO reduz carregamento")
if s_wdg2 < s_orig:
    print(f"  wdg=2 tap=0.9667 REDUZ o carregamento ({s_orig:.1f} → {s_wdg2:.1f} kVA)")
else:
    print(f"  wdg=2 tap=0.9667 NÃO reduz carregamento")

# ---------------------------------------------------------------------------
# 2. Diagnóstico do CapControl
# ---------------------------------------------------------------------------
print("\n" + "="*60)
print("DIAGNÓSTICO DO CAPCONTROL")
print("="*60)

carregar()

# Lista os elementos disponíveis para referência do CapControl
print("\nLinhas conectadas ao barramento 9051:")
circuit.SetActiveClass("Line")
lines = circuit.Lines
idx = lines.First
linhas_9051 = []
while idx > 0:
    b1 = lines.Bus1.split(".")[0].lower()
    b2 = lines.Bus2.split(".")[0].lower()
    if b1 == "9051" or b2 == "9051":
        linhas_9051.append(lines.Name)
        print(f"  Line.{lines.Name}  ({b1} → {b2})  normAmps={lines.NormAmps:.1f}")
    idx = lines.Next

# Testa CapControl usando a primeira linha conectada ao barramento
if linhas_9051:
    linha_ref = linhas_9051[0]
    print(f"\nTestando CapControl com element=Line.{linha_ref}")

    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    dss.Text.Command = "New Capacitor.CAP2 bus1=9051 phases=3 kvar=1200 kv=23.1"
    dss.Text.Command = f"New CapControl.CC2 element=Line.{linha_ref} terminal=1 capacitor=CAP2 type=kvar onsetting=200 offsetting=150"

    # Resolve 24h e verifica se o capacitor atuou
    dss.Text.Command = "Set mode=daily stepsize=1h number=24"
    circuit.Solution.Solve()

    # Verifica estado do capacitor
    circuit.SetActiveElement("Capacitor.CAP2")
    print(f"  Capacitor CAP2 existe: {circuit.ActiveCktElement.Name}")

    # Verifica potência reativa no barramento 9051
    circuit.SetActiveBus("9051")
    v9051 = circuit.ActiveBus.VMagAngle
    print(f"  Tensão barra 9051: {v9051[0]:.1f} V  ({v9051[0]/(23100/3**0.5):.4f} pu)")

    # Lê perdas totais com capacitor
    perdas_com = circuit.Losses[0] / 1000.0
    print(f"  Perdas totais: {perdas_com:.2f} kW")

    print(f"\n  Comando alternativo para CapControl baseado em kvar:")
    print(f"  New CapControl.CC2 element=Line.{linha_ref} terminal=1 capacitor=CAP2 type=kvar onsetting=200 offsetting=150")
else:
    print("  Nenhuma linha encontrada no barramento 9051")
    print("  Verificando transformador como elemento de referência...")
    
    # Verifica se o transformador funciona como referência
    circuit.SetActiveElement("Transformer.TRF_6_4910A")
    print(f"  Transformer.TRF_6_4910A existe: {circuit.ActiveCktElement.Name}")
    print(f"  NumTerminals: {circuit.ActiveCktElement.NumTerminals}")
    print(f"  BusNames: {list(circuit.ActiveCktElement.BusNames)}")
