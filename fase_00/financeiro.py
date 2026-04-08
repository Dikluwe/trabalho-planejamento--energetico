# Crystalline Lineage
# @prompt 00_nucleo/prompts/financeiro.md
# @layer L1
# @updated 2026-04-04

"""
Funções financeiras puras para o Trabalho 1a — Planejamento Energético.
Todas as funções recebem dados primitivos ou DataFrames e devolvem floats.
Nenhuma função acessa disco, OpenDSS ou imprime na tela.

Parâmetros fixos do enunciado (podem ser sobrescritos via argumento):
  - Tarifa venda:    150 USD/MWh
  - Custo compra:     35 USD/MWh
  - TUSD:             90 USD/MWh
  - Taxa de desconto: 14% ao ano
  - Vida útil:        15 anos (condutores e capacitores)
  - Horizonte:         3 anos
  - Crescimento carga: 10% ao ano
"""

from __future__ import annotations
import math
import pandas as pd


# ---------------------------------------------------------------------------
# Caso base — energia e faturamento
# ---------------------------------------------------------------------------


def faturamento_mensal(
    energia_dia_kwh: float,
    tarifa_usd_mwh: float = 150.0,
    dias_mes: float = 30.0,
) -> float:
    """
    Receita bruta mensal com a venda de energia.

    energia_dia_kwh : totalEnergyKWh do EnergySummary do professor (1 dia)
    Retorna USD.
    """
    energia_mes_mwh = energia_dia_kwh * dias_mes / 1000.0
    return energia_mes_mwh * tarifa_usd_mwh


def custo_perdas_mensal(
    perdas_dia_kwh: float,
    preco_compra_usd_mwh: float = 35.0,
    dias_mes: float = 30.0,
) -> float:
    """
    Custo operacional mensal pago pela distribuidora pelas perdas técnicas.

    perdas_dia_kwh : totalLossesKWh do EnergySummary do professor (1 dia)
    Retorna USD.
    """
    perdas_mes_mwh = perdas_dia_kwh * dias_mes / 1000.0
    return perdas_mes_mwh * preco_compra_usd_mwh


# ---------------------------------------------------------------------------
# Compensação PRODIST Módulo 8 — itens 26 a 29
# ---------------------------------------------------------------------------


def _classificar_violacao_prodist(
    tensao_pu: float,
    nivel: str,
    limite_min_pu: float = 0.92,
    limite_max_pu: float = 1.05,
) -> tuple[bool, bool]:
    """
    Classifica uma leitura de tensão como precária ou crítica conforme
    PRODIST Módulo 8, Anexo 8.A — tabelas reais por nível de tensão.

    MT (> 2,3 kV e < 69 kV) — Tabela 3:
      Adequada : 0,93 ≤ TL ≤ 1,05
      Precária : 0,90 ≤ TL < 0,93
      Crítica  : TL < 0,90 ou TL > 1,05

    BT 380/220V — Tabela 5 (rede CRELUZ secundário trifásico):
      Adequada : 350–399V → 0,921 – 1,050 pu
      Precária : 331–350V → 0,871 – 0,921 pu
      Crítica  : < 331V   → < 0,871 pu
      Crítica  : > 403V   → > 1,061 pu

    BT 220/127V — Tabela 4 (monofásicos):
      Adequada : 202–231V → 0,918 – 1,050 pu
      Precária : 191–202V → 0,868 – 0,918 pu
      Crítica  : < 191V   → < 0,868 pu

    Usamos BT 380V como padrão para LV (maioria dos secundários CRELUZ).

    Retorna (is_precaria, is_critica).
    """
    if nivel == "LV":
        # BT 380/220V — Tabela 5
        ad_inf = limite_min_pu
        ad_sup = limite_max_pu

        # Diferença PRODIST: Crítica inf é ~0.05 abaixo da adequada inf (0.921 - 0.871)
        cr_inf = ad_inf - 0.05
        # Crítica sup é ~0.011 acima da adequada sup (1.061 - 1.050)
        cr_sup = ad_sup + 0.011

        is_critica = tensao_pu < cr_inf or tensao_pu > cr_sup
        is_precaria = (not is_critica) and (tensao_pu < ad_inf or tensao_pu > ad_sup)
    else:
        # MT > 2,3 kV e < 69 kV — Tabela 3
        ad_inf = limite_min_pu
        ad_sup = limite_max_pu

        # Diferença PRODIST: Crítica inf é ~0.03 abaixo da adequada inf (0.93 - 0.90)
        cr_inf = ad_inf - 0.03
        cr_sup = ad_sup

        is_critica = tensao_pu < cr_inf or tensao_pu > cr_sup
        is_precaria = (not is_critica) and tensao_pu < ad_inf

    return is_precaria, is_critica


