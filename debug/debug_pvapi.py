import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dss import dss

MASTER = str(HERE / "Master.dss")
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
circuit = dss.ActiveCircuit

pvs = circuit.PVSystems
idx = pvs.First
print(f"Atributos de IPVSystems:")
attrs = [a for a in dir(pvs) if not a.startswith('_')]
for a in attrs:
    print(f"  {a}")
