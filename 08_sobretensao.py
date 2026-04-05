# 08_sobretensao.py
# Investigação das sobretensões identificadas no PRODIST DRP/DRC
# Barramentos: bt56881 (DRC=2.98%) e uc1607347 (DRC=3.57%)

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dss import dss

MASTER = str(HERE / "Master.dss")

def carregar(loadmult=1.0, cmds=None):
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{MASTER}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    dss.Text.Command = f"Set LoadMult={loadmult}"
    if cmds:
        for c in cmds: dss.Text.Command = c
    return dss.ActiveCircuit

ALVOS = ["bt56881", "uc1607347", "uc606147", "bt71761"]

print("\n" + "="*70)
print("INVESTIGAÇÃO DE SOBRETENSÕES — PRODIST TABELA 5")
print("="*70)

# ===========================================================================
# 1. TOPOLOGIA DOS BARRAMENTOS COM SOBRETENSÃO
# ===========================================================================
print("\n1. TOPOLOGIA DOS BARRAMENTOS COM SOBRETENSÃO")
print("─"*70)

circuit = carregar(1.0)
all_bus = list(circuit.AllBusNames)

for alvo in ALVOS:
    circuit.SetActiveBus(alvo)
    kv = circuit.ActiveBus.kVBase
    nn = circuit.ActiveBus.NumNodes
    print(f"\n  Barramento: {alvo}")
    print(f"    kVBase={kv:.4f} kV  NumNodes={nn}")

    # Encontra linhas conectadas
    circuit.SetActiveClass("Line")
    idx = circuit.Lines.First
    linhas_conectadas = []
    while idx > 0:
        b1 = circuit.Lines.Bus1.split(".")[0]
        b2 = circuit.Lines.Bus2.split(".")[0]
        if b1 == alvo or b2 == alvo:
            linhas_conectadas.append({
                "nome": circuit.Lines.Name,
                "b1": b1, "b2": b2,
                "length": circuit.Lines.Length * 1000,
            })
        idx = circuit.Lines.Next

    for l in linhas_conectadas:
        print(f"    Line.{l['nome']}: {l['b1']} → {l['b2']} ({l['length']:.1f}m)")

    # Encontra transformadores conectados
    circuit.SetActiveClass("Transformer")
    idx = circuit.Transformers.First
    while idx > 0:
        circuit.SetActiveElement(f"Transformer.{circuit.Transformers.Name}")
        buses = [b.split(".")[0] for b in circuit.ActiveCktElement.BusNames]
        if alvo in buses:
            kva = circuit.Transformers.kVA
            print(f"    Transformer.{circuit.Transformers.Name}: {buses}  {kva:.0f} kVA")
        idx = circuit.Transformers.Next

    # Encontra cargas conectadas
    loads = circuit.Loads
    idx = loads.First
    while idx > 0:
        circuit.SetActiveElement(f"Load.{loads.Name}")
        bus = circuit.ActiveCktElement.BusNames[0].split(".")[0]
        if bus == alvo:
            print(f"    Load.{loads.Name}: {loads.kW:.2f} kW  {loads.kvar:.2f} kvar")
        idx = loads.Next

    # Encontra PVSystems conectados
    circuit.SetActiveClass("PVSystem")
    idx = circuit.ActiveClass.First
    while idx > 0:
        bus_pv = circuit.ActiveCktElement.BusNames[0].split(".")[0]
        if bus_pv == alvo:
            nome_pv = circuit.ActiveClass.Name
            print(f"    PVSystem.{nome_pv}  bus={bus_pv}")
        idx = circuit.ActiveClass.Next

# ===========================================================================
# 2. PERFIL HORÁRIO DE TENSÃO NOS BARRAMENTOS COM VIOLAÇÃO
# ===========================================================================
print(f"\n{'─'*70}")
print("2. PERFIL HORÁRIO DE TENSÃO — CASO BASE (LoadMult=1.0)")
print("─"*70)

circuit = carregar(1.0)

print(f"\n  {'Hora':>4}", end="")
for alvo in ALVOS:
    print(f"  {alvo:>14}", end="")
print(f"  {'GD total kW':>12}")
print(f"  {'-'*74}")

