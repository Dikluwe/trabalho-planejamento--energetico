# 09_ranking_gd.py
# Ranking dos 23 PVSystems por impacto na rede
# Métricas: sobretensão local, contribuição para perdas, qualidade de posicionamento

import sys
from pathlib import Path
from collections import deque
import json

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

with open(HERE / "parametros.json", "r") as f:
    config = json.load(f)
MASTER = str(HERE / config["caminhos"]["dss_file"])

from dss import dss

def carregar(loadmult=1.0, cmds=None):
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{MASTER}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    dss.Text.Command = f"Set LoadMult={loadmult}"
    if cmds:
        for c in cmds: dss.Text.Command = c
    return dss.ActiveCircuit

print("\n" + "="*70)
print("[09.01] RANKING DOS PVSystems POR IMPACTO NA REDE")
print("="*70)

# ---------------------------------------------------------------------------
# PASSO 1 — Inventário de todos os PVSystems
# ---------------------------------------------------------------------------
circuit = carregar(1.0)

pv_info = {}  # {nome: {bus, pmpp, kva, carga_local_kw, ratio}}

# Coleta info de cada PVSystem
idx = circuit.PVSystems.First
while idx > 0:
    nome   = circuit.PVSystems.Name
    bus_pv = circuit.ActiveCktElement.BusNames[0].split(".")[0]
    pmpp   = circuit.PVSystems.Pmpp
    kva    = circuit.PVSystems.kVArated
    pv_info[nome] = {
        "bus":  bus_pv,
        "pmpp": pmpp,
        "kva":  kva,
    }
    idx = circuit.PVSystems.Next

# Coleta carga local por barramento (cargas diretamente conectadas)
carga_por_bus = {}
loads = circuit.Loads
idx = loads.First
while idx > 0:
    circuit.SetActiveElement(f"Load.{loads.Name}")
    bus = circuit.ActiveCktElement.BusNames[0].split(".")[0]
    kw  = loads.kW
    if bus not in carga_por_bus:
        carga_por_bus[bus] = 0.0
    carga_por_bus[bus] += kw
    idx = loads.Next

# Carga acessível a até N saltos via BFS
grafo = {}
circuit.SetActiveClass("Line")
idx = circuit.Lines.First
while idx > 0:
    if not circuit.Lines.IsSwitch:
        b1 = circuit.Lines.Bus1.split(".")[0]
        b2 = circuit.Lines.Bus2.split(".")[0]
        if b1 not in grafo: grafo[b1] = []
        if b2 not in grafo: grafo[b2] = []
        grafo[b1].append(b2)
        grafo[b2].append(b1)
    idx = circuit.Lines.Next

def carga_vizinhanca(bus_raiz, n_saltos=3):
    """Soma de carga nos barramentos a até n_saltos do bus_raiz."""
    visitados = {bus_raiz}
    fila = deque([(bus_raiz, 0)])
    total = carga_por_bus.get(bus_raiz, 0.0)
    while fila:
        bus, dist = fila.popleft()
        if dist < n_saltos:
            for viz in grafo.get(bus, []):
                if viz not in visitados:
                    visitados.add(viz)
                    fila.append((viz, dist + 1))
                    total += carga_por_bus.get(viz, 0.0)
    return total

# Calcula ratio GD/carga para cada PVSystem
for nome, info in pv_info.items():
    carga_local  = carga_por_bus.get(info["bus"], 0.0)
    carga_viz3   = carga_vizinhanca(info["bus"], 3)
    carga_viz5   = carga_vizinhanca(info["bus"], 5)
    ratio_local  = info["pmpp"] / carga_local if carga_local > 0 else 999.0
    ratio_viz3   = info["pmpp"] / carga_viz3  if carga_viz3  > 0 else 999.0
    info["carga_local"] = carga_local
    info["carga_viz3"]  = carga_viz3
    info["carga_viz5"]  = carga_viz5
    info["ratio_local"] = ratio_local
    info["ratio_viz3"]  = ratio_viz3

