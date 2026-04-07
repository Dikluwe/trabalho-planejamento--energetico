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

# Quantos barramentos MT existem de fato (kV > 1)
n_mt = sum(1 for b in circuit.AllBusNames
           if (circuit.SetActiveBus(b), circuit.ActiveBus.kVBase)[1] > 1.0)
print(f"Barramentos com kVBase > 1.0: {n_mt}")

# Distribuição de kVBase
from collections import Counter
kvs = []
for b in circuit.AllBusNames:
    circuit.SetActiveBus(b)
    kvs.append(round(circuit.ActiveBus.kVBase, 2))
dist = Counter(kvs)
print("Distribuição de kVBase (top 10):")
for kv, cnt in sorted(dist.items(), reverse=True)[:10]:
    print(f"  {kv:.2f} kV: {cnt} barramentos")

# Quantas linhas MT existem
n_linhas_mt = 0
circuit.SetActiveClass("Line")
idx = circuit.Lines.First
kvs_linhas = set()
while idx > 0:
    if not circuit.Lines.IsSwitch:
        b1 = circuit.Lines.Bus1.split(".")[0]
        circuit.SetActiveBus(b1)
        kv = circuit.ActiveBus.kVBase
        if kv > 1.0:
            n_linhas_mt += 1
            kvs_linhas.add(round(kv, 2))
    idx = circuit.Lines.Next
print(f"\nLinhas MT (kV > 1): {n_linhas_mt}")
print(f"kVs distintos nas linhas MT: {sorted(kvs_linhas)}")

# PVSystem — nome real
print("\nPVSystems (primeiros 3):")
circuit.SetActiveClass("PVSystem")
idx = circuit.ActiveClass.First
count = 0
while idx > 0 and count < 3:
    nome_completo = circuit.ActiveCktElement.Name
    print(f"  Name completo: {repr(nome_completo)}")
    # Tenta ler Pmpp via propriedade do objeto
    pvs = circuit.ActiveClass
    print(f"  ActiveClass.Name: {repr(pvs.Name)}")
    idx = circuit.ActiveClass.Next
    count += 1
