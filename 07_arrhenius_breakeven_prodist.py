# 07_arrhenius_breakeven_prodist.py
# 1. Custo esperado de falha por Arrhenius (trf_6_4910a)
# 2. Break-even do remanejamento por interpolação
# 3. Custo do atraso na decisão do tap
# 4. CSV consolidado de todos os resultados
# 5. Tabela PRODIST DRP/DRC por barramento

import sys
import csv
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent

from dss import dss

import json
with open(HERE / "parametros.json", "r") as f:
    config = json.load(f)

MASTER        = str(HERE / config["caminhos"]["dss_file"])
TRAFO_ALVO    = config.get("graficos", {}).get("trafo_critico", "trf_6_4910a")
TAXA_DESCONTO = config["economico"]["taxa_desconto"]
CUSTO_PERDAS  = config["economico"]["preco_compra_usd_mwh"]
TARIFA_VENDA  = config["economico"]["tarifa_venda_usd_mwh"]
TUSD          = config["economico"]["tusd_usd_mwh"]
VIDA_UTIL_TRAFO = config["simulacao"]["vida_util_projeto"]
CUSTO_EMERG     = config["financeiro_extra"]["custo_emergencia_usd"]

# ===========================================================================
# 1. CUSTO ESPERADO DE FALHA — ARRHENIUS
# ===========================================================================
print("\n" + "="*70)
print("[07.02] CUSTO ESPERADO DE FALHA — MODELO DE ARRHENIUS")
print("="*70)

# Modelo de Arrhenius para transformadores (IEEE C57.91):
# A vida útil do isolamento cai exponencialmente com a temperatura
# Para carregamento > 100%: a cada 6°C acima de 98°C, a vida reduz à metade
# Carregamento 105,7% → elevação de temperatura adicional ≈ +15°C
# Fator de aceleração de envelhecimento: FAA = exp((θH - 98) / 6 * ln2)

import math

def faa(carregamento_pct):
    """Fator de aceleração de envelhecimento (IEEE C57.91).
    Baseado na temperatura de ponto quente estimada.
    Trafo ONAN: θH = θA + Δθ_topo + Δθ_PQ
    Simplificação: θH ≈ 40 + (carregamento/100)^1.6 × 65
    """
    theta_a = 30  # temperatura ambiente média RS (°C)
    delta_topo = (carregamento_pct / 100) ** 1.6 * 55  # elevação no topo
    delta_pq   = (carregamento_pct / 100) ** 1.6 * 23  # ponto quente
    theta_h = theta_a + delta_topo + delta_pq
    return math.exp((theta_h - 98) / 6 * math.log(2)), theta_h

print(f"\n  Modelo IEEE C57.91 — temperatura ambiente: 30°C")
print(f"  {'Carregamento':>14} {'θH (°C)':>9} {'FAA':>8} {'Vida equiv.':>12}")
print(f"  {'-'*48}")

for pct in [80, 88.5, 97.1, 100, 105.7, 110, 120]:
    f, theta_h = faa(pct)
    vida_eq = VIDA_UTIL_TRAFO / f if f > 0 else 999
    print(f"  {pct:>13.1f}% {theta_h:>9.1f} {f:>8.3f} {vida_eq:>11.1f} anos")

# Custo esperado de falha por ano
# Horas em sobrecarga: Ano1=0, Ano2=0, Ano3=730h
horas_sob = {1: 0, 2: 0, 3: 730}
pct_sob   = {1: 88.5, 2: 97.1, 3: 105.7}

print(f"\n  Consumo de vida útil e risco financeiro por ano:")
print(f"  {'Ano':>4} {'Carg%':>7} {'FAA':>7} {'h/ano':>7} {'Δvida (h)':>10} {'P(falha)/ano':>14} {'Risco (USD)':>12}")
print(f"  {'-'*66}")

vida_total_h = VIDA_UTIL_TRAFO * 8760  # horas totais de vida nominal
risco_total  = 0.0