hora_pico_vmax = {a: (0, 0.0) for a in ALVOS}

for h in range(24):
    circuit.Solution.Solve()

    # GD total
    p_gd = 0.0
    circuit.SetActiveClass("PVSystem")
    idx = circuit.ActiveClass.First
    while idx > 0:
        pw = circuit.ActiveCktElement.Powers
        n  = circuit.ActiveCktElement.NumPhases
        if len(pw) >= n*2:
            p_gd += abs(sum(pw[0:n*2:2]))
        idx = circuit.ActiveClass.Next

    print(f"  {h+1:>4}", end="")
    for alvo in ALVOS:
        circuit.SetActiveBus(alvo)
        kv   = circuit.ActiveBus.kVBase
        vmag = circuit.ActiveBus.VMagAngle
        if len(vmag) >= 1 and kv > 0:
            vpu = vmag[0] / (kv * 1000)
            flag = " !" if vpu > 1.050 else ("  " if vpu >= 0.921 else " v")
            print(f"  {vpu:.4f}{flag}     ", end="")
            if vpu > hora_pico_vmax[alvo][1]:
                hora_pico_vmax[alvo] = (h+1, vpu)
        else:
            print(f"  {'—':>14}", end="")
    print(f"  {p_gd:>12.1f}")

print(f"\n  Legenda: ! = faixa crítica (>1,050 pu)  v = faixa precária (<0,921 pu)")

# ===========================================================================
# 3. CAUSA: CORRELAÇÃO COM GD
# ===========================================================================
print(f"\n{'─'*70}")
print("3. CORRELAÇÃO SOBRETENSÃO × GERAÇÃO FOTOVOLTAICA")
print("─"*70)

for alvo, (h_pico, v_pico) in hora_pico_vmax.items():
    print(f"\n  {alvo}: tensão máxima = {v_pico:.4f} pu na hora {h_pico}")

# Verifica se há GD no mesmo ramal dos barramentos com sobretensão
print(f"\n  PVSystems próximos aos barramentos com violação:")
circuit = carregar(1.0)

# BFS a partir de cada barramento alvo para encontrar PVSystems a 3 saltos
from collections import deque

grafo_bt = {}
circuit.SetActiveClass("Line")
idx = circuit.Lines.First
while idx > 0:
    b1 = circuit.Lines.Bus1.split(".")[0]
    b2 = circuit.Lines.Bus2.split(".")[0]
    if b1 not in grafo_bt: grafo_bt[b1] = []
    if b2 not in grafo_bt: grafo_bt[b2] = []
    grafo_bt[b1].append(b2)
    grafo_bt[b2].append(b1)
    idx = circuit.Lines.Next

# Coleta posição de todos os PVSystems
pv_por_bus = {}
circuit.SetActiveClass("PVSystem")
idx = circuit.ActiveClass.First
while idx > 0:
    bus_pv = circuit.ActiveCktElement.BusNames[0].split(".")[0]
    nome   = circuit.ActiveClass.Name
    # Usa API Python para evitar problema de pontos no nome
    pmpp = circuit.PVSystems.Pmpp
    if bus_pv not in pv_por_bus:
        pv_por_bus[bus_pv] = []
    pv_por_bus[bus_pv].append((nome, pmpp))
    idx = circuit.ActiveClass.Next

for alvo in ALVOS[:2]:  # só os críticos
    vizinhos = set()
    fila = deque([(alvo, 0)])
    visitados = {alvo}
    while fila:
        bus, dist = fila.popleft()
        if dist <= 4:
            vizinhos.add(bus)
            for viz in grafo_bt.get(bus, []):
                if viz not in visitados:
                    visitados.add(viz)
                    fila.append((viz, dist+1))

    pvs_proximos = [(b, pvs) for b, pvs in pv_por_bus.items() if b in vizinhos]
    if pvs_proximos:
        print(f"\n  PVSystems a até 4 saltos de {alvo}:")
        for bus_pv, pvs in pvs_proximos:
            for nome, pmpp in pvs:
                print(f"    PVSystem.{nome}  bus={bus_pv}  Pmpp={pmpp:.1f} kW")
    else:
        print(f"\n  {alvo}: nenhum PVSystem nos 4 barramentos vizinhos")