def compensacao_prodist_mensal(
    df_voltages: pd.DataFrame,
    df_meter_by_hour: pd.DataFrame,
    limite_min_pu: float = 0.92,
    limite_max_pu: float = 1.05,
    tusd_usd_mwh: float = 90.0,
    leituras_por_hora: int = 6,
    leituras_mes_prodist: int = 1008,
) -> float:
    """
    Compensação financeira mensal por violação de tensão — PRODIST Módulo 8, item 29.

    Fórmula (item 29):
      Comp = [(DRP - DRPlim)/100 × k1 + (DRC - DRClim)/100 × k2] × EUSD

    Limites (item 28):
      DRPlimite = 3%
      DRClimite = 0,5%

    Fatores k (item 29):
      k1 = 3 se DRP > DRPlimite, senão 0
      k2 = 7 para BT se DRC > DRClimite, senão 0
      k2 = 5 para MT se DRC > DRClimite, senão 0

    Faixas de tensão (Anexo 8.A):
      BT: adequada 0,92–1,05 | precária 0,87–0,92 e 1,05–1,06 | crítica <0,87 e >1,06
      MT: adequada 0,95–1,05 | precária 0,90–0,95 e 1,05–1,06 | crítica <0,90 e >1,06

    Extrapolação dia → mês:
      Simulação em passos de 1h. O PRODIST mede em blocos de 10 min.
      1 hora de violação = 6 leituras × 7 dias = 42 leituras mensais.
      Mês PRODIST = 1008 leituras. Fator correto = 42.

    df_voltages     : CollectVoltageRowsForHour — colunas: hour, bus, phase,
                      voltagePu, violationPu, hasViolation, voltageLevel
    df_meter_by_hour: CollectMeterRowsForHour — colunas: hour,
                      deltaActiveEnergyKWh

    Retorna USD/mês (soma das compensações de todos os consumidores).
    """
    if df_voltages.empty or df_meter_by_hour.empty:
        return 0.0

    # Fator de extrapolação: horas simuladas → leituras mês PRODIST
    # A simulação roda em passos de 1h, mas o PRODIST mede em blocos de 10min.
    # 1 hora de violação = 6 leituras de 10min × 7 dias = 42 leituras mensais
    # (PRODIST Módulo 8: 1008 leituras = 7 dias × 24h × 6 leituras/h)
    fator_mes = leituras_por_hora * 7  # 6 × 7 = 42

    # Limites PRODIST (item 28)
    drp_limite = 3.0  # %
    drc_limite = 0.5  # %

    from fase_00 import configuracao

    medidor = configuracao.MEDIDOR_SUBESTACAO.lower()
    df_medidor = df_meter_by_hour[df_meter_by_hour["meterName"].str.lower() == medidor]

    if not df_medidor.empty:
        energia_total_dia_kwh = df_medidor["deltaActiveEnergyKWh"].sum()
    else:
        # Fallback se não encontrar o medidor pelo nome
        energia_total_dia_kwh = df_meter_by_hour["deltaActiveEnergyKWh"].sum() / (
            1 + df_voltages["bus"].nunique() / 50
        )  # Heurística se falhar

    n_nos = df_voltages["bus"].nunique()
    if n_nos == 0:
        return 0.0

    # TUSD em USD/kWh
    tusd_usd_kwh = tusd_usd_mwh / 1000.0

    # Consumo mensal estimado por nó (proxy para EUSD individual)
    energia_mes_por_no_kwh = (energia_total_dia_kwh * 30.0) / n_nos

    compensacao_total = 0.0

    # Calcula DRP e DRC por nó usando faixas corretas por nível de tensão
    for bus, grupo in df_voltages.groupby("bus"):
        nivel = grupo["voltageLevel"].iloc[0]  # "MV" ou "LV"

        n_precarias = 0
        n_criticas = 0
        for _, row in grupo.iterrows():
            is_prec, is_crit = _classificar_violacao_prodist(
                float(row["voltagePu"]), nivel, limite_min_pu, limite_max_pu
            )
            if is_prec:
                n_precarias += 1
            if is_crit:
                n_criticas += 1

        # Extrapola para o mês (pega a pior fase — aqui já é por nó)
        nlp_mes = int(n_precarias * fator_mes)
        nlc_mes = int(n_criticas * fator_mes)

        drp = (nlp_mes / leituras_mes_prodist) * 100.0
        drc = (nlc_mes / leituras_mes_prodist) * 100.0

        # Fatores k
        k1 = 3.0 if drp > drp_limite else 0.0
        if drc > drc_limite:
            k2 = 7.0 if nivel == "LV" else 5.0
        else:
            k2 = 0.0

        if k1 == 0.0 and k2 == 0.0:
            continue

        # EUSD = consumo mensal do consumidor × TUSD (USD/kWh)
        eusd = energia_mes_por_no_kwh * tusd_usd_kwh

        comp = (
            (drp - drp_limite) / 100.0 * k1 + (drc - drc_limite) / 100.0 * k2
        ) * eusd

        if comp > 0:
            compensacao_total += comp

    return compensacao_total


