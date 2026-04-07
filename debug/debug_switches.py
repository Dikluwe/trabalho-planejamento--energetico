import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dss import dss

MASTER = str(HERE.parent / "dss" / "Master.dss")
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
circuit = dss.ActiveCircuit

# Conta chaves (switches) na rede
circuit.SetActiveClass("Line")
lines = circuit.Lines
switches = []
idx = lines.First
while idx > 0:
    if lines.IsSwitch:
        b1 = lines.Bus1.split(".")[0]
        b2 = lines.Bus2.split(".")[0]
        switches.append((lines.Name, b1, b2))
    idx = lines.Next

print(f"Total de chaves (IsSwitch=True): {len(switches)}")
for nome, b1, b2 in switches[:20]:
    print(f"  Line.{nome}: {b1} → {b2}")
if len(switches) > 20:
    print(f"  ... e mais {len(switches)-20}")

# Verifica se há elementos Open na rede (chaves abertas)
print(f"\nElementos com IsOpen=True (chaves normalmente abertas):")
n_open = 0
circuit.SetActiveClass("Line")
idx = circuit.Lines.First
while idx > 0:
    circuit.SetActiveElement(f"Line.{circuit.Lines.Name}")
    if circuit.ActiveCktElement.IsOpen(1, 0):
        b1 = circuit.Lines.Bus1.split(".")[0]
        b2 = circuit.Lines.Bus2.split(".")[0]
        print(f"  Line.{circuit.Lines.Name}: {b1} → {b2}")
        n_open += 1
    idx = circuit.Lines.Next

if n_open == 0:
    print("  Nenhum — rede estritamente radial, sem pontos de manobra")
print(f"\nTotal abertos: {n_open}")