for ano in [1, 2, 3]:
    pct   = pct_sob[ano]
    f, _  = faa(pct)
    h_sob = horas_sob[ano]
    h_nom = 8760 - h_sob  # horas em carregamento normal

    # Consumo de vida útil
    delta_vida_h = h_sob * (f - 1)  # horas "extras" consumidas
    consumo_pct  = (8760 + delta_vida_h) / vida_total_h * 100

    # Probabilidade de falha simplificada (taxa de falha de Weibull)
    # P(falha/ano) ≈ horas_em_sobrecarga / vida_restante_estimada
    vida_restante_h = vida_total_h - (ano - 1) * 8760 * 1.0
    if vida_restante_h > 0 and h_sob > 0:
        p_falha = min(0.99, h_sob * f / vida_restante_h)
    else:
        p_falha = 0.001  # taxa base de falha

    risco_anual = p_falha * CUSTO_EMERG
    risco_total += risco_anual / (1 + TAXA_DESCONTO)**ano

    print(f"  {ano:>4} {pct:>7.1f} {f:>7.3f} {h_sob:>7} {h_sob*(f-1):>10.0f} "
          f"{p_falha*100:>13.2f}% {risco_anual:>12.2f}")

print(f"\n  Valor presente do risco total (3 anos): USD {risco_total:,.2f}")
print(f"  Custo do tap (elimina o risco)        : USD 1.500,00")
print(f"  VPL do tap incluindo risco            : USD {1283 + risco_total:,.2f}")

# ===========================================================================
# 2. BREAK-EVEN DO REMANEJAMENTO
# ===========================================================================
print(f"\n{'='*70}")
print("[07.03] BREAK-EVEN DO REMANEJAMENTO — INTERPOLAÇÃO")
print("="*70)

# Dados já calculados: VPL s/risco e c/risco por horizonte
# s/risco: 3a=-1705, 5a=-2258, 10a=-2926, 15a=-3101
# c/risco: 3a=-693,  5a=+422,  10a=+2428, 15a=+3642
CAPEX_REMANE = config["financeiro_extra"]["custo_remane_usd"]
BEN_BASE     = 200.0   # USD/ano redução de perdas
BEN_RISCO    = BEN_BASE + config["financeiro_extra"]["custo_emergencia_usd"] * 0.15

print(f"\n  CAPEX remanejamento: USD {CAPEX_REMANE:,.0f}")
print(f"  Benefício s/risco  : USD {BEN_BASE:,.0f}/ano")
print(f"  Benefício c/risco  : USD {BEN_RISCO:,.0f}/ano")

# Calcula VPL ano a ano até encontrar break-even
print(f"\n  VPL acumulado por ano (c/risco):")
print(f"  {'Ano':>4} {'Fluxo':>10} {'VPL acum':>12} {'Status':>10}")
print(f"  {'-'*42}")

vpl_acum = -CAPEX_REMANE
print(f"  {'0':>4} {-CAPEX_REMANE:>10,.0f} {vpl_acum:>12,.0f} {'investimento':>10}")

breakeven_ano = None
for ano in range(1, 21):
    # Benefício só começa no Ano 3 (quando sobrecarga inicia)
    if ano < 3:
        ben = BEN_BASE / (1 + TAXA_DESCONTO)**ano
    else:
        residual = CAPEX_REMANE * (VIDA_UTIL_TRAFO - ano) / VIDA_UTIL_TRAFO if ano == 20 else 0
        ben = (BEN_RISCO + residual) / (1 + TAXA_DESCONTO)**ano

    vpl_acum += ben
    status = "✓ break-even" if vpl_acum >= 0 and breakeven_ano is None else ""
    if vpl_acum >= 0 and breakeven_ano is None:
        breakeven_ano = ano
    if ano <= 6 or ano % 5 == 0 or status:
        print(f"  {ano:>4} {ben:>10,.0f} {vpl_acum:>12,.0f} {status:>10}")

print(f"\n  Break-even do remanejamento: Ano {breakeven_ano}")
print(f"  Recomendação: planejar o remanejamento agora para execução")
print(f"  antes do Ano {breakeven_ano - 1}, maximizando o VPL acumulado.")

# ===========================================================================
# 3. CUSTO DO ATRASO NA DECISÃO DO TAP
# ===========================================================================
print(f"\n{'='*70}")
print("[07.04] CUSTO DO ATRASO NA DECISÃO DO TAP")
print("="*70)

# Benefícios do tap por ano (atualizados com as reduções de penalização PRODIST)
BEN_TAP = {1: 4350.0, 2: 4400.0, 3: 4450.0}
CAPEX_TAP = config["alternativas"][1]["custo_inicial_usd"]

print(f"\n  Cenários de timing de implementação:")
print(f"  {'Cenário':<30} {'CAPEX':>8} {'VPL':>10} {'Custo atraso':>13}")
print(f"  {'-'*65}")

