# Crystalline Lineage
# @prompt 00_nucleo/prompts/expansao.md
# @layer L1
# @updated 2026-04-05

"""
Funções de avaliação de alternativas de expansão para o Trabalho 1a.
Atualizado para utilizar a arquitetura modular rigorosa (DSSSimulation e DailyNetworkAnalyzer).
"""

from __future__ import annotations
import sys
from pathlib import Path
from dataclasses import dataclass
import pandas as pd

# Adiciona a raiz ao path para importar os novos módulos rigorosos
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from dss_engine import DSSSimulation
from data_processor import DailyNetworkAnalyzer
from . import financeiro, configuracao


@dataclass
class Alternativa:
    descricao: str
    comandos_dss: list[str]
    custo_inicial_usd: float
    custo_manutencao_anual_usd: float = 0.0
    vida_util_anos: int = 15


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
    
    if output_folder is None:
        base = Path(dss_file_path).parent
        fator_str = f"{fator_carga:.2f}".replace(".", "p")
        output_folder = str(base / f"_temp_cenario_{fator_str}")

    # 1. Inicializa a engine rigorosa (com trava contra arquivos corrompidos)
    simulacao = DSSSimulation(dss_file=dss_file_path, pv_system=considerar_pv)

    # 2. Aplica modificações de cenário ANTES de resolver o circuito
    if fator_carga != 1.0:
        simulacao.text.Command = f"Set LoadMult={fator_carga}"
        
    for cmd in comandos_modificacao:
        simulacao.text.Command = cmd

    # 3. Instancia o analisador (que agora contém o extrator rigoroso acoplado)
    analisador = DailyNetworkAnalyzer(
        simulador=simulacao,
        total_hours=total_horas,
        low_voltage_kv=limite_bt_kv,
        lower_v_pu=limite_min_pu,
        upper_v_pu=limite_max_pu,
        output_folder=output_folder
    )

    # 4. Executa a simulação, coleta e salva os CSVs (substitui todo o bloco antigo)
    resultados = analisador.run_analysis_and_export()

    return resultados


def extrair_indicadores(
    resultado: dict,
    limite_min_pu: float = 0.95,
    limite_max_pu: float = 1.05,
) -> dict:
    df_energy = resultado["dfEnergySummary"]
    df_voltages = resultado["dfVoltages"]
    df_meter_hour = resultado["dfMeterByHour"]

    medidor = configuracao.MEDIDOR_SUBESTACAO.lower()
    df_medidor = df_energy[df_energy["meterName"].str.lower() == medidor]

    if not df_medidor.empty:
        energia_dia_kwh = df_medidor["totalEnergyKWh"].iloc[0]
        perdas_dia_kwh = df_medidor["totalLossesKWh"].iloc[0]
    else:
        # Fallback para o primeiro medidor se não encontrar pelo nome exato
        energia_dia_kwh = (
            df_energy["totalEnergyKWh"].iloc[0] if not df_energy.empty else 0.0
        )
        perdas_dia_kwh = (
            df_energy["totalLossesKWh"].iloc[0] if not df_energy.empty else 0.0
        )

    compensacao = financeiro.compensacao_prodist_mensal(
        df_voltages=df_voltages,
        df_meter_by_hour=df_meter_hour,
        limite_min_pu=limite_min_pu,
        limite_max_pu=limite_max_pu,
    )

    return {
        "energia_dia_kwh": energia_dia_kwh,
        "perdas_dia_kwh": perdas_dia_kwh,
        "compensacao_mensal_usd": compensacao,
    }


def avaliar_alternativa(
    dss_file_path: str,
    alternativa: Alternativa,
    indicadores_base_ano1: dict,
    indicadores_base_ano2: dict,
    indicadores_base_ano3: dict,
    taxa: float = 0.14,
    preco_compra_usd_mwh: float = 35.0,
) -> dict:
    print(f"\n>>> Avaliando: {alternativa.descricao}")
    c = configuracao.CRESCIMENTO
    fatores = [1.0, 1.0 + c, 1.0 + 2 * c]
    bases = [indicadores_base_ano1, indicadores_base_ano2, indicadores_base_ano3]
    beneficios = []

    for fator, base in zip(fatores, bases):
        resultado_proposta = rodar_cenario(
            dss_file_path=dss_file_path,
            comandos_modificacao=alternativa.comandos_dss,
            fator_carga=fator,
        )
        ind_proposta = extrair_indicadores(
            resultado_proposta,
            limite_min_pu=configuracao.LIMITE_MIN_PU,
            limite_max_pu=configuracao.LIMITE_MAX_PU,
        )
        delta_perdas = base["perdas_dia_kwh"] - ind_proposta["perdas_dia_kwh"]
        delta_comp = (
            base["compensacao_mensal_usd"] - ind_proposta["compensacao_mensal_usd"]
        )

        ben = financeiro.beneficio_anual(
            delta_perdas_dia_kwh=delta_perdas,
            delta_compensacao_mensal_usd=delta_comp,
            preco_compra_usd_mwh=preco_compra_usd_mwh,
        )
        beneficios.append(ben)

    residual = financeiro.valor_residual_linear(
        alternativa.custo_inicial_usd, alternativa.vida_util_anos, 3
    )
    fluxos = financeiro.montar_fluxos(
        alternativa.custo_inicial_usd,
        alternativa.custo_manutencao_anual_usd,
        beneficios[0],
        beneficios[1],
        beneficios[2],
        residual,
    )
    vpl_resultado = financeiro.vpl(fluxos, taxa)

    return {
        "descricao": alternativa.descricao,
        "custo_inicial_usd": alternativa.custo_inicial_usd,
        "vpl_usd": vpl_resultado,
        "atrativo": vpl_resultado > 0,
    }


def rodar_caso_base_3_anos(
    dss_file_path: str, output_folder_base: str
) -> tuple[dict, dict, dict]:
    resultados = []
    c = configuracao.CRESCIMENTO
    for ano, fator in enumerate([1.0, 1.0 + c, 1.0 + 2 * c], start=1):
        print(f"\n>>> Caso base — Ano {ano} (fator {fator})")
        resultado = rodar_cenario(
            dss_file_path, [], fator, output_folder=f"{output_folder_base}_ano{ano}"
        )
        resultados.append(
            extrair_indicadores(
                resultado,
                limite_min_pu=configuracao.LIMITE_MIN_PU,
                limite_max_pu=configuracao.LIMITE_MAX_PU,
            )
        )
    return resultados[0], resultados[1], resultados[2]


def imprimir_tabela_comparativa(
    indicadores_base: dict, resultados_alternativas: list[dict]
) -> None:
    print(f"\n{'=' * 80}\n[01.04] FINALIZAÇÃO — RESULTADOS COMPARATIVOS\n{'=' * 80}")
    resumo = financeiro.resumo_financeiro_caso_base(
        indicadores_base["energia_dia_kwh"],
        indicadores_base["perdas_dia_kwh"],
        indicadores_base["compensacao_mensal_usd"],
    )
    print(f"  Faturamento Base: USD {resumo['faturamento_mensal_usd']:,.2f}")
    for r in sorted(resultados_alternativas, key=lambda x: x["vpl_usd"], reverse=True):
        print(f"  {r['descricao']:<35} | VPL: USD {r['vpl_usd']:>12,.2f}")
    print("=" * 80)