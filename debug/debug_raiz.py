import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dss import dss

MASTER = str(HERE.parent / "dss" / "Master.dss")
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"
circuit = dss.ActiveCircuit

# Linha smt_24122
circuit.SetActiveClass("Line")
idx = circuit.Lines.First
while idx > 0:
    if circuit.Lines.Name.lower() == "smt_24122":
        b1 = circuit.Lines.Bus1.split(".")[0]
        b2 = circuit.Lines.Bus2.split(".")[0]
        print(f"smt_24122: {b1} → {b2}")
        circuit.SetActiveBus(b1)
        print(f"  kV b1={circuit.ActiveBus.kVBase:.3f}")
        circuit.SetActiveBus(b2)
        print(f"  kV b2={circuit.ActiveBus.kVBase:.3f}")
        break
    idx = circuit.Lines.Next

# PVSystem — como ler e setar kVA
circuit.SetActiveClass("PVSystem")
idx = circuit.ActiveClass.First
nome = circuit.ActiveCktElement.Name.split(".")[1]
print(f"\nPVSystem.{nome}:")
dss.Text.Command = f"? PVSystem.{nome}.kVA"
print(f"  kVA : {dss.Text.Result}")
dss.Text.Command = f"? PVSystem.{nome}.Pmpp"
print(f"  Pmpp: {dss.Text.Result}")
dss.Text.Command = f"? PVSystem.{nome}.irradiance"
print(f"  irradiance: {dss.Text.Result}")

# Testa escalar via kVA e Pmpp
kva_str = dss.Text.Result  # já é irradiance, pega kVA de novo
dss.Text.Command = f"? PVSystem.{nome}.kVA"
kva_orig = float(dss.Text.Result)
dss.Text.Command = f"? PVSystem.{nome}.Pmpp"
pmpp_orig = float(dss.Text.Result)
print(f"\n  Teste de escala +20%:")
print(f"  Edit kVA={kva_orig*1.2:.2f} Pmpp={pmpp_orig*1.2:.2f}")
dss.Text.Command = f"Edit PVSystem.{nome} kVA={kva_orig*1.2:.2f} Pmpp={pmpp_orig*1.2:.2f}"
dss.Text.Command = f"? PVSystem.{nome}.kVA"
print(f"  kVA após edit: {dss.Text.Result}")
