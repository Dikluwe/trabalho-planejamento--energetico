# 04_pior_caso_duracao_degradacao.py
# 1. Pior caso diário (LoadMult no pico)
# 2. Curva de duração de carga dos trafos críticos
# 3. Horizonte com degradação da GD (0.7% ao ano)

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dss import dss

import json
with open(HERE / "parametros.json", "r") as f:
    config = json.load(f)

MASTER = str(HERE / config["caminhos"]["dss_file"])
DEGRADACAO_GD = config["simulacao"]["degradacao_gd"]
CRESCIMENTO_CARGA = config["simulacao"]["crescimento_carga"]
ANOS_SIMULACAO = config["simulacao"].get("vida_util_projeto", 3)
TRAFOS_CRITICOS = [config.get("graficos", {}).get("trafo_critico", "trf_6_4910a"), "trf_11_305a"]

def carregar(loadmult=1.0, gd_fator=1.0):
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{MASTER}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    dss.Text.Command = f"Set LoadMult={loadmult}"
    if gd_fator != 1.0:
        # Escala todos os PVSystems
        circuit = dss.ActiveCircuit
        circuit.SetActiveClass("PVSystem")
        idx = circuit.ActiveClass.First
        while idx > 0:
            nome = circuit.ActiveCktElement.Name.split(".")[1]
            dss.Text.Command = f"Edit PVSystem.{nome} irradiance={gd_fator:.4f}"
            idx = circuit.ActiveClass.Next
    return dss.ActiveCircuit

def v_pu_bus(circuit, nome):
    circuit.SetActiveBus(nome)
    kv = circuit.ActiveBus.kVBase
    if kv <= 0: return None
    vmag = circuit.ActiveBus.VMagAngle
    if len(vmag) < 1: return None
    nn = circuit.ActiveBus.NumNodes
    vbase_v = kv * 1000  # kVBase já é tensão de fase nesta rede
    vpu = vmag[0] / vbase_v
    return vpu if vpu > 0.01 else None

def trafo_loading(circuit, nome, kva):
    circuit.SetActiveElement(f"Transformer.{nome}")
    powers = circuit.ActiveCktElement.Powers
    n = circuit.ActiveCktElement.NumPhases
    if len(powers) < n * 2 or kva <= 0:
        return 0.0
    p = sum(powers[0:n*2:2])
    q = sum(powers[1:n*2+1:2])
    return 100 * (p**2 + q**2)**0.5 / kva

# Lê kVA dos trafos uma vez
circuit = carregar(1.0)
kva_trafo = {}
circuit.SetActiveClass("Transformer")
idx = circuit.Transformers.First
while idx > 0:
    kva_trafo[circuit.Transformers.Name] = circuit.Transformers.kVA
    idx = circuit.Transformers.Next

all_bus_names = list(circuit.AllBusNames)
bt_buses = []
for nome in all_bus_names:
    circuit.SetActiveBus(nome)
    kv = circuit.ActiveBus.kVBase
    if 0.05 < kv <= 1.0:
        bt_buses.append(nome)

# ===========================================================================
# [04.04] PIOR CASO DIÁRIO — hora de pico (LoadMult máximo do perfil)
# ===========================================================================
print("\n" + "="*70)
print("[04.04] PIOR CASO DIÁRIO — LoadMult no pico (hora 12, máximo do perfil)")
print("="*70)

# Descobre o LoadMult máximo do perfil de carga
circuit = carregar(1.0)
loadshape_max = 0.0
hora_pico = 0
for h in range(24):
    circuit.Solution.Solve()
    # Usa a potência total fornecida como proxy do mult efetivo
    p_total = abs(circuit.TotalPower[0])
    if p_total > loadshape_max:
        loadshape_max = p_total
        hora_pico = h + 1

print(f"\n  Hora de pico identificada: hora {hora_pico}")
print(f"  Potência total na hora de pico: {loadshape_max:.1f} kW")

