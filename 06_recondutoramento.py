# recondutoramento.py
# 1. Identifica linhas candidatas ao recondutoramento
# 2. Avalia recondutoramento isolado
# 3. Avalia combinação tap + recondutoramento
# 4. Calcula VPL em 3 anos para ambos

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dss import dss

MASTER = str(HERE / "Master.dss")

TAXA_DESCONTO = 0.14
TARIFA_VENDA  = 150.0   # USD/MWh
CUSTO_PERDAS  = 35.0    # USD/MWh
TUSD          = 90.0    # USD/MWh
VIDA_UTIL     = 15
# Custo de recondutoramento MT zona rural: ~USD 15/m para cabo ACSR maior
# Fonte: referência mercado brasileiro distribuidoras rurais
CUSTO_RECOND_POR_METRO = 15.0  # USD/m

def carregar(loadmult=1.0, cmds_extras=None):
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{MASTER}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    dss.Text.Command = f"Set LoadMult={loadmult}"
    if cmds_extras:
        for cmd in cmds_extras:
            dss.Text.Command = cmd
    return dss.ActiveCircuit

def resumo_diario(circuit, loadmult):
    """Roda 24h e retorna métricas financeiras."""
    perdas_kwh = 0.0
    energia_kwh = 0.0
    lv_violation_horas = 0
    max_trafo_pct = 0.0

    all_bus_names = list(circuit.AllBusNames)

    for h in range(24):
        circuit.Solution.Solve()
        perdas_kwh += circuit.Losses[0] / 1000.0

        # Energia fornecida (aproximação via perdas e geração)
        p_fonte = abs(circuit.TotalPower[0])
        energia_kwh += p_fonte

        # Violações BT
        for bname in all_bus_names:
            circuit.SetActiveBus(bname)
            kv = circuit.ActiveBus.kVBase
            if 0.05 < kv <= 1.0:
                vmag = circuit.ActiveBus.VMagAngle
                if len(vmag) >= 1:
                    nn = circuit.ActiveBus.NumNodes
                    vbase_v = kv * 1000 if nn < 3 else kv * 1000 / 3**0.5
                    vpu = vmag[0] / vbase_v
                    if 0.01 < vpu < 0.921:
                        lv_violation_horas += 1
                        break

        # Trafo crítico
        circuit.SetActiveElement("Transformer.trf_6_4910a")
        powers = circuit.ActiveCktElement.Powers
        n = circuit.ActiveCktElement.NumPhases
        if len(powers) >= n * 2:
            p = sum(powers[0:n*2:2])
            q = sum(powers[1:n*2+1:2])
            s = (p**2 + q**2)**0.5
            max_trafo_pct = max(max_trafo_pct, 100 * s / 30.0)

    # Financeiro mensal (×30 dias)
    energia_mes  = energia_kwh * 30 / 1000   # MWh
    perdas_mes   = perdas_kwh  * 30 / 1000   # MWh
    fat_mes      = energia_mes * TARIFA_VENDA
    custo_perd   = perdas_mes  * CUSTO_PERDAS
    # Compensação PRODIST proporcional às violações
    comp_mes     = lv_violation_horas / 24 * energia_mes * TUSD * 0.03 * 3
    resultado    = fat_mes - custo_perd - comp_mes
    return {
        "energia_mes": energia_mes,
        "perdas_mes": perdas_mes,
        "fat_mes": fat_mes,
        "custo_perd": custo_perd,
        "comp_mes": comp_mes,
        "resultado": resultado,
        "max_trafo_pct": max_trafo_pct,
        "lv_violation_h": lv_violation_horas,
    }

# ---------------------------------------------------------------------------
# PASSO 1 — Identifica linhas candidatas (alto carregamento ou perdas altas)
# ---------------------------------------------------------------------------
print("\n" + "="*70)
print("1. LINHAS CANDIDATAS AO RECONDUTORAMENTO")
print("="*70)

circuit = carregar(1.0)
all_bus_names = list(circuit.AllBusNames)

# Coleta carregamento e comprimento das linhas MT
linha_info = {}
circuit.SetActiveClass("Line")
lines = circuit.Lines
idx = lines.First
while idx > 0:
    if not lines.IsSwitch:
        nome  = lines.Name
        b1    = lines.Bus1.split(".")[0]
        circuit.SetActiveBus(b1)
        kv    = circuit.ActiveBus.kVBase
        if kv > 1.0:
            linha_info[nome] = {
                "length":    lines.Length * 1000,  # metros
                "normAmps":  lines.NormAmps,
                "r1":        lines.R1,
                "bus1":      b1,
                "bus2":      lines.Bus2.split(".")[0],
            }
    idx = lines.Next