# Implementação imediata (Ano 0)
fluxos_imediato = [-CAPEX_TAP,
                   BEN_TAP[1],
                   BEN_TAP[2],
                   BEN_TAP[3] + CAPEX_TAP*(VIDA_UTIL_TRAFO-3)/VIDA_UTIL_TRAFO]
vpl_imediato = sum(f/(1+TAXA_DESCONTO)**t for t,f in enumerate(fluxos_imediato))

print(f"  {'Implementação imediata (Ano 0)':<30} {CAPEX_TAP:>8,.0f} {vpl_imediato:>10,.0f} {'—':>13}")

# Atraso de 1 ano (implementa no início do Ano 1, perde benefício do Ano 1)
fluxos_atraso1 = [0,
                  -CAPEX_TAP,
                  BEN_TAP[2],
                  BEN_TAP[3] + CAPEX_TAP*(VIDA_UTIL_TRAFO-3)/VIDA_UTIL_TRAFO]
vpl_atraso1 = sum(f/(1+TAXA_DESCONTO)**t for t,f in enumerate(fluxos_atraso1))
custo_atraso1 = vpl_imediato - vpl_atraso1

print(f"  {'Atraso 1 ano (impl. Ano 1)':<30} {CAPEX_TAP:>8,.0f} {vpl_atraso1:>10,.0f} {custo_atraso1:>13,.0f}")

# Atraso de 2 anos (implementa no Ano 2, perde Ano 1 e 2, trafo sobrecarrega Ano 3)
# Adiciona risco de falha no Ano 3 (sem proteção do tap)
risco_ano3 = 0.05 * CUSTO_EMERG  # 5% de probabilidade com sobrecarga de 105,7%
fluxos_atraso2 = [0,
                  0,
                  -CAPEX_TAP,
                  BEN_TAP[3] - risco_ano3 + CAPEX_TAP*(VIDA_UTIL_TRAFO-3)/VIDA_UTIL_TRAFO]
vpl_atraso2 = sum(f/(1+TAXA_DESCONTO)**t for t,f in enumerate(fluxos_atraso2))
custo_atraso2 = vpl_imediato - vpl_atraso2

print(f"  {'Atraso 2 anos (impl. Ano 2)':<30} {CAPEX_TAP:>8,.0f} {vpl_atraso2:>10,.0f} {custo_atraso2:>13,.0f}")

# Sem implementação (nenhuma ação)
risco_3anos = sum(0.05*CUSTO_EMERG/(1+TAXA_DESCONTO)**t for t in [3])
vpl_nenhum = -risco_3anos
custo_nenhum = vpl_imediato - vpl_nenhum

print(f"  {'Sem ação (risco de falha)':<30} {'0':>8} {vpl_nenhum:>10,.0f} {custo_nenhum:>13,.0f}")

print(f"\n  Custo de adiar 1 ano: USD {custo_atraso1:,.0f}")
print(f"  Custo de adiar 2 anos: USD {custo_atraso2:,.0f}")
print(f"  Cada mês de atraso custa aproximadamente: USD {custo_atraso1/12:,.0f}")

# ===========================================================================
# 4. CSV CONSOLIDADO
# ===========================================================================
print(f"\n{'='*70}")
print("[07.05] EXPORTANDO CSV CONSOLIDADO")
print("="*70)

csv_path = HERE / "resultados_consolidados.csv"

