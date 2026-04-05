import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dss import dss

MASTER = str(HERE / "Master.dss")
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"
circuit = dss.ActiveCircuit

# Verifica barramentos vizinhos de 1_rede2_1
print("Vizinhos de 1_rede2_1 no grafo MT:")
circuit.SetActiveClass("Line")
idx = circuit.Lines.First
count = 0
while idx > 0:
    if not circuit.Lines.IsSwitch:
        b1 = circuit.Lines.Bus1.split(".")[0]
        b2 = circuit.Lines.Bus2.split(".")[0]
        if b1 == "1_rede2_1" or b2 == "1_rede2_1":
            circuit.SetActiveBus(b1)
            kv1 = circuit.ActiveBus.kVBase
            circuit.SetActiveBus(b2)
            kv2 = circuit.ActiveBus.kVBase
            print(f"  Line.{circuit.Lines.Name}: {b1}(kV={kv1:.2f}) → {b2}(kV={kv2:.2f})")
            count += 1
    idx = circuit.Lines.Next
print(f"  Total: {count} linhas")

# BFS a partir de 1_rede2_1 em vez de 660991
from collections import deque
grafo = {}
circuit.SetActiveClass("Line")
idx = circuit.Lines.First
while idx > 0:
    if not circuit.Lines.IsSwitch:
        b1 = circuit.Lines.Bus1.split(".")[0]
        b2 = circuit.Lines.Bus2.split(".")[0]
        comp = circuit.Lines.Length * 1000
        circuit.SetActiveBus(b1)
        kv1 = circuit.ActiveBus.kVBase
        circuit.SetActiveBus(b2)
        kv2 = circuit.ActiveBus.kVBase
        if kv1 > 1.0 and kv2 > 1.0:
            if b1 not in grafo: grafo[b1] = []
            if b2 not in grafo: grafo[b2] = []
            grafo[b1].append((b2, comp))
            grafo[b2].append((b1, comp))
    idx = circuit.Lines.Next

distancia = {"1_rede2_1": 0.0}
fila = deque(["1_rede2_1"])
while fila:
    bus = fila.popleft()
    for viz, comp in grafo.get(bus, []):
        if viz not in distancia:
            distancia[viz] = distancia[bus] + comp
            fila.append(viz)

print(f"\nBFS a partir de 1_rede2_1: {len(distancia)} barramentos")
max_d = max(distancia.values())
print(f"Distância máxima: {max_d/1000:.1f} km")
top5 = sorted(distancia.items(), key=lambda x: x[1], reverse=True)[:5]
for b, d in top5:
    print(f"  {b}: {d/1000:.2f} km")

# PVSystems — lista nomes reais
print("\nPVSystems disponíveis:")
circuit.SetActiveClass("PVSystem")
idx = circuit.ActiveClass.First
while idx > 0:
    nome_completo = circuit.ActiveCktElement.Name
    nome = nome_completo.split(".")[1] if "." in nome_completo else nome_completo
    # Lê kVA via Pmpp usando Text
    dss.Text.Command = f'? PVSystem."{nome}".Pmpp'
    pmpp = dss.Text.Result
    dss.Text.Command = f'? PVSystem."{nome}".kVA'
    kva = dss.Text.Result
    print(f"  {nome_completo}  Pmpp={pmpp}  kVA={kva}")
    if idx > 3:
        print("  ...")
        break
    idx = circuit.ActiveClass.Next