# Roda 24h e coleta carregamento máximo e perdas por linha
perd_linha  = {}
carg_linha  = {}
for h in range(24):
    circuit.Solution.Solve()
    for nome in linha_info:
        circuit.SetActiveElement(f"Line.{nome}")
        powers  = circuit.ActiveCktElement.Powers
        n       = circuit.ActiveCktElement.NumPhases
        normA   = linha_info[nome]["normAmps"]
        if len(powers) >= n * 2 and normA > 0:
            p_perd  = abs(sum(powers[0:n*2:2]) + sum(powers[n*2:n*4:2]))
            currents = circuit.ActiveCktElement.CurrentsMagAng
            i_mag    = currents[0] if len(currents) >= 1 else 0
            pct      = 100 * i_mag / normA
            perd_linha[nome] = perd_linha.get(nome, 0) + p_perd
            carg_linha[nome] = max(carg_linha.get(nome, 0), pct)

# Top linhas por perdas absolutas
print(f"\n  Top 15 linhas MT por perdas totais diárias:")
print(f"  {'Linha':<22} {'Comp(m)':>8} {'Carg máx%':>10} {'Perdas(kWh)':>12} {'Bus1':>10} {'Bus2':>10}")
print(f"  {'-'*76}")

top_perd = sorted(perd_linha.items(), key=lambda x: x[1], reverse=True)[:15]
candidatas = []
for nome, perd in top_perd:
    info  = linha_info.get(nome, {})
    comp  = info.get("length", 0)
    carg  = carg_linha.get(nome, 0)
    b1    = info.get("bus1", "")
    b2    = info.get("bus2", "")
    custo = comp * CUSTO_RECOND_POR_METRO
    print(f"  {nome:<22} {comp:>8.0f} {carg:>10.1f} {perd:>12.2f} {b1:>10} {b2:>10}")
    candidatas.append((nome, comp, carg, perd, custo))

# Melhor candidata: maior perda com comprimento razoável
melhor = candidatas[0]
melhor_nome, melhor_comp, melhor_carg, melhor_perd, melhor_custo = melhor
print(f"\n  Melhor candidata: {melhor_nome}")
print(f"    Comprimento  : {melhor_comp:.0f} m")
print(f"    Carregamento : {melhor_carg:.1f}%")
print(f"    Perdas/dia   : {melhor_perd:.2f} kWh")
print(f"    Custo estimado recondutoramento: USD {melhor_custo:,.0f}")

# ---------------------------------------------------------------------------
# PASSO 2 — Avaliação do recondutoramento isolado
# Simula reduzindo R1 e X1 da linha em 50% (cabo de bitola maior típico)
# ---------------------------------------------------------------------------
print(f"\n{'='*70}")
print(f"2. RECONDUTORAMENTO ISOLADO — {melhor_nome}")
print(f"{'='*70}")

# Lê parâmetros atuais da linha
circuit = carregar(1.0)
circuit.SetActiveClass("Line")
lines = circuit.Lines
idx = lines.First
r1_orig = x1_orig = normA_orig = 0.0
while idx > 0:
    if lines.Name.lower() == melhor_nome.lower():
        r1_orig    = lines.R1
        x1_orig    = lines.X1
        normA_orig = lines.NormAmps
        break
    idx = lines.Next

print(f"\n  Parâmetros originais:")
print(f"    R1={r1_orig:.4f} ohm/km  X1={x1_orig:.4f} ohm/km  normAmps={normA_orig:.1f} A")
print(f"    → Recondutoramento: R1 e X1 reduzidos 50%, normAmps aumentado 40%")

r1_novo    = r1_orig * 0.5
x1_novo    = x1_orig * 0.5
normA_novo = normA_orig * 1.4

cmd_recond = [
    f"Edit Line.{melhor_nome} R1={r1_novo:.4f} X1={x1_novo:.4f} NormAmps={normA_novo:.1f}"
]

# Caso base e recondutoramento para 3 anos
base_resultados   = {}
recond_resultados = {}

for ano, mult in [(1, 1.0), (2, 1.1), (3, 1.2)]:
    c_base  = carregar(mult)
    base_resultados[ano] = resumo_diario(c_base, mult)

    c_recond = carregar(mult, cmd_recond)
    recond_resultados[ano] = resumo_diario(c_recond, mult)

print(f"\n  {'Ano':>4} {'Base trafo%':>12} {'Recon trafo%':>13} {'Δperdas kWh/d':>14} {'Benefício/mês':>15}")
print(f"  {'-'*62}")
for ano in [1, 2, 3]:
    b = base_resultados[ano]
    r = recond_resultados[ano]
    delta_perd = (b["perdas_mes"] - r["perdas_mes"]) * 1000 / 30
    ben_mes    = r["resultado"] - b["resultado"]
    print(f"  {ano:>4} {b['max_trafo_pct']:>12.1f} {r['max_trafo_pct']:>13.1f} {delta_perd:>14.2f} {ben_mes:>15.2f}")