# ---------------------------------------------------------------------------
# PASSO 2 — Impacto individual: tensão máxima com e sem cada PVSystem
# ---------------------------------------------------------------------------
print("\nColetando tensão máxima com e sem cada PVSystem...")
print("(23 simulações de 24h — pode demorar alguns minutos)\n")

# Caso base — tensão máxima global diária
circuit = carregar(1.0)
vmax_base_por_bus = {}
for h in range(24):
    circuit.Solution.Solve()
    for bname in circuit.AllBusNames:
        circuit.SetActiveBus(bname)
        kv = circuit.ActiveBus.kVBase
        if kv > 0.05:
            vmag = circuit.ActiveBus.VMagAngle
            if len(vmag) >= 1:
                # kVBase em ambos MT e BT é referência de fase
                # VMagAngle[0] é tensão de fase em Volts
                # Para MT: VMag/kVBase*1000 ≈ 0.98-1.02 pu (correto)
                vpu = vmag[0] / (kv * 1000)
                if 0.5 < vpu < 1.5:
                    if vpu > vmax_base_por_bus.get(bname, 0):
                        vmax_base_por_bus[bname] = vpu

perdas_base = 0.0
circuit = carregar(1.0)
for h in range(24):
    circuit.Solution.Solve()
    perdas_base += circuit.Losses[0] / 1000.0

# Para cada PVSystem: desabilita e mede impacto
impacto = {}
nomes_pv = list(pv_info.keys())

for i, nome in enumerate(nomes_pv):
    print(f"  [{i+1:>2}/{len(nomes_pv)}] PVSystem.{nome[:30]}")

    # Desabilita este PVSystem
    circuit = carregar(1.0)
    idx = circuit.PVSystems.First
    while idx > 0:
        if circuit.PVSystems.Name == nome:
            circuit.PVSystems.kVArated = 0.001  # desliga efetivamente
            circuit.PVSystems.Pmpp = 0.001
        idx = circuit.PVSystems.Next

    perdas_sem = 0.0
    vmax_bus_pv = 0.0
    bus_pv = pv_info[nome]["bus"]

    for h in range(24):
        circuit.Solution.Solve()
        perdas_sem += circuit.Losses[0] / 1000.0

        # Tensão no barramento do PVSystem
        circuit.SetActiveBus(bus_pv)
        kv = circuit.ActiveBus.kVBase
        if kv > 0:
            vmag = circuit.ActiveBus.VMagAngle
            if len(vmag) >= 1:
                vpu = vmag[0] / (kv * 1000)
                if 0.5 < vpu < 1.5:
                    vmax_bus_pv = max(vmax_bus_pv, vpu)

    delta_perdas = perdas_sem - perdas_base  # positivo = GD reduzia perdas
    vmax_com = vmax_base_por_bus.get(bus_pv, 0)
    delta_v   = vmax_com - vmax_bus_pv       # positivo = GD causava sobretensão

    impacto[nome] = {
        "delta_perdas": delta_perdas,  # kWh/dia que a GD salva (negativo = piora)
        "vmax_com":     vmax_com,
        "vmax_sem":     vmax_bus_pv,
        "delta_v":      delta_v,       # redução de tensão ao remover a GD
    }

# ---------------------------------------------------------------------------
# PASSO 3 — RANKING
# ---------------------------------------------------------------------------
print(f"\n{'='*70}")
print("RANKING — POSICIONAMENTO DOS PVSystems (melhor → pior)")
print(f"{'='*70}")

# Score: penaliza sobretensão, premia redução de perdas
# Score = -delta_perdas_norm + delta_v_norm × 10 (sobretensão pesa mais)
max_dp = max(abs(v["delta_perdas"]) for v in impacto.values()) or 1
max_dv = max(abs(v["delta_v"])      for v in impacto.values()) or 1