# Roda apenas a hora de pico com LoadMult=1.0 fixo
# (simula toda a carga no pico simultâneo)
for ano in range(1, ANOS_SIMULACAO + 1):
    mult_carga = 1.0 + (ano - 1) * CRESCIMENTO_CARGA
    gd_fat     = max(0.5, 1.0 - (ano - 1) * DEGRADACAO_GD)
    circuit = carregar(mult_carga, gd_fat)
    # Avança até a hora de pico
    for h in range(hora_pico):
        circuit.Solution.Solve()

    # Carregamento dos trafos críticos
    pct_4910 = trafo_loading(circuit, TRAFOS_CRITICOS[0], kva_trafo.get(TRAFOS_CRITICOS[0], 30))
    pct_305  = trafo_loading(circuit, TRAFOS_CRITICOS[1], kva_trafo.get(TRAFOS_CRITICOS[1], 75))

    # Tensão mínima BT
    vmin = 999.0
    for bname in bt_buses:
        vpu = v_pu_bus(circuit, bname)
        if vpu and vpu < vmin:
            vmin = vpu

    # Linhas sobrecarregadas
    circuit.SetActiveClass("Line")
    lines = circuit.Lines
    n_over = 0
    idx = lines.First
    while idx > 0:
        if not lines.IsSwitch:
            circuit.SetActiveElement(f"Line.{lines.Name}")
            pcts = circuit.ActiveCktElement.NormalAmps
            if pcts > 0:
                currents = circuit.ActiveCktElement.CurrentsMagAng
                if len(currents) >= 2:
                    i_mag = currents[0]
                    if i_mag / pcts * 100 > 100:
                        n_over += 1
        idx = lines.Next

    gd_pct = (1 - gd_fat) * 100
    print(f"\n  Ano {ano} (carga ×{mult_carga}, GD -{gd_pct:.1f}%):")
    print(f"    {TRAFOS_CRITICOS[0]} : {pct_4910:.1f}%")
    print(f"    {TRAFOS_CRITICOS[1]} : {pct_305:.1f}%")
    print(f"    Vmin BT     : {vmin:.4f} pu")
    print(f"    Linhas >100%: {n_over}")

# ===========================================================================
# [04.05] CURVA DE DURAÇÃO DE CARGA — trafos críticos
# ===========================================================================
print("\n" + "="*70)
print(f"[04.05] CURVA DE DURAÇÃO DE CARGA — {', '.join(TRAFOS_CRITICOS)}")
print("="*70)

for trafo in TRAFOS_CRITICOS:
    kva = kva_trafo.get(trafo, 0)
    print(f"\n  {trafo} ({kva:.0f} kVA):")
    header = " ".join([f"Ano{a} h/ano" for a in range(1, ANOS_SIMULACAO + 1)])
    print(f"  {'Limiar':>8} {header}")
    print(f"  {'-'*(50 + (ANOS_SIMULACAO-3)*12)}")

    horas_por_ano = {}
    for ano in range(1, ANOS_SIMULACAO + 1):
        mult_carga = 1.0 + (ano - 1) * CRESCIMENTO_CARGA
        gd_fat     = max(0.5, 1.0 - (ano - 1) * DEGRADACAO_GD)
        circuit = carregar(mult_carga, gd_fat)
        carregamentos = []
        for h in range(24):
            circuit.Solution.Solve()
            pct = trafo_loading(circuit, trafo, kva)
            carregamentos.append(pct)
        horas_por_ano[ano] = carregamentos

    for limiar in [70, 80, 90, 100]:
        linha = f"  {limiar:>7}%"
        for ano in range(1, ANOS_SIMULACAO + 1):
            h_acima = sum(1 for p in horas_por_ano[ano] if p > limiar) * 365
            linha += f" {h_acima:>12}"
        print(linha)

# ===========================================================================
# [04.06] HORIZONTE COM DEGRADAÇÃO DA GD
# ===========================================================================
print("\n" + "="*70)
print(f"[04.06] HORIZONTE COM DEGRADAÇÃO DA GD ({DEGRADACAO_GD*100:.1f}%/ano)")
print("="*70)
print(f"\n  {'Ano':>4} {'Carga':>8} {'GD (%)':>8} {'trf_1 %':>12} {'trf_2 %':>11} {'Perdas kWh':>12} {'Vmin BT':>9}")
print(f"  {'-'*70}")

for ano in range(1, ANOS_SIMULACAO + 1):
    mult_carga = 1.0 + (ano - 1) * CRESCIMENTO_CARGA
    gd_fat     = 1.0 - (ano - 1) * DEGRADACAO_GD

    circuit = carregar(mult_carga, gd_fat)
    perdas_dia = 0.0
    pct_1_max = 0.0
    pct_2_max  = 0.0
    vmin_dia = 999.0

    for h in range(24):
        circuit.Solution.Solve()
        perdas_dia += circuit.Losses[0] / 1000.0

        p1 = trafo_loading(circuit, TRAFOS_CRITICOS[0], kva_trafo.get(TRAFOS_CRITICOS[0], 30))
        p2 = trafo_loading(circuit, TRAFOS_CRITICOS[1], kva_trafo.get(TRAFOS_CRITICOS[1], 75))
        pct_1_max = max(pct_1_max, p1)
        pct_2_max  = max(pct_2_max, p2)

        for bname in bt_buses:
            vpu = v_pu_bus(circuit, bname)
            if vpu and vpu < vmin_dia:
                vmin_dia = vpu

    gd_pct = gd_fat * 100
    print(f"  {ano:>4} {mult_carga:>8.1f} {gd_pct:>8.1f} {pct_1_max:>12.1f} {pct_2_max:>11.1f} {perdas_dia:>12.1f} {vmin_dia:>9.4f}")

print(f"\n  Degradação GD: {DEGRADACAO_GD*100:.1f}%/ano (painel cristalino típico)")
print(f"  Carga: +{CRESCIMENTO_CARGA*100:.1f}%/ano conforme enunciado")
print("="*70)