linhas = [
    # Cabeçalho
    ["Categoria", "Métrica", "Ano1", "Ano2", "Ano3", "Unidade"],

    # Caso base
    ["Caso Base", "Energia fornecida/dia", 13117.3, 14756.6, 16394.7, "kWh/dia"],
    ["Caso Base", "Perdas totais/dia", 609.1, 637.0, 668.7, "kWh/dia"],
    ["Caso Base", "Perdas (%)", 4.64, 4.32, 4.08, "%"],
    ["Caso Base", "Faturamento/mês", 59028, 66000, 73200, "USD"],
    ["Caso Base", "Compensação PRODIST/mês", 944, 1050, 1100, "USD"],
    ["Caso Base", "trf_6_4910a carregamento máx", 88.5, 97.1, 105.7, "%"],
    ["Caso Base", "trf_11_305a carregamento máx", 80.7, 80.6, 80.5, "%"],
    ["Caso Base", "Linhas sobrecarregadas", 0, 0, 0, "qtd"],
    ["Caso Base", "Trafos sobrecarregados", 0, 0, 1, "qtd"],
    ["Caso Base", "Violações tensão MT", 0, 0, 0, "%"],
    ["Caso Base", "Violações tensão BT (faixa precária)", 0, 0, 0, "qtd"],
    ["Caso Base", "Tensão mínima MT", 0.9810, 0.9780, 0.9750, "pu"],
    ["Caso Base", "Tensão mínima BT", 0.9406, 0.9340, 0.9274, "pu"],
    ["Caso Base", "FP global", 0.982, 0.981, 0.980, "adim"],
    ["Caso Base", "GD geração/dia", 3264.5, 3241.6, 3218.7, "kWh/dia"],
    ["Caso Base", "Participação GD no consumo", 22.2, 21.8, 21.4, "%"],

    # Alternativas — VPL
    ["Alternativas VPL", config["alternativas"][1]["descricao"], 1283, "", "", "USD"],
    ["Alternativas VPL", "Ajuste FP 0,92→0,95", 20, "", "", "USD"],
    ["Alternativas VPL", config["alternativas"][4]["descricao"], -914, "", "", "USD"],
    ["Alternativas VPL", "Novo trafo 30 kVA paralelo", -2674, "", "", "USD"],
    ["Alternativas VPL", "Novo trafo 45 kVA paralelo", -3359, "", "", "USD"],
    ["Alternativas VPL", "Regulador de tensão", -6207, "", "", "USD"],
    ["Alternativas VPL", config["alternativas"][3]["descricao"], -8008, "", "", "USD"],
    ["Alternativas VPL", config["alternativas"][2]["descricao"], -27727, "", "", "USD"],

    # Tap — resultados
    ["Alternativa Tap", "trf_6_4910a carregamento c/tap", 85.5, 93.8, 102.1, "%"],
    ["Alternativa Tap", "trf_11_305a carregamento c/tap", 80.7, 80.6, 80.5, "%"],
    ["Alternativa Tap", "Benefício mensal", 970, 760, 796, "USD/mês"],
    ["Alternativa Tap", "CAPEX", 1500, "", "", "USD"],
    ["Alternativa Tap", "TIR", 54, "", "", "%"],
    ["Alternativa Tap", "Payback", 2, "", "", "anos"],

    # GD
    ["GD Fotovoltaica", "Unidades instaladas", 23, 23, 23, "qtd"],
    ["GD Fotovoltaica", "Capacidade instalada", 521, 521, 521, "kW"],
    ["GD Fotovoltaica", "Redução de perdas vs sem GD", 42.16, 41.8, 41.4, "kWh/dia"],
    ["GD Fotovoltaica", "Valor para a rede", 538, 534, 530, "USD/ano"],
    ["GD Fotovoltaica", "Horas fluxo reverso", 0, 0, 0, "h/dia"],

    # Monte Carlo
    ["Monte Carlo", "P10 ano de sobrecarga", 2, "", "", "ano"],
    ["Monte Carlo", "P50 ano de sobrecarga (mediana)", 3, "", "", "ano"],
    ["Monte Carlo", "P90 ano de sobrecarga", 4, "", "", "ano"],
    ["Monte Carlo", "Probabilidade sobrecarga até Ano 15", 100, "", "", "%"],

    # Longo prazo
    ["Longo Prazo", "Trafos com alerta em 15 anos", 5, "", "", "qtd"],
    ["Longo Prazo", "trf_6_3509a entra em sobrecarga", 10, "", "", "ano"],
    ["Longo Prazo", "Break-even remanejamento (c/risco)", breakeven_ano, "", "", "ano"],
    ["Longo Prazo", "N-1 smt_31408 barramentos afetados", 83, "", "", "qtd"],
    ["Longo Prazo", "N-1 smt_31408 trafos afetados", 6, "", "", "qtd"],
]

with open(csv_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f, delimiter=';')
    writer.writerows(linhas)

print(f"\n  Arquivo gerado: {csv_path.name}")
print(f"  Linhas: {len(linhas)} (incluindo cabeçalho)")
print(f"  Colunas: Categoria, Métrica, Ano1, Ano2, Ano3, Unidade")

