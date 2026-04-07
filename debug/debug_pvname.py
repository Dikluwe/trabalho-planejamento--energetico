import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dss import dss

MASTER = str(HERE.parent / "dss" / "Master.dss")
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
circuit = dss.ActiveCircuit

circuit.SetActiveClass("PVSystem")
idx = circuit.ActiveClass.First
count = 0
while idx > 0 and count < 3:
    print(f"ActiveClass.Name     : {repr(circuit.ActiveClass.Name)}")
    print(f"ActiveCktElement.Name: {repr(circuit.ActiveCktElement.Name)}")
    # Tenta AllNames
    idx = circuit.ActiveClass.Next
    count += 1

# AllNames da classe
print("\nPVSystem.AllNames[:3]:")
circuit.SetActiveClass("PVSystem")
nomes = list(circuit.ActiveClass.AllNames)
for n in nomes[:3]:
    print(f"  {repr(n)}")
    dss.Text.Command = f"? PVSystem.{n}.Pmpp"
    print(f"  Pmpp query result: {repr(dss.Text.Result)}")
