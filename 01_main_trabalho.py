# Crystalline Lineage
# @prompt 00_nucleo/prompts/expansao.md
# @layer L4
# @updated 2026-04-04

"""
Ponto de entrada do Trabalho 1a — Planejamento Energético.

Coloca este arquivo na mesma pasta que Main.py (do professor) e os
arquivos .dss da CRELUZ. Execute com:

    python main_trabalho.py

O programa:
  1. Roda o caso base para os 3 anos de crescimento de carga
  2. Avalia as alternativas de intervenção definidas abaixo
  3. Imprime a tabela comparativa com VPL de cada alternativa

Para alterar as alternativas avaliadas, edite a lista ALTERNATIVAS abaixo.
"""

import sys
from pathlib import Path

# Garante que Main.py e os módulos novos estão no path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import Main as professor
import financeiro
import expansao
from expansao import Alternativa


# ---------------------------------------------------------------------------
# Configuração do problema
# ---------------------------------------------------------------------------

DSS_FILE = str(HERE / "Master.dss")
OUTPUT_BASE = str(HERE / "Resultados")

# Parâmetros do enunciado — não alterar sem justificativa no relatório
TAXA_DESCONTO = 0.14
TARIFA_VENDA_USD_MWH = 150.0
PRECO_COMPRA_USD_MWH = 35.0
TUSD_USD_MWH = 90.0
LIMITE_MIN_PU = 0.95
LIMITE_MAX_PU = 1.05


# ---------------------------------------------------------------------------
# Alternativas de intervenção
# ---------------------------------------------------------------------------
#
# Cada Alternativa recebe:
#   descricao          : texto curto que vai aparecer no relatório
#   comandos_dss       : lista de comandos DSS a executar antes de simular
#   custo_inicial_usd  : CAPEX total em t=0
#   custo_manutencao_anual_usd: OPEX anual (só capacitores)
#   vida_util_anos     : 15 para condutores e capacitores (enunciado)
#
# Os custos vêm das Tabelas 1 e 2 do enunciado.
#
# IMPORTANTE: os comandos DSS usam os nomes reais dos elementos na rede
# da CRELUZ. Ajuste os nomes após verificar os CSVs de saída do caso base
# (LinesLoadingByHour.csv e TransformersLoadingByHour.csv).
# Os nomes mais carregados aparecem no topo de LineSummary.csv.
#
# Exemplos de comandos DSS:
#   Ajuste de tap (600V por derivação, até 5 derivações):
#     "Transformer.TR_NOME wdg=1 tap=0.9667"   ← tap -1 (abaixa 600V em 23,1kV)
#     "Transformer.TR_NOME wdg=1 tap=1.0333"   ← tap +1
#
#   Recondutoramento (substitui o linecode do trecho):
#     "Line.NOME_TRECHO linecode=2/0CA"
#     "Line.NOME_TRECHO linecode=4/0CA"
#     "Line.NOME_TRECHO linecode=336_4CA"
#
#   Banco de capacitor fixo 600 kvar em barramento MT:
#     "New Capacitor.CAP1 bus1=NOME_BARRAMENTO phases=3 kvar=600 kv=23.1"
#
#   Banco de capacitor automático (CapControl):
#     "New Capacitor.CAP2 bus1=NOME_BARRAMENTO phases=3 kvar=1200 kv=23.1"
#     "New CapControl.CC2 element=Line.TRECHO_PROXIMO terminal=1 capacitor=CAP2 type=current onsetting=80 offsetting=60"
#