scored = []
for nome, info in pv_info.items():
    imp = impacto[nome]
    score_perdas = -imp["delta_perdas"] / max_dp      # GD que reduz perdas → score positivo
    score_tensao = -imp["delta_v"]      / max_dv * 10 # GD que causa sobretensão → score negativo
    score_total  = score_perdas + score_tensao
    scored.append((nome, info, imp, score_total))

scored.sort(key=lambda x: x[3], reverse=True)

print(f"\n  {'#':>3} {'PVSystem':<28} {'Pmpp':>6} {'Carga viz3':>11} {'Ratio':>7} "
      f"{'Vmax c/GD':>10} {'ΔV':>8} {'ΔPerd':>9} {'Score':>7}")
print(f"  {'-'*98}")

for rank, (nome, info, imp, score) in enumerate(scored, 1):
    ratio = info["ratio_viz3"]
    ratio_str = f"{ratio:.1f}×" if ratio < 100 else ">99×"
    qualidade = "✓ bom" if score > 0 else ("~ ok" if score > -2 else "✗ ruim")
    print(f"  {rank:>3} {nome[:28]:<28} {info['pmpp']:>6.0f} "
          f"{info['carga_viz3']:>11.1f} {ratio_str:>7} "
          f"{imp['vmax_com']:>10.4f} {imp['delta_v']:>+8.4f} "
          f"{imp['delta_perdas']:>+9.2f} {score:>7.2f}  {qualidade}")

print(f"\n  Colunas:")
print(f"  Pmpp      = potência de pico da GD (kW)")
print(f"  Carga viz3 = soma de carga nos 3 barramentos vizinhos (kW)")
print(f"  Ratio     = Pmpp / carga_viz3 (ideal < 2×)")
print(f"  Vmax c/GD = tensão máxima no barramento da GD com geração")
print(f"  ΔV        = quanto a GD eleva a tensão (positivo = piora)")
print(f"  ΔPerd     = variação de perdas ao remover a GD (negativo = GD ajuda)")
print(f"  Score     = métrica combinada (maior = melhor posicionamento)")

# Resumo
n_bom   = sum(1 for _, _, _, s in scored if s > 0)
n_ok    = sum(1 for _, _, _, s in scored if -2 < s <= 0)
n_ruim  = sum(1 for _, _, _, s in scored if s <= -2)
pmpp_total = sum(info["pmpp"] for _, info, _, _ in scored)

print(f"\n{'='*70}")
print(f"[09.02] SÍNTESE")
print(f"{'='*70}")
print(f"\n  Total de PVSystems    : {len(scored)}")
print(f"  Potência total (Pmpp) : {pmpp_total:.0f} kW")
print(f"  Bem posicionados (✓)  : {n_bom} ({100*n_bom/len(scored):.0f}%)")
print(f"  Aceitáveis     (~)    : {n_ok}  ({100*n_ok/len(scored):.0f}%)")
print(f"  Mal posicionados (✗)  : {n_ruim} ({100*n_ruim/len(scored):.0f}%)")

# Piores casos
print(f"\n  Piores PVSystems (causam sobretensão ou pioram perdas):")
for nome, info, imp, score in scored[-5:]:
    print(f"    {nome[:35]:<35} Pmpp={info['pmpp']:.0f}kW  "
          f"carga_viz3={info['carga_viz3']:.1f}kW  "
          f"ratio={info['ratio_viz3']:.1f}×  Vmax={imp['vmax_com']:.4f}pu")

print(f"\n  Melhores PVSystems (bem integrados à rede):")
for nome, info, imp, score in scored[:5]:
    print(f"    {nome[:35]:<35} Pmpp={info['pmpp']:.0f}kW  "
          f"carga_viz3={info['carga_viz3']:.1f}kW  "
          f"ratio={info['ratio_viz3']:.1f}×  Vmax={imp['vmax_com']:.4f}pu")

print("="*70)
