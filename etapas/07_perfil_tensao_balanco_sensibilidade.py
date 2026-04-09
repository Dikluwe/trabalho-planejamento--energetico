# 07_perfil_tensao_balanco_sensibilidade.py
# 1. Perfil de tensão por distância elétrica da subestação
# 2. Balanço energético completo (GD vs carga vs perdas hora a hora)
# 3. Sensibilidade do VPL à taxa de desconto (10%, 14%, 18%)

import sys
import json
from pathlib import Path

# 1. Ajuste do PATH absoluto (Sempre no topo)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 2. Imports locais e dependências
from dss import dss

# 3. Uso do ROOT para acessar os arquivos na raiz do projeto
with open(ROOT / "parametros.json", "r", encoding="utf-8") as f:
    config = json.load(f)

MASTER = str(ROOT / config["caminhos"]["dss_file"])
CUSTO_PERDAS = config["economico"]["preco_compra_usd_mwh"]
TARIFA_VENDA = config["economico"]["tarifa_venda_usd_mwh"]
TUSD = config["economico"]["tusd_usd_mwh"]
VIDA_UTIL = 15

def carregar(loadmult=1.0, cmds=None):
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{MASTER}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    dss.Text.Command = f"Set LoadMult={loadmult}"
    if cmds:
        for c in cmds:
            dss.Text.Command = c
    return dss.ActiveCircuit


# ===========================================================================
# 1. PERFIL DE TENSÃO POR DISTÂNCIA ELÉTRICA
# ===========================================================================
print("\n" + "=" * 70)
print("[07.10] PERFIL DE TENSÃO POR DISTÂNCIA ELÉTRICA DA SUBESTAÇÃO")
print("=" * 70)

circuit = carregar(1.0)
all_bus_names = list(circuit.AllBusNames)

# Nota: a rede tem 2320 barramentos MT todos a 13,34 kV mas o grafo
# é desconexo a partir da linha de entrada — múltiplos ramais partem
# de pontos distintos. O perfil por distância elétrica não é viável
# via BFS simples. Usamos análise estatística por decil de tensão.

print(f"\n  Barramentos MT: 2320  (todos a 13,34 kV)")
print(f"  Barramentos BT: 844 (0,22 kV) + 30 (0,13 kV)")
print(f"  Comprimento total estimado: >50 km (rede rural extensa)")

# Coleta tensão mínima diária por barramento MT
v_mt = {}
v_bt = {}
circuit.Solution.dblHour = 0.0
for h in range(24):
    circuit.Solution.Solve()
    for nome in all_bus_names:
        circuit.SetActiveBus(nome)
        kv = circuit.ActiveBus.kVBase
        vmag = circuit.ActiveBus.VMagAngle
        if len(vmag) < 1 or kv <= 0:
            continue
        nn = circuit.ActiveBus.NumNodes
        vbase = (
            kv * 1000
        )  # kVBase já é tensão de fase nesta rede if nn >= 3 else kv * 1000
        vpu = vmag[0] / vbase
        if vpu < 0.01 or vpu > 1.2:
            continue
        if kv > 1.0:
            if nome not in v_mt or vpu < v_mt[nome]:
                v_mt[nome] = vpu
        elif kv > 0.05:
            if nome not in v_bt or vpu < v_bt[nome]:
                v_bt[nome] = vpu

# Estatísticas MT
vpus_mt = sorted(v_mt.values())
n = len(vpus_mt)
print(f"\n  Perfil de tensão MT ({n} barramentos com tensão válida):")
print(f"  {'Percentil':>10} {'Tensão (pu)':>12}")
print(f"  {'-' * 24}")
for pct in [0, 10, 25, 50, 75, 90, 95, 99, 100]:
    idx_p = min(int(pct / 100 * n), n - 1)
    print(f"  {pct:>9}%  {vpus_mt[idx_p]:>12.4f}")