# ===========================================================================
# 5. TABELA PRODIST DRP/DRC
# ===========================================================================
print(f"\n{'='*70}")
print("[07.06] TABELA PRODIST — DRP/DRC POR BARRAMENTO (CASO BASE, ANO 1)")
print("="*70)

# Carrega o caso base e coleta tensões horárias por barramento BT
print("\n  Coletando leituras de tensão (24 leituras × fator = 144 leituras equiv.)...")

dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"
dss.Text.Command = "Set LoadMult=1.0"
circuit = dss.ActiveCircuit
all_bus = list(circuit.AllBusNames)

# Coleta tensão por hora por barramento BT
leituras = defaultdict(list)  # {nome_bus: [vpu_h1, vpu_h2, ...]}

circuit.Solution.dblHour = 0.0
for h in range(24):
    circuit.Solution.Solve()
    for nome in all_bus:
        circuit.SetActiveBus(nome)
        kv = circuit.ActiveBus.kVBase
        if 0.05 < kv <= 1.0:
            vmag = circuit.ActiveBus.VMagAngle
            if len(vmag) >= 1:
                vpu = vmag[0] / (kv * 1000)
                if vpu > 0.01:
                    leituras[nome].append(vpu)

# Faixas PRODIST Tabela 5 (BT 220/127V)
# Adequada: 0,921–1,050
# Precária:  0,871–0,921 ou 1,050–1,061
# Crítica:   < 0,871 ou > 1,061

def faixas_prodist(vpus):
    """Retorna DRP e DRC em % (relativo a 1008 leituras mensais).
    Fator correto: 1h de violação = 6 leituras × 7 dias = 42 leituras mensais.
    """
    n_total = 1008  # leituras mensais padrão PRODIST (7 dias × 24h × 6)
    fator   = 42    # 6 leituras/h × 7 dias

    n_prec = sum(1 for v in vpus if 0.871 <= v < 0.921 or 1.050 < v <= 1.061) * fator
    n_crit = sum(1 for v in vpus if v < 0.871 or v > 1.061) * fator

    drp = 100 * n_prec / n_total
    drc = 100 * n_crit / n_total
    return drp, drc

# Filtra só barramentos com alguma violação
print(f"\n  Barramentos BT com DRP > 0% ou DRC > 0% (violações PRODIST):")
print(f"  {'Barramento':<25} {'Vmin (pu)':>10} {'Vmax (pu)':>10} {'DRP (%)':>9} {'DRC (%)':>9} {'Status':>10}")
print(f"  {'-'*76}")

violacoes = []
for nome, vpus in leituras.items():
    if not vpus: continue
    vmin = min(vpus)
    vmax = max(vpus)
    drp, drc = faixas_prodist(vpus)
    if drp > 0 or drc > 0:
        violacoes.append((nome, vmin, vmax, drp, drc))

violacoes.sort(key=lambda x: x[3] + x[4], reverse=True)

if violacoes:
    for nome, vmin, vmax, drp, drc in violacoes[:20]:
        status = "crítica" if drc > 0 else "precária"
        print(f"  {nome:<25} {vmin:>10.4f} {vmax:>10.4f} {drp:>9.2f} {drc:>9.2f} {status:>10}")
    print(f"\n  Total de barramentos com violação: {len(violacoes)}")
else:
    print(f"  Nenhum barramento BT com violação PRODIST no caso base.")
    print(f"  Rede dentro dos limites regulatórios em todas as barras.")

# Exporta CSV PRODIST
prodist_path = HERE / "prodist_drp_drc.csv"
with open(prodist_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f, delimiter=';')
    writer.writerow(["Barramento", "Vmin_pu", "Vmax_pu", "Vmed_pu",
                     "DRP_%", "DRC_%", "Status"])
    for nome, vpus in leituras.items():
        if not vpus: continue
        vmin = min(vpus)
        vmax = max(vpus)
        vmed = sum(vpus)/len(vpus)
        drp, drc = faixas_prodist(vpus)
        if vmin < 0.921 or vmax > 1.050:
            status = "crítica" if drc > 0 else ("precária" if drp > 0 else "adequada")
        else:
            status = "adequada"
        writer.writerow([nome, f"{vmin:.4f}", f"{vmax:.4f}", f"{vmed:.4f}",
                        f"{drp:.2f}", f"{drc:.2f}", status])

print(f"\n  CSV PRODIST exportado: {prodist_path.name}")
print(f"  Barramentos BT avaliados: {len(leituras)}")
print("="*70)
