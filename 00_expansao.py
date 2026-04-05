# Crystalline Lineage
# @prompt 00_nucleo/prompts/expansao.md
# @layer L1
# @updated 2026-04-04

"""
Funções de avaliação de alternativas de expansão para o Trabalho 1a.

Cada alternativa é definida por:
  - Uma lista de comandos DSS que modificam a rede
  - Um custo inicial (CAPEX em t=0)
  - Um custo de manutenção anual (OPEX — só capacitores têm)
  - Uma descrição legível

O fluxo de uso é:
  1. Rodar o caso base com RunDailyNetworkAnalysis (programa do professor)
  2. Para cada alternativa, chamar rodar_cenario_com_modificacao
  3. Calcular os benefícios anuais para cada ano (carga × 1.0, 1.1, 1.2)
  4. Montar fluxos e calcular VPL

Dependências externas: dss (OpenDSS), pandas, numpy
Não importa nada de L2, L3, L4.
"""

from __future__ import annotations
import sys
from pathlib import Path
from dataclasses import dataclass

import pandas as pd

# Importa o programa do professor como módulo
# O Main.py deve estar na mesma pasta ou no sys.path
import Main as professor

import financeiro


# ---------------------------------------------------------------------------
# Definição de uma alternativa de intervenção
# ---------------------------------------------------------------------------

@dataclass
class Alternativa:
    """
    Descreve uma proposta de modificação na rede.

    comandos_dss: lista de strings de comando DSS a executar após carregar
                  o circuito, antes de simular.
                  Ex: ["Transformer.TR1 wdg=1 tap=0.9667",
                       "Line.SMT_27096 linecode=4/0CA"]

    custo_inicial_usd      : CAPEX pago em t=0
    custo_manutencao_anual : OPEX anual (0 para condutores e taps)
    vida_util_anos         : para calcular o valor residual (15 padrão)
    descricao              : texto curto para o relatório
    """
    descricao: str
    comandos_dss: list[str]
    custo_inicial_usd: float
    custo_manutencao_anual_usd: float = 0.0
    vida_util_anos: int = 15


# ---------------------------------------------------------------------------
# Execução de um cenário com modificações
# ---------------------------------------------------------------------------

def rodar_cenario(
    dss_file_path: str,
    comandos_modificacao: list[str],
    fator_carga: float = 1.0,
    considerar_pv: bool = True,
    total_horas: int = 24,
    limite_bt_kv: float = 1.0,
    limite_min_pu: float = 0.95,
    limite_max_pu: float = 1.05,
    output_folder: str | None = None,
) -> dict:
    """
    Carrega a rede, aplica modificações, ajusta fator de carga e roda 24h.

    Retorna o dicionário de DataFrames produzido por RunDailyNetworkAnalysis.
    Se output_folder for None, usa uma pasta temporária que não polui os
    resultados do caso base.

    fator_carga: 1.0 = ano 1 (nominal), 1.1 = ano 2, 1.2 = ano 3
    """
    from dss import dss

    # Pasta de saída separada por fator de carga para não sobrescrever
    if output_folder is None:
        base = Path(dss_file_path).parent
        fator_str = f"{fator_carga:.2f}".replace(".", "p")
        output_folder = str(base / f"_temp_cenario_{fator_str}")

    # Inicializa o circuito (Clear + Redirect) e obtém o objeto solution
    solution = professor.InitializeCircuit(dss_file_path, considerar_pv)

    # Aplica o fator de carga APÓS o Redirect e ANTES de qualquer Solve
    if fator_carga != 1.0:
        dss.Text.Command = f"Set LoadMult={fator_carga}"

    # Aplica as modificações da alternativa
    for cmd in comandos_modificacao:
        dss.Text.Command = cmd

    # Roda sem chamar InitializeCircuit de novo (preserva LoadMult)
    (
        df_voltages,
        df_lines,
        df_transformers,
        df_meter_by_hour,
    ) = professor.RunDailySimulationAndCollect(
        solution=solution,
        totalHours=total_horas,
        lowVoltageLimitKv=limite_bt_kv,
        lowerVoltageLimitPu=limite_min_pu,
        upperVoltageLimitPu=limite_max_pu,
    )

    df_phase_a, df_phase_b, df_phase_c = professor.SplitVoltagesByPhase(df_voltages)
    df_voltage_summary  = professor.BuildVoltageSummary(df_voltages)
    df_line_summary     = professor.BuildLineSummary(df_lines)
    df_trafo_summary    = professor.BuildTransformerSummary(df_transformers)
    df_meter_hr_summary = professor.BuildMeterHourSummary(df_meter_by_hour)
    df_energy_summary   = professor.CollectEnergySummary(df_meter_by_hour)
    df_network_summary  = professor.BuildDailyNetworkSummary(
        dfVoltageSummary=df_voltage_summary,
        dfLineSummary=df_line_summary,
        dfTransformerSummary=df_trafo_summary,
        dfEnergySummary=df_energy_summary,
    )

    professor.ExportResults(
        outputFolderPath=output_folder,
        dfVoltages=df_voltages,
        dfLines=df_lines,
        dfTransformers=df_transformers,
        dfMeterByHour=df_meter_by_hour,
        dfVoltageSummary=df_voltage_summary,
        dfLineSummary=df_line_summary,
        dfTransformerSummary=df_trafo_summary,
        dfMeterHourSummary=df_meter_hr_summary,
        dfEnergySummary=df_energy_summary,
        dfNetworkSummary=df_network_summary,
    )

    print(f"\nResumo (LoadMult={fator_carga}):\n")
    print(df_network_summary.to_string(index=False))

    return {
        "dfVoltages": df_voltages,
        "dfPhaseA": df_phase_a,
        "dfPhaseB": df_phase_b,
        "dfPhaseC": df_phase_c,
        "dfLines": df_lines,
        "dfTransformers": df_transformers,
        "dfMeterByHour": df_meter_by_hour,
        "dfVoltageSummary": df_voltage_summary,
        "dfLineSummary": df_line_summary,
        "dfTransformerSummary": df_trafo_summary,
        "dfMeterHourSummary": df_meter_hr_summary,
        "dfEnergySummary": df_energy_summary,
        "dfNetworkSummary": df_network_summary,
    }