# Barramentos críticos MT
criticos_mt = [(b, v) for b, v in v_mt.items() if v < 0.95]
print(f"\n  Barramentos MT abaixo de 0,95 pu: {len(criticos_mt)}")
if criticos_mt:
    criticos_mt.sort(key=lambda x: x[1])
    for b, v in criticos_mt[:10]:
        print(f"    {b:<25} {v:.4f} pu")

# Estatísticas BT
vpus_bt = sorted(v_bt.values())
nb = len(vpus_bt)
print(f"\n  Perfil de tensão BT ({nb} barramentos com tensão válida):")
print(f"  {'Percentil':>10} {'Tensão (pu)':>12}")
print(f"  {'-' * 24}")
for pct in [0, 10, 25, 50, 75, 90, 100]:
    idx_p = min(int(pct / 100 * nb), nb - 1)
    print(f"  {pct:>9}%  {vpus_bt[idx_p]:>12.4f}")

criticos_bt = [(b, v) for b, v in v_bt.items() if v < 0.921]
print(f"\n  Barramentos BT em faixa precária (<0,921 pu): {len(criticos_bt)}")
if criticos_bt:
    criticos_bt.sort(key=lambda x: x[1])
    for b, v in criticos_bt[:10]:
        faixa = "CRÍTICA" if v < 0.871 else "precária"
        print(f"    {b:<25} {v:.4f} pu  [{faixa}]")

# ===========================================================================
# 2. BALANÇO ENERGÉTICO HORA A HORA
# ===========================================================================
print(f"\n{'=' * 70}")
print("[07.11] BALANÇO ENERGÉTICO HORA A HORA — COM GD vs SEM GD (Ano 1)")
print("=" * 70)

# COM GD
circuit = carregar(1.0)
h_p_total = {}  # potência total fornecida pela subestação
h_p_gd = {}  # geração fotovoltaica total
h_perdas = {}  # perdas totais
h_p_carga = {}  # consumo total das cargas

circuit.Solution.dblHour = 0.0
for h in range(24):
    circuit.Solution.Solve()

    # Potência da fonte (subestação) — TotalPower inclui GD
    p_fonte = circuit.TotalPower[0]  # kW, positivo = saindo da fonte
    h_p_total[h] = abs(p_fonte)

    # Perdas
    h_perdas[h] = circuit.Losses[0] / 1000.0

    # Geração fotovoltaica total
    p_gd = 0.0
    circuit.SetActiveClass("PVSystem")
    idx = circuit.ActiveClass.First
    while idx > 0:
        powers = circuit.ActiveCktElement.Powers
        n = circuit.ActiveCktElement.NumPhases
        if len(powers) >= n * 2:
            p_gd += abs(sum(powers[0 : n * 2 : 2]))
        idx = circuit.ActiveClass.Next
    h_p_gd[h] = p_gd

    # Carga total = fonte + GD - perdas
    h_p_carga[h] = h_p_total[h] + h_p_gd[h] - h_perdas[h]

print(
    f"\n  {'Hora':>4} {'Subestação':>12} {'GD (kW)':>9} {'Perdas':>8} "
    f"{'Carga':>8} {'GD/Carga':>10} {'Fluxo':>8}"
)
print(f"  {'-' * 64}")

e_sub = e_gd = e_perd = e_carga = 0.0
horas_reverso = 0

circuit.Solution.dblHour = 0.0
for h in range(24):
    p_sub = h_p_total[h]
    p_gd = h_p_gd[h]
    p_perd = h_perdas[h]
    p_carg = h_p_carga[h]
    gd_pct = 100 * p_gd / p_carg if p_carg > 0 else 0
    # Fluxo reverso: GD > carga + perdas → subestação recebe
    reverso = p_gd > (p_carg + p_perd)
    fluxo = "←REVERSO" if reverso else "→normal"
    if reverso:
        horas_reverso += 1

    e_sub += p_sub
    e_gd += p_gd
    e_perd += p_perd
    e_carga += p_carg

    print(
        f"  {h + 1:>4} {p_sub:>12.1f} {p_gd:>9.1f} {p_perd:>8.2f} "
        f"{p_carg:>8.1f} {gd_pct:>9.1f}% {fluxo:>9}"
    )

