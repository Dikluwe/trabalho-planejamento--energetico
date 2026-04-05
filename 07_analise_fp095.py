# analise_fp095.py
# Análise financeira completa do ajuste de FP dos PVSystems de 0,92 para 0,95
# Medida operacional sem CAPEX — apenas reconfiguração dos inversores

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dss import dss

MASTER        = str(HERE / "Master.dss")
TAXA_DESCONTO = 0.14
CUSTO_PERDAS  = 35.0    # USD/MWh
TARIFA_VENDA  = 150.0   # USD/MWh
TUSD          = 90.0    # USD/MWh
VIDA_UTIL     = 15
DEGRADACAO_GD = 0.007

def carregar(loadmult=1.0, cmds=None):
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{MASTER}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    dss.Text.Command = f"Set LoadMult={loadmult}"
    if cmds:
        for c in cmds: dss.Text.Command = c
    return dss.ActiveCircuit

def set_fp(circuit, pf):
    idx = circuit.PVSystems.First
    while idx > 0:
        circuit.PVSystems.PF = pf
        idx = circuit.PVSystems.Next

def set_gd_degradacao(circuit, ano):
    gd_f = max(0.5, 1.0 - (ano - 1) * DEGRADACAO_GD)
    idx = circuit.PVSystems.First
    while idx > 0:
        circuit.PVSystems.Irradiance = gd_f
        idx = circuit.PVSystems.Next

def metricas_financeiras(circuit):
    """Roda 24h e retorna métricas financeiras mensais."""
    perdas_kwh  = 0.0
    energia_kwh = 0.0
    n_viol_bt   = 0
    all_bus     = list(circuit.AllBusNames)

    for h in range(24):
        circuit.Solution.Solve()
        perdas_kwh  += circuit.Losses[0] / 1000.0
        energia_kwh += abs(circuit.TotalPower[0])

        # Violações BT (kVBase já é tensão de fase nesta rede)
        tem_viol = False
        for bname in all_bus:
            circuit.SetActiveBus(bname)
            kv = circuit.ActiveBus.kVBase
            if 0.05 < kv <= 1.0:
                vmag = circuit.ActiveBus.VMagAngle
                if len(vmag) >= 1:
                    vpu = vmag[0] / (kv * 1000)
                    if 0.01 < vpu < 0.921:
                        tem_viol = True
                        break
        if tem_viol:
            n_viol_bt += 1

    # Financeiro mensal (×30 dias)
    energia_mes = energia_kwh * 30 / 1000  # MWh
    perdas_mes  = perdas_kwh  * 30 / 1000  # MWh
    fat_mes     = energia_mes * TARIFA_VENDA
    custo_perd  = perdas_mes  * CUSTO_PERDAS
    comp_mes    = (n_viol_bt / 24) * energia_mes * TUSD * 0.03 * 3
    resultado   = fat_mes - custo_perd - comp_mes

    return {
        "perdas_mes":  perdas_mes,
        "energia_mes": energia_mes,
        "fat_mes":     fat_mes,
        "custo_perd":  custo_perd,
        "comp_mes":    comp_mes,
        "resultado":   resultado,
        "n_viol_h":    n_viol_bt,
    }

print("\n" + "="*70)
print("ANÁLISE FINANCEIRA — AJUSTE DE FP: 0,92 → 0,95 NOS PVSYSTEMS")
print("="*70)
print(f"\n  Medida: reconfiguração dos inversores via comando de despacho")
print(f"  CAPEX : USD 0 (sem hardware adicional)")
print(f"  Vida útil considerada: {VIDA_UTIL} anos")
print(f"  Taxa de desconto: {TAXA_DESCONTO*100:.0f}% a.a.")

# ---------------------------------------------------------------------------
# Compara FP 0,92 vs FP 0,95 nos 3 anos
# ---------------------------------------------------------------------------
print(f"\n{'─'*70}")
print(f"  COMPARAÇÃO ANUAL — FP 0,92 (atual) vs FP 0,95 (proposto)")
print(f"{'─'*70}")
print(f"\n  {'':>4} {'Métrica':<28} {'FP 0,92':>12} {'FP 0,95':>12} {'Δ mensal':>10}")
print(f"  {'-'*68}")

beneficios_anuais = {}