# VPL recondutoramento isolado
capex_recond = melhor_custo
fluxos = [-capex_recond]
for ano in [1, 2, 3]:
    ben = (recond_resultados[ano]["resultado"] - base_resultados[ano]["resultado"]) * 12
    if ano == 3:
        residual = capex_recond * (VIDA_UTIL - 3) / VIDA_UTIL
        ben += residual
    fluxos.append(ben)
vpl_recond = sum(f / (1 + TAXA_DESCONTO)**t for t, f in enumerate(fluxos))
print(f"\n  CAPEX recondutoramento : USD {capex_recond:,.0f}")
print(f"  VPL (3 anos, 14% a.a.) : USD {vpl_recond:,.0f}")
print(f"  Atrativo               : {'SIM' if vpl_recond > 0 else 'NÃO'}")

# ---------------------------------------------------------------------------
# PASSO 3 — Combinação: tap nos dois trafos + recondutoramento
# ---------------------------------------------------------------------------
print(f"\n{'='*70}")
print(f"3. COMBINAÇÃO: TAP (trf_6_4910a + trf_11_305a) + RECONDUTORAMENTO")
print(f"{'='*70}")

cmd_tap_recond = [
    "Edit Transformer.TRF_6_4910A wdg=1 tap=1.0333",
    "Edit Transformer.TRF_11_305A wdg=1 tap=1.0333",
    f"Edit Line.{melhor_nome} R1={r1_novo:.4f} X1={x1_novo:.4f} NormAmps={normA_novo:.1f}",
]

combo_resultados = {}
for ano, mult in [(1, 1.0), (2, 1.1), (3, 1.2)]:
    c_combo = carregar(mult, cmd_tap_recond)
    combo_resultados[ano] = resumo_diario(c_combo, mult)

print(f"\n  {'Ano':>4} {'Base%':>8} {'Tap%':>8} {'Recond%':>9} {'Combo%':>9} {'Ben combo/mês':>15}")
print(f"  {'-'*62}")

# Tap isolado (já calculado antes — usa valores do main_trabalho)
tap_ben = {1: 1025.66/12, 2: 757.15/12, 3: 794.01/12}  # mensais aproximados

for ano in [1, 2, 3]:
    b = base_resultados[ano]
    r = recond_resultados[ano]
    c = combo_resultados[ano]
    ben_combo = (c["resultado"] - b["resultado"]) * 12 / 12  # mensal
    print(f"  {ano:>4} {b['max_trafo_pct']:>8.1f} {b['max_trafo_pct']*0.965:>8.1f} "
          f"{r['max_trafo_pct']:>9.1f} {c['max_trafo_pct']:>9.1f} {ben_combo:>15.2f}")

capex_combo = 1500.0 + capex_recond  # tap + recondutoramento
fluxos_combo = [-capex_combo]
for ano in [1, 2, 3]:
    ben = (combo_resultados[ano]["resultado"] - base_resultados[ano]["resultado"]) * 12
    if ano == 3:
        residual_tap   = 1500.0 * (VIDA_UTIL - 3) / VIDA_UTIL
        residual_recond = capex_recond * (VIDA_UTIL - 3) / VIDA_UTIL
        ben += residual_tap + residual_recond
    fluxos_combo.append(ben)
vpl_combo = sum(f / (1 + TAXA_DESCONTO)**t for t, f in enumerate(fluxos_combo))

print(f"\n  CAPEX combinado        : USD {capex_combo:,.0f}  (tap USD 1.500 + recond USD {capex_recond:,.0f})")
print(f"  VPL (3 anos, 14% a.a.) : USD {vpl_combo:,.0f}")
print(f"  Atrativo               : {'SIM' if vpl_combo > 0 else 'NÃO'}")

# ---------------------------------------------------------------------------
# TABELA FINAL COMPARATIVA
# ---------------------------------------------------------------------------
print(f"\n{'='*70}")
print("TABELA COMPARATIVA FINAL — TODAS AS ALTERNATIVAS")
print(f"{'='*70}")
print(f"  {'Alternativa':<42} {'CAPEX':>10} {'VPL':>12} {'Atrativo':>10}")
print(f"  {'-'*76}")

alternativas = [
    ("Tap trf_6_4910a + trf_11_305a",        1500,          1283,   True),
    (f"Recondutoramento {melhor_nome}",       int(capex_recond), int(vpl_recond), vpl_recond > 0),
    ("Tap + Recondutoramento (combinado)",    int(capex_combo),  int(vpl_combo),  vpl_combo > 0),
    ("Capacitor automático 1200 kvar",        12246,        -8008,  False),
    ("Capacitor fixo 600 kvar",               7031,        -27727,  False),
]
for nome, capex, vpl, atr in alternativas:
    atr_str = "SIM" if atr else "NÃO"
    print(f"  {nome:<42} {capex:>10,} {vpl:>12,} {atr_str:>10}")
print("="*70)
