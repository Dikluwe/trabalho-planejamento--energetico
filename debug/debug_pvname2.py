import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dss import dss

MASTER = str(HERE / "Master.dss")
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
circuit = dss.ActiveCircuit

circuit.SetActiveClass("PVSystem")
idx = circuit.ActiveClass.First
nome = circuit.ActiveClass.Name  # gd.rs.001.593.160

print(f"Nome: {nome}")

# Testa com aspas simples no nome
dss.Text.Command = f"? PVSystem.'{nome}'.Pmpp"
print(f"Com aspas simples: {repr(dss.Text.Result)}")

# Testa com brackets
dss.Text.Command = f'? PVSystem.[{nome}].Pmpp'
print(f"Com brackets: {repr(dss.Text.Result)}")

# Tenta via interface Python do PVSystems
pvs = circuit.PVSystems
print(f"\nPVSystems count: {pvs.Count}")
idx2 = pvs.First
if idx2 > 0:
    print(f"pvs.Name: {repr(pvs.Name)}")
    print(f"pvs.kVArated: {pvs.kVArated}")
    print(f"pvs.Pmpp: {pvs.Pmpp}")
    print(f"pvs.irradiance: {pvs.irradiance}")