for ano, mult in [(1, 1.0), (2, 1.1), (3, 1.2)]:
    # FP 0,92 (caso base)
    c092 = carregar(mult)
    set_fp(c092, 0.92)
    set_gd_degradacao(c092, ano)
    m092 = metricas_financeiras(c092)

    # FP 0,95
    c095 = carregar(mult)
    set_fp(c095, 0.95)
    set_gd_degradacao(c095, ano)
    m095 = metricas_financeiras(c095)

    # Benefício real: redução de perdas + redução de compensação PRODIST
    # O faturamento não muda — a cooperativa vende a mesma energia às cargas
    delta_perd = m092["perdas_mes"] - m095["perdas_mes"]   # MWh/mês poupados
    delta_comp = m092["comp_mes"]   - m095["comp_mes"]     # compensação evitada
    ben_mes    = delta_perd * CUSTO_PERDAS + delta_comp    # USD/mês

    print(f"\n  Ano {ano} (LoadMult={mult}):")
    print(f"  {'':>4} {'Perdas (MWh/mês)':<28} "
          f"{m092['perdas_mes']:>12.3f} {m095['perdas_mes']:>12.3f} "
          f"{-delta_perd*1000:>+9.1f} kWh")
    print(f"  {'':>4} {'Economia perdas (USD/mês)':<28} "
          f"{'---':>12} {'---':>12} {delta_perd*CUSTO_PERDAS:>+10.2f}")
    print(f"  {'':>4} {'Comp. PRODIST (USD/mês)':<28} "
          f"{m092['comp_mes']:>12.2f} {m095['comp_mes']:>12.2f} "
          f"{delta_comp:>+10.2f}")
    print(f"  {'':>4} {'Benefício líquido (USD/mês)':<28} "
          f"{'---':>12} {'---':>12} {ben_mes:>+10.2f}")

    beneficios_anuais[ano] = ben_mes * 12  # anual

# ---------------------------------------------------------------------------
# VPL com CAPEX = 0
# ---------------------------------------------------------------------------
print(f"\n{'─'*70}")
print(f"  VPL — HORIZONTE 3 ANOS (CAPEX = 0)")
print(f"{'─'*70}")

print(f"\n  Benefícios anuais:")
for ano, ben in beneficios_anuais.items():
    print(f"    Ano {ano}: USD {ben:,.2f}/ano")

# Fluxos com CAPEX zero
residual = 0.0  # sem investimento, sem valor residual
fluxos = [0.0]  # CAPEX zero
for ano in [1, 2, 3]:
    ben = beneficios_anuais[ano]
    fluxos.append(ben)

vpl = sum(f / (1 + TAXA_DESCONTO)**t for t, f in enumerate(fluxos))

print(f"\n  VPL (3 anos, 14% a.a., CAPEX=0) : USD {vpl:,.2f}")
print(f"  Payback                          : imediato (sem investimento)")
print(f"  TIR                              : indefinida (CAPEX=0, sempre positivo)")

# VPL em horizonte de 15 anos (vida útil dos inversores)
# Assume benefício do Ano 3 se repete nos anos 4–15
ben_residual = beneficios_anuais[3]
fluxos_15 = [0.0] + [beneficios_anuais.get(ano, ben_residual) for ano in range(1, 16)]
vpl_15 = sum(f / (1 + TAXA_DESCONTO)**t for t, f in enumerate(fluxos_15))
print(f"  VPL (15 anos, 14% a.a., CAPEX=0): USD {vpl_15:,.2f}")

# ---------------------------------------------------------------------------
# Tabela final consolidada
# ---------------------------------------------------------------------------
print(f"\n{'='*70}")
print("TABELA FINAL — TODAS AS ALTERNATIVAS AVALIADAS")
print(f"{'='*70}")
print(f"  {'Alternativa':<42} {'CAPEX':>8} {'VPL 3a':>10} {'Atrativo':>9}")
print(f"  {'-'*72}")

alternativas = [
    ("Tap trf_6_4910a + trf_11_305a",            1500,    1283, True),
    ("Ajuste FP inversores 0,92→0,95",               0,
     int(vpl), vpl > 0),
    ("Recondutoramento smt_29422",                2207,    -914, False),
    ("Novo trafo 30 kVA paralelo",                6000,   -2674, False),
    ("Novo trafo 45 kVA paralelo",                7500,   -3359, False),
    ("Regulador de tensão",                      12000,   -6207, False),
    ("Capacitor automático 1200 kvar",           12246,   -8008, False),
    ("Capacitor fixo 600 kvar",                   7031,  -27727, False),
]

for nome, capex, vpl_alt, atr in alternativas:
    capex_str = f"{capex:>8,}" if capex > 0 else f"{'0':>8}"
    print(f"  {nome:<42} {capex_str} {vpl_alt:>10,} {'SIM' if atr else 'NÃO':>9}")

print(f"\n  Nota: ajuste de FP é medida operacional sem investimento.")
print(f"  Recomendação: implementar junto com o tap — custo zero,")
print(f"  benefício imediato de USD {beneficios_anuais[1]:,.2f}/ano no Ano 1.")
print("="*70)