# ---------------------------------------------------------------------------
# VPL e valor residual
# ---------------------------------------------------------------------------


def vpl(fluxos: list[float], taxa: float = 0.14) -> float:
    """
    Valor Presente Líquido de uma série de fluxos de caixa.

    fluxos[0] = investimento em t=0  (negativo, saída de caixa)
    fluxos[1] = fluxo líquido no ano 1
    fluxos[2] = fluxo líquido no ano 2
    fluxos[3] = fluxo líquido no ano 3 + valor residual

    Retorna USD.
    """
    return sum(f / (1.0 + taxa) ** t for t, f in enumerate(fluxos))


def valor_residual_linear(
    custo_instalado_usd: float,
    vida_util_anos: int = 15,
    anos_decorridos: int = 3,
) -> float:
    """
    Valor de livro do equipamento após anos_decorridos (depreciação linear).
    Valor residual nulo após o fim da vida útil.

    Retorna USD.
    """
    if anos_decorridos >= vida_util_anos:
        return 0.0
    return custo_instalado_usd * (vida_util_anos - anos_decorridos) / vida_util_anos


# ---------------------------------------------------------------------------
# Benefícios anuais de uma intervenção
# ---------------------------------------------------------------------------


def beneficio_anual(
    delta_perdas_dia_kwh: float,
    delta_compensacao_mensal_usd: float,
    preco_compra_usd_mwh: float = 35.0,
    dias_ano: float = 365.0,
) -> float:
    """
    Benefício financeiro anual de uma intervenção em relação ao caso base.

    delta_perdas_dia_kwh        : redução de perdas por dia (base - proposta)
    delta_compensacao_mensal_usd: redução da compensação PRODIST por mês

    Retorna USD/ano.
    """
    economia_perdas_ano = (
        delta_perdas_dia_kwh / 1000.0 * dias_ano * preco_compra_usd_mwh
    )
    economia_compensacao_ano = delta_compensacao_mensal_usd * 12.0

    return economia_perdas_ano + economia_compensacao_ano


# ---------------------------------------------------------------------------
# Montagem dos fluxos de caixa para 3 anos com crescimento de carga
# ---------------------------------------------------------------------------


def montar_fluxos(
    custo_inicial_usd: float,
    custo_manutencao_anual_usd: float,
    beneficio_ano1_usd: float,
    beneficio_ano2_usd: float,
    beneficio_ano3_usd: float,
    residual_usd: float,
) -> list[float]:
    """
    Monta a lista de fluxos de caixa para o VPL de 3 anos.

    t=0: investimento inicial (negativo)
    t=1: benefício ano 1 - manutenção
    t=2: benefício ano 2 - manutenção
    t=3: benefício ano 3 - manutenção + valor residual

    Retorna lista de 4 floats.
    """
    return [
        -custo_inicial_usd,
        beneficio_ano1_usd - custo_manutencao_anual_usd,
        beneficio_ano2_usd - custo_manutencao_anual_usd,
        beneficio_ano3_usd - custo_manutencao_anual_usd + residual_usd,
    ]


# ---------------------------------------------------------------------------
# Resumo financeiro do caso base (impressão pelo main)
# ---------------------------------------------------------------------------


def resumo_financeiro_caso_base(
    energia_dia_kwh: float,
    perdas_dia_kwh: float,
    compensacao_mensal_usd: float,
    tarifa_usd_mwh: float = 150.0,
    preco_compra_usd_mwh: float = 35.0,
) -> dict:
    """
    Consolida os indicadores financeiros mensais do caso base.

    Retorna dicionário com todos os valores em USD/mês,
    mais energia em MWh/mês para o relatório.
    """
    fat = faturamento_mensal(energia_dia_kwh, tarifa_usd_mwh)
    custo = custo_perdas_mensal(perdas_dia_kwh, preco_compra_usd_mwh)

    return {
        "energia_fornecida_mwh_mes": energia_dia_kwh * 30.0 / 1000.0,
        "energia_perdas_mwh_mes": perdas_dia_kwh * 30.0 / 1000.0,
        "percentual_perdas_pct": 100.0 * perdas_dia_kwh / energia_dia_kwh
        if energia_dia_kwh > 0
        else 0.0,
        "faturamento_mensal_usd": fat,
        "custo_perdas_mensal_usd": custo,
        "compensacao_prodist_mensal_usd": compensacao_mensal_usd,
        "resultado_operacional_mensal_usd": fat - custo - compensacao_mensal_usd,
    }