print(f"  {'-' * 64}")
print(
    f"  {'TOTAL':>4} {e_sub:>12.1f} {e_gd:>9.1f} {e_perd:>8.2f} "
    f"{e_carga:>8.1f} {100 * e_gd / e_carga:>9.1f}%"
)

print(f"\n  Energia fornecida pela subestação: {e_sub:.1f} kWh/dia")
print(f"  Energia gerada pela GD           : {e_gd:.1f} kWh/dia")
print(f"  Perdas totais                    : {e_perd:.1f} kWh/dia")
print(f"  Consumo total das cargas         : {e_carga:.1f} kWh/dia")
print(f"  Participação da GD no consumo    : {100 * e_gd / e_carga:.1f}%")
print(f"  Horas com fluxo reverso          : {horas_reverso}/24")

# ===========================================================================
# 3. SENSIBILIDADE DO VPL À TAXA DE DESCONTO
# ===========================================================================
print(f"\n{'=' * 70}")
print("[07.12] SENSIBILIDADE DO VPL — TAXA DE DESCONTO")
print("=" * 70)

# Benefícios anuais calculados no main_trabalho (tap nos dois trafos)
# Ano 1: USD 970, Ano 2: USD 760, Ano 3: USD 794 (mensal × 12)
BEN = {1: 970.04 * 12 / 12, 2: 760.16 * 12 / 12, 3: 796.47 * 12 / 12}
CAPEX = config["alternativas"][1]["custo_inicial_usd"]

print(f"\n  Alternativa: Tap trf_6_4910a + trf_11_305a")
print(f"  CAPEX: USD {CAPEX:,.0f}")
print(
    f"  Benefícios anuais: Ano1={BEN[1]:,.0f}  Ano2={BEN[2]:,.0f}  Ano3={BEN[3]:,.0f}"
)

print(f"\n  {'Taxa':>8} {'VPL':>12} {'Atrativo':>10} {'Payback':>10}")
print(f"  {'-' * 44}")


def _find_tir(ben, capex, vida):
    for taxa in [x / 1000 for x in range(1, 1000)]:
        residual = capex * (vida - 3) / vida
        fluxos = [-capex, ben[1], ben[2], ben[3] + residual]
        vpl = sum(f / (1 + taxa) ** t for t, f in enumerate(fluxos))
        if vpl < 0:
            return taxa
    return 1.0


for taxa in [0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.25]:
    residual = CAPEX * (VIDA_UTIL - 3) / VIDA_UTIL
    fluxos = [-CAPEX, BEN[1], BEN[2], BEN[3] + residual]
    vpl = sum(f / (1 + taxa) ** t for t, f in enumerate(fluxos))
    atr = "SIM" if vpl > 0 else "NÃO"

    # Payback simples (sem desconto)
    acum = -CAPEX
    pb = ">"
    for ano in [1, 2, 3]:
        acum += BEN[ano]
        if acum >= 0:
            pb = f"{ano} ano{'s' if ano > 1 else ''}"
            break
    if pb == ">":
        pb = ">3 anos"

    print(f"  {taxa * 100:>7.0f}% {vpl:>12,.0f} {atr:>10} {pb:>10}")


tir = _find_tir(BEN, CAPEX, VIDA_UTIL)
print(f"\n  Conclusão: o tap nos dois trafos é atrativo para qualquer")
print(f"  taxa de desconto abaixo de {tir * 100:.0f}% (TIR aproximada).")
print(f"  TIR aproximada: {tir * 100:.0f}%")
print("=" * 70)