# ---------------------------------------------------------------------------
# Extração dos indicadores financeiros de um resultado
# ---------------------------------------------------------------------------

def extrair_indicadores(resultado: dict) -> dict:
    """
    Extrai energia, perdas e compensação de um resultado do professor.

    Retorna dicionário com:
      energia_dia_kwh, perdas_dia_kwh, compensacao_mensal_usd
    """
    df_energy = resultado["dfEnergySummary"]
    df_voltages = resultado["dfVoltages"]
    df_meter_hour = resultado["dfMeterByHour"]

    energia_dia_kwh = 0.0
    perdas_dia_kwh = 0.0

    if not df_energy.empty:
        energia_dia_kwh = df_energy["totalEnergyKWh"].sum()
        perdas_dia_kwh = df_energy["totalLossesKWh"].sum()

    compensacao = financeiro.compensacao_prodist_mensal(
        df_voltages=df_voltages,
        df_meter_by_hour=df_meter_hour,
    )

    return {
        "energia_dia_kwh": energia_dia_kwh,
        "perdas_dia_kwh": perdas_dia_kwh,
        "compensacao_mensal_usd": compensacao,
    }


# ---------------------------------------------------------------------------
# Cálculo do VPL de uma alternativa
# ---------------------------------------------------------------------------

def avaliar_alternativa(
    dss_file_path: str,
    alternativa: Alternativa,
    indicadores_base_ano1: dict,
    indicadores_base_ano2: dict,
    indicadores_base_ano3: dict,
    taxa: float = 0.14,
    preco_compra_usd_mwh: float = 35.0,
) -> dict:
    """
    Roda a alternativa para os 3 anos de crescimento e calcula o VPL.

    indicadores_base_anoX: resultado de extrair_indicadores para o caso base
                           com fator de carga correspondente (1.0, 1.1, 1.2)

    Retorna dicionário com VPL, benefícios por ano e valor residual.
    """
    print(f"\n>>> Avaliando: {alternativa.descricao}")

    # Simula a proposta para cada ano
    fatores = [1.0, 1.1, 1.2]
    bases = [indicadores_base_ano1, indicadores_base_ano2, indicadores_base_ano3]
    beneficios = []

    for fator, base in zip(fatores, bases):
        print(f"    Rodando proposta com fator de carga {fator:.1f}...")
        resultado_proposta = rodar_cenario(
            dss_file_path=dss_file_path,
            comandos_modificacao=alternativa.comandos_dss,
            fator_carga=fator,
        )
        ind_proposta = extrair_indicadores(resultado_proposta)

        # Benefício = redução de perdas + redução de compensação PRODIST
        delta_perdas = base["perdas_dia_kwh"] - ind_proposta["perdas_dia_kwh"]
        delta_comp = base["compensacao_mensal_usd"] - ind_proposta["compensacao_mensal_usd"]

        ben = financeiro.beneficio_anual(
            delta_perdas_dia_kwh=delta_perdas,
            delta_compensacao_mensal_usd=delta_comp,
            preco_compra_usd_mwh=preco_compra_usd_mwh,
        )
        beneficios.append(ben)
        print(f"    Benefício ano {fatores.index(fator)+1}: USD {ben:,.2f}")

    residual = financeiro.valor_residual_linear(
        custo_instalado_usd=alternativa.custo_inicial_usd,
        vida_util_anos=alternativa.vida_util_anos,
        anos_decorridos=3,
    )

    fluxos = financeiro.montar_fluxos(
        custo_inicial_usd=alternativa.custo_inicial_usd,
        custo_manutencao_anual_usd=alternativa.custo_manutencao_anual_usd,
        beneficio_ano1_usd=beneficios[0],
        beneficio_ano2_usd=beneficios[1],
        beneficio_ano3_usd=beneficios[2],
        residual_usd=residual,
    )

    vpl_resultado = financeiro.vpl(fluxos, taxa)

    return {
        "descricao": alternativa.descricao,
        "custo_inicial_usd": alternativa.custo_inicial_usd,
        "custo_manutencao_anual_usd": alternativa.custo_manutencao_anual_usd,
        "beneficio_ano1_usd": beneficios[0],
        "beneficio_ano2_usd": beneficios[1],
        "beneficio_ano3_usd": beneficios[2],
        "valor_residual_usd": residual,
        "fluxos": fluxos,
        "vpl_usd": vpl_resultado,
        "atrativo": vpl_resultado > 0,
    }