# ===========================================================================
# 4. TESTE: SOBRETENSÃO SEM GD
# ===========================================================================
print(f"\n{'─'*70}")
print("4. TESTE: TENSÃO NOS MESMOS BARRAMENTOS SEM GD")
print("─"*70)

circuit_sem_gd = carregar(1.0)
dss.Text.Command = "Disable PVSystem.*"

print(f"\n  {'Hora':>4}", end="")
for alvo in ALVOS:
    print(f"  {alvo:>14}", end="")
print()
print(f"  {'-'*62}")

for h in range(24):
    circuit_sem_gd.Solution.Solve()
    print(f"  {h+1:>4}", end="")
    for alvo in ALVOS:
        circuit_sem_gd.SetActiveBus(alvo)
        kv   = circuit_sem_gd.ActiveBus.kVBase
        vmag = circuit_sem_gd.ActiveBus.VMagAngle
        if len(vmag) >= 1 and kv > 0:
            vpu = vmag[0] / (kv * 1000)
            flag = " !" if vpu > 1.050 else "  "
            print(f"  {vpu:.4f}{flag}     ", end="")
        else:
            print(f"  {'—':>14}", end="")
    print()

# ===========================================================================
# 5. MITIGAÇÃO: FP 0,95 vs FP 1,0 nos barramentos críticos
# ===========================================================================
print(f"\n{'─'*70}")
print("5. MITIGAÇÃO — IMPACTO DO FP NOS BARRAMENTOS COM SOBRETENSÃO")
print("─"*70)

print(f"\n  {'FP':>6} {'bt56881 Vmax':>14} {'uc1607347 Vmax':>16} {'Perdas kWh':>11}")
print(f"  {'-'*52}")

for pf in [0.90, 0.92, 0.95, 1.00]:
    circuit = carregar(1.0)
    idx = circuit.PVSystems.First
    while idx > 0:
        circuit.PVSystems.PF = pf
        idx = circuit.PVSystems.Next

    vmax = {a: 0.0 for a in ALVOS[:2]}
    perdas = 0.0
    for h in range(24):
        circuit.Solution.Solve()
        perdas += circuit.Losses[0] / 1000.0
        for alvo in ALVOS[:2]:
            circuit.SetActiveBus(alvo)
            kv   = circuit.ActiveBus.kVBase
            vmag = circuit.ActiveBus.VMagAngle
            if len(vmag) >= 1 and kv > 0:
                vpu = vmag[0] / (kv * 1000)
                vmax[alvo] = max(vmax[alvo], vpu)

    flag1 = " !" if vmax["bt56881"]    > 1.050 else "  "
    flag2 = " !" if vmax["uc1607347"] > 1.050 else "  "
    print(f"  {pf:>6.2f} {vmax['bt56881']:>12.4f}{flag1} {vmax['uc1607347']:>14.4f}{flag2} {perdas:>11.1f}")

print(f"\n  Legenda: ! = ainda em faixa crítica (>1,050 pu)")

print(f"\n{'='*70}")
print("CONCLUSÃO")
print("="*70)
print(f"""
  Os barramentos bt56881 e uc1607347 apresentam sobretensão (DRC > 0%)
  no caso base. A investigação determina se a causa é a GD fotovoltaica
  ou outro fator estrutural da rede.

  Se a sobretensão desaparecer sem GD (seção 4): causa confirmada como GD.
    → Recomendação: ajuste de FP nos inversores para reduzir injeção de
      reativo nos ramais afetados. FP 0,95 pode ser suficiente.

  Se a sobretensão persistir sem GD: causa estrutural (tap de trafo ou
  configuração do modelo).
    → Recomendação: verificar configuração do transformador do ramal e
      reportar ao professor como possível inconsistência no modelo.

  PRODIST Tabela 5 — BT 380/220V:
    Faixa adequada: 0,921–1,050 pu
    Faixa precária: 1,050–1,061 pu (DRP — compensação k1=3)
    Faixa crítica : >1,061 pu    (DRC — compensação k2=7)
""")
