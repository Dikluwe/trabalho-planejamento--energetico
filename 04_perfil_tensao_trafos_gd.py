# analise_complementar.py
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dss import dss

MASTER = str(HERE / "Master.dss")

def carregar(loadmult=1.0):
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{MASTER}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    dss.Text.Command = f"Set LoadMult={loadmult}"
    return dss.ActiveCircuit

# ===========================================================================
# 1. PERFIL DE TENSÃO
# ===========================================================================
print("\n" + "="*70)
print("1. PERFIL DE TENSÃO — CASO BASE (Ano 1, LoadMult=1.0)")
print("="*70)

circuit = carregar(1.0)
all_bus_names = list(circuit.AllBusNames)

v_min_bus = {}  # {nome: (vpu_min, kv_base)}
v_max_bus = {}

for h in range(24):
    circuit.Solution.Solve()
    for nome in all_bus_names:
        circuit.SetActiveBus(nome)
        kv = circuit.ActiveBus.kVBase
        if kv <= 0:
            continue
        vmag = circuit.ActiveBus.VMagAngle
        if len(vmag) < 1:
            continue
        # VMagAngle[0] é tensão de fase em Volts
        # Para sistemas trifásicos: kVBase é tensão de linha → fase = kVBase/√3
        # Para sistemas monofásicos: kVBase é tensão de fase diretamente
        num_nodes = circuit.ActiveBus.NumNodes
        if num_nodes >= 3:
            v_base_v = kv * 1000  # kVBase já é tensão de fase
        else:
            v_base_v = kv * 1000
        v_pu = vmag[0] / v_base_v
        # Ignora barramentos sem carga real (tensão exatamente zero)
        if v_pu < 0.01:
            continue
        if nome not in v_min_bus:
            v_min_bus[nome] = (v_pu, kv, num_nodes)
            v_max_bus[nome] = (v_pu, kv, num_nodes)
        else:
            if v_pu < v_min_bus[nome][0]:
                v_min_bus[nome] = (v_pu, kv, num_nodes)
            if v_pu > v_max_bus[nome][0]:
                v_max_bus[nome] = (v_pu, kv, num_nodes)

mt_buses = {k: v for k, v in v_min_bus.items() if v[1] > 1.0}
bt_buses = {k: v for k, v in v_min_bus.items() if 0.05 < v[1] <= 1.0}

print(f"\nBarramentos MT com tensão mínima abaixo de 0,95 pu:")
criticos_mt = [(k, v) for k, v in mt_buses.items() if v[0] < 0.95]
if criticos_mt:
    criticos_mt.sort(key=lambda x: x[1][0])
    for nome, (vpu, kv, nn) in criticos_mt[:20]:
        print(f"  {nome:<25} {kv:>8.3f} kV  Vmin={vpu:.4f} pu")
else:
    vmin_mt = min(mt_buses.items(), key=lambda x: x[1][0])
    print(f"  Nenhum. Tensão mínima MT: {vmin_mt[0]} = {vmin_mt[1][0]:.4f} pu")

print(f"\nEstatísticas MT ({len(mt_buses)} barramentos):")
print(f"  Tensão mínima : {min(v[0] for v in mt_buses.values()):.4f} pu")
print(f"  Tensão máxima : {max(v[0] for v in mt_buses.values()):.4f} pu")
print(f"  Tensão média  : {sum(v[0] for v in mt_buses.values())/len(mt_buses):.4f} pu")

print(f"\nBarramentos BT com tensão mínima abaixo de 0,921 pu (faixa precária PRODIST):")
criticos_bt = [(k, v) for k, v in bt_buses.items() if v[0] < 0.921]
criticos_bt.sort(key=lambda x: x[1][0])
print(f"  Total em faixa precária ou crítica: {len(criticos_bt)} de {len(bt_buses)} barramentos BT")
for nome, (vpu, kv, nn) in criticos_bt[:20]:
    faixa = "CRÍTICA" if vpu < 0.871 else "precária"
    print(f"  {nome:<25} {kv:>6.3f} kV  {nn} fios  Vmin={vpu:.4f} pu  [{faixa}]")

print(f"\nEstatísticas BT ({len(bt_buses)} barramentos):")
print(f"  Tensão mínima : {min(v[0] for v in bt_buses.values()):.4f} pu")
print(f"  Tensão máxima : {max(v[0] for v in bt_buses.values()):.4f} pu")
print(f"  Tensão média  : {sum(v[0] for v in bt_buses.values())/len(bt_buses):.4f} pu")

# ===========================================================================
# 2. CARREGAMENTO DOS TRANSFORMADORES
# ===========================================================================
print("\n" + "="*70)
print("2. CARREGAMENTO DOS TRANSFORMADORES — ANOS 1, 2 e 3")
print("="*70)

# Lê kVA de cada trafo no caso base
circuit = carregar(1.0)
kva_trafo = {}
circuit.SetActiveClass("Transformer")
trafos = circuit.Transformers
idx = trafos.First
while idx > 0:
    kva_trafo[trafos.Name] = trafos.kVA
    idx = trafos.Next

resultado_trafos = {}