# ---------------------------------------------------------------------------
# Avaliação do caso base para os 3 anos (necessária antes das alternativas)
# ---------------------------------------------------------------------------

def rodar_caso_base_3_anos(
    dss_file_path: str,
    output_folder_base: str,
) -> tuple[dict, dict, dict]:
    """
    Roda o caso base com fatores de carga 1.0, 1.1 e 1.2.
    Retorna tupla (indicadores_ano1, indicadores_ano2, indicadores_ano3).
    """
    resultados = []
    for ano, fator in enumerate([1.0, 1.1, 1.2], start=1):
        print(f"\n>>> Caso base — Ano {ano} (fator de carga {fator:.1f})")
        resultado = rodar_cenario(
            dss_file_path=dss_file_path,
            comandos_modificacao=[],  # sem modificação
            fator_carga=fator,
            output_folder=f"{output_folder_base}_ano{ano}",
        )
        resultados.append(extrair_indicadores(resultado))

    return resultados[0], resultados[1], resultados[2]


# ---------------------------------------------------------------------------
# Impressão da tabela comparativa final
# ---------------------------------------------------------------------------

def imprimir_tabela_comparativa(
    indicadores_base: dict,
    resultados_alternativas: list[dict],
) -> None:
    """
    Imprime no terminal a tabela de comparação entre o caso base e as
    alternativas, com faturamento, custos, compensação e VPL.
    """
    sep = "-" * 80

    print(f"\n{'=' * 80}")
    print("AVALIAÇÃO ECONÔMICA — TRABALHO 1a: PLANEJAMENTO ENERGÉTICO")
    print(f"{'=' * 80}")

    # Caso base (ano 1 nominal)
    resumo = financeiro.resumo_financeiro_caso_base(
        energia_dia_kwh=indicadores_base["energia_dia_kwh"],
        perdas_dia_kwh=indicadores_base["perdas_dia_kwh"],
        compensacao_mensal_usd=indicadores_base["compensacao_mensal_usd"],
    )

    print("\nCASO BASE (Ano 1 — carga nominal):")
    print(sep)
    print(f"  Energia fornecida/mês : {resumo['energia_fornecida_mwh_mes']:>10.2f} MWh")
    print(f"  Perdas/mês            : {resumo['energia_perdas_mwh_mes']:>10.2f} MWh  ({resumo['percentual_perdas_pct']:.2f}%)")
    print(f"  Faturamento/mês       : USD {resumo['faturamento_mensal_usd']:>10,.2f}")
    print(f"  Custo perdas/mês      : USD {resumo['custo_perdas_mensal_usd']:>10,.2f}")
    print(f"  Compensação PRODIST/mês: USD {resumo['compensacao_prodist_mensal_usd']:>9,.2f}")
    print(f"  Resultado operacional : USD {resumo['resultado_operacional_mensal_usd']:>10,.2f}")

    if not resultados_alternativas:
        return

    print(f"\n{'COMPARAÇÃO DAS ALTERNATIVAS (VPL — 3 anos, taxa 14% a.a.)':^80}")
    print(sep)
    print(f"  {'Alternativa':<35} {'CAPEX (USD)':>12} {'VPL (USD)':>12} {'Atrativo':>8}")
    print(sep)

    for r in sorted(resultados_alternativas, key=lambda x: x["vpl_usd"], reverse=True):
        atrativo = "SIM" if r["atrativo"] else "NÃO"
        print(
            f"  {r['descricao']:<35} "
            f"{r['custo_inicial_usd']:>12,.2f} "
            f"{r['vpl_usd']:>12,.2f} "
            f"{atrativo:>8}"
        )

    print(sep)
    melhor = max(resultados_alternativas, key=lambda x: x["vpl_usd"])
    if melhor["atrativo"]:
        print(f"\n  Melhor alternativa: {melhor['descricao']}")
        print(f"  VPL: USD {melhor['vpl_usd']:,.2f}")
    else:
        print("\n  Nenhuma alternativa apresentou VPL positivo.")
    print(f"{'=' * 80}\n")