ALTERNATIVAS: list[Alternativa] = [

    # ------------------------------------------------------------------
    # Alternativa 1 — Ajuste de tap no trf_6_4910a (mais carregado)
    # Sobe tap do secundário de 1.0 para 1.0333 (+1 derivação de 600V)
    # para reduzir a corrente no primário e aliviar o carregamento.
    # Custo: 750 USD por transformador (enunciado)
    # ------------------------------------------------------------------
    Alternativa(
        descricao="Ajuste de tap — trf_6_4910a (+1 derivacao)",
        comandos_dss=[
            "Edit Transformer.TRF_6_4910A wdg=1 tap=1.0333",
        ],
        custo_inicial_usd=750.0,
        custo_manutencao_anual_usd=0.0,
        vida_util_anos=15,
    ),

    # ------------------------------------------------------------------
    # Alternativa 2 — Ajuste de tap nos 2 trafos mais carregados
    # trf_6_4910a (88,5% → ano 3: 105,7%) e trf_11_305a (80,7%)
    # Custo: 2 × 750 = 1500 USD
    # ------------------------------------------------------------------
    Alternativa(
        descricao="Ajuste de tap — trf_6_4910a + trf_11_305a",
        comandos_dss=[
            "Edit Transformer.TRF_6_4910A wdg=1 tap=1.0333",
            "Edit Transformer.TRF_11_305A wdg=1 tap=1.0333",
        ],
        custo_inicial_usd=2 * 750.0,
        custo_manutencao_anual_usd=0.0,
        vida_util_anos=15,
    ),

    # ------------------------------------------------------------------
    # Alternativa 3 — Banco de capacitor fixo 600 kvar no barramento 9051
    # Barramento MT do trf_6_4910a (23,1 kV, 3 fases)
    # Custo Tabela 2: aquisição 6500 + instalação 531 = 7031 USD
    # Manutenção anual: 341 USD
    # ------------------------------------------------------------------
    Alternativa(
        descricao="Capacitor fixo 600 kvar (barra 9051)",
        comandos_dss=[
            "New Capacitor.CAP1 bus1=9051 phases=3 kvar=600 kv=23.1",
        ],
        custo_inicial_usd=6500.0 + 531.0,
        custo_manutencao_anual_usd=341.0,
        vida_util_anos=15,
    ),

    # ------------------------------------------------------------------
    # Alternativa 4 — Banco de capacitor automático 1200 kvar no barra 9051
    # Custo Tabela 2: aquisição 11450 + instalação 796 = 12246 USD
    # Manutenção anual: 1023 USD
    # ------------------------------------------------------------------
    Alternativa(
        descricao="Capacitor automatico 1200 kvar (barra 9051)",
        comandos_dss=[
            "New Capacitor.CAP2 bus1=9051 phases=3 kvar=1200 kv=23.1",
            "New CapControl.CC2 element=Line.smt_14449 terminal=1 capacitor=CAP2 type=kvar onsetting=200 offsetting=150",
        ],
        custo_inicial_usd=11450.0 + 796.0,
        custo_manutencao_anual_usd=1023.0,
        vida_util_anos=15,
    ),

]


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("TRABALHO 1a — PLANEJAMENTO ENERGÉTICO (CRELUZ)")
    print("=" * 80)

    # 1. Caso base para os 3 anos de crescimento
    print("\n[PASSO 1] Rodando caso base para os 3 anos de crescimento de carga...")
    ind_base_1, ind_base_2, ind_base_3 = expansao.rodar_caso_base_3_anos(
        dss_file_path=DSS_FILE,
        output_folder_base=OUTPUT_BASE,
    )

    # 2. Imprime diagnóstico do caso base (ano 1)
    resumo = financeiro.resumo_financeiro_caso_base(
        energia_dia_kwh=ind_base_1["energia_dia_kwh"],
        perdas_dia_kwh=ind_base_1["perdas_dia_kwh"],
        compensacao_mensal_usd=ind_base_1["compensacao_mensal_usd"],
    )

    print("\n[PASSO 2] Diagnóstico financeiro do caso base (Ano 1 — carga nominal):")
    print(f"  Energia fornecida/mês  : {resumo['energia_fornecida_mwh_mes']:.2f} MWh")
    print(f"  Perdas/mês             : {resumo['energia_perdas_mwh_mes']:.2f} MWh ({resumo['percentual_perdas_pct']:.2f}%)")
    print(f"  Faturamento/mês        : USD {resumo['faturamento_mensal_usd']:,.2f}")
    print(f"  Custo perdas/mês       : USD {resumo['custo_perdas_mensal_usd']:,.2f}")
    print(f"  Compensação PRODIST/mês: USD {resumo['compensacao_prodist_mensal_usd']:,.2f}")
    print(f"  Resultado operacional  : USD {resumo['resultado_operacional_mensal_usd']:,.2f}")

    # 3. Filtra alternativas com comandos DSS definidos
    alternativas_ativas = [a for a in ALTERNATIVAS if a.comandos_dss]

    if not alternativas_ativas:
        print("\n[AVISO] Nenhuma alternativa tem comandos DSS definidos.")
        print("        Rode o caso base primeiro, identifique os elementos críticos")
        print("        nos CSVs de saída e preencha os comandos na lista ALTERNATIVAS.")
        print("\n        Arquivos gerados em:", OUTPUT_BASE + "_ano1")
        print("        Consulte: LineSummary.csv e TransformerSummary.csv")
        return

    # 4. Avalia cada alternativa
    print(f"\n[PASSO 3] Avaliando {len(alternativas_ativas)} alternativa(s) de intervenção...")
    resultados = []
    for alt in alternativas_ativas:
        resultado = expansao.avaliar_alternativa(
            dss_file_path=DSS_FILE,
            alternativa=alt,
            indicadores_base_ano1=ind_base_1,
            indicadores_base_ano2=ind_base_2,
            indicadores_base_ano3=ind_base_3,
            taxa=TAXA_DESCONTO,
            preco_compra_usd_mwh=PRECO_COMPRA_USD_MWH,
        )
        resultados.append(resultado)

    # 5. Tabela comparativa final
    expansao.imprimir_tabela_comparativa(ind_base_1, resultados)


if __name__ == "__main__":
    main()