for ano, mult in [(1, 1.0), (2, 1.1), (3, 1.2)]:
    circuit = carregar(mult)
    trafo_max = {}
    for h in range(24):
        circuit.Solution.Solve()
        circuit.SetActiveClass("Transformer")
        trafos = circuit.Transformers
        idx = trafos.First
        while idx > 0:
            nome = trafos.Name
            kva  = kva_trafo.get(nome, trafos.kVA)
            if kva > 0:
                circuit.SetActiveElement(f"Transformer.{nome}")
                powers = circuit.ActiveCktElement.Powers
                n = circuit.ActiveCktElement.NumPhases
                if len(powers) >= n * 2:
                    p = sum(powers[0:n*2:2])
                    q = sum(powers[1:n*2+1:2])
                    s = (p**2 + q**2)**0.5
                    pct = 100 * s / kva
                    trafo_max[nome] = max(trafo_max.get(nome, 0), pct)
            idx = trafos.Next
    for nome, pct in trafo_max.items():
        if nome not in resultado_trafos:
            resultado_trafos[nome] = {}
        resultado_trafos[nome][ano] = pct

print(f"\nTrafos com carregamento > 80% em algum ano:")
print(f"  {'Trafo':<25} {'kVA':>6} {'Ano1':>8} {'Ano2':>8} {'Ano3':>8}  Status")
print(f"  {'-'*72}")

alertas = []
for nome, anos in resultado_trafos.items():
    a1 = anos.get(1, 0)
    a2 = anos.get(2, 0)
    a3 = anos.get(3, 0)
    if max(a1, a2, a3) > 80:
        if a1 > 100: status = "SOBRECARGA Ano1"
        elif a2 > 100: status = "SOBRECARGA Ano2"
        elif a3 > 100: status = "SOBRECARGA Ano3"
        elif a3 > 80: status = "alerta Ano3"
        elif a2 > 80: status = "alerta Ano2"
        else: status = "alerta Ano1"
        alertas.append((nome, kva_trafo.get(nome, 0), a1, a2, a3, status))

alertas.sort(key=lambda x: x[4], reverse=True)
for nome, kva, a1, a2, a3, status in alertas:
    print(f"  {nome:<25} {kva:>6.0f} {a1:>8.1f} {a2:>8.1f} {a3:>8.1f}  {status}")

print(f"\n  Total trafos com alerta: {len(alertas)} de {len(resultado_trafos)}")

# ===========================================================================
# 3. IMPACTO DA GD FOTOVOLTAICA
# ===========================================================================
print("\n" + "="*70)
print("3. IMPACTO DA GD FOTOVOLTAICA — COM vs SEM GD (Ano 1)")
print("="*70)

# --- COM GD ---
circuit = carregar(1.0)
all_bus_names = list(circuit.AllBusNames)
h_perdas_com = {}
h_vmin_com   = {}

for h in range(24):
    circuit.Solution.Solve()
    h_perdas_com[h] = circuit.Losses[0] / 1000.0
    vmin = 999.0
    for bname in all_bus_names:
        circuit.SetActiveBus(bname)
        kv = circuit.ActiveBus.kVBase
        if 0.05 < kv <= 1.0:
            vmag = circuit.ActiveBus.VMagAngle
            if len(vmag) >= 1:
                nn = circuit.ActiveBus.NumNodes
                vbase_v = kv * 1000  # kVBase já é tensão de fase nesta rede
                vpu = vmag[0] / vbase_v
                if vpu > 0.01:
                    vmin = min(vmin, vpu)
    h_vmin_com[h] = vmin if vmin < 999 else 0.0

# --- SEM GD — desabilita via comando DSS direto ---
circuit = carregar(1.0)

# Desabilita generators
dss.Text.Command = "Disable Generator.*"
# Desabilita PVSystems
dss.Text.Command = "Disable PVSystem.*"

# Conta quantos foram desabilitados
n_gen = 0
circuit.SetActiveClass("Generator")
idx = circuit.Generators.First
while idx > 0:
    n_gen += 1
    idx = circuit.Generators.Next

n_pv = 0
circuit.SetActiveClass("PVSystem")
idx = circuit.ActiveClass.First
while idx > 0:
    n_pv += 1
    idx = circuit.ActiveClass.Next

print(f"\n  Generators desabilitados: {n_gen}")
print(f"  PVSystems desabilitados : {n_pv}")

h_perdas_sem = {}
h_vmin_sem   = {}

for h in range(24):
    circuit.Solution.Solve()
    h_perdas_sem[h] = circuit.Losses[0] / 1000.0
    vmin = 999.0
    for bname in all_bus_names:
        circuit.SetActiveBus(bname)
        kv = circuit.ActiveBus.kVBase
        if 0.05 < kv <= 1.0:
            vmag = circuit.ActiveBus.VMagAngle
            if len(vmag) >= 1:
                nn = circuit.ActiveBus.NumNodes
                vbase_v = kv * 1000  # kVBase já é tensão de fase nesta rede
                vpu = vmag[0] / vbase_v
                if vpu > 0.01:
                    vmin = min(vmin, vpu)
    h_vmin_sem[h] = vmin if vmin < 999 else 0.0

print(f"\n  {'Hora':>4} {'Perd c/GD':>10} {'Perd s/GD':>10} {'Delta':>8} {'Vmin c/GD':>10} {'Vmin s/GD':>10}")
print(f"  {'-'*58}")

delta_total = 0.0
for h in range(24):
    delta = h_perdas_sem[h] - h_perdas_com[h]
    delta_total += delta
    print(f"  {h+1:>4} {h_perdas_com[h]:>10.2f} {h_perdas_sem[h]:>10.2f} {delta:>8.2f} {h_vmin_com[h]:>10.4f} {h_vmin_sem[h]:>10.4f}")

eco = delta_total * 365 / 1000 * 35
print(f"\n  Redução de perdas c/GD vs s/GD    : {delta_total:.2f} kW/dia")
print(f"  Redução de perdas anual           : {delta_total*365/1000:.2f} MWh/ano")
print(f"  Valor da GD para a rede (35 USD): USD {eco:.2f}/ano")
print("="*70)
