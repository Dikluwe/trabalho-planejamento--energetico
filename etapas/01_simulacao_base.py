# Crystalline Lineage
# @layer L2
# @updated 2026-04-08

"""
Etapa 01: Simulação Base e Avaliação de Alternativas.
Substitui os antigos main_trabalho.py e fase_00/expansao.py.
"""

import sys
import multiprocessing
from pathlib import Path
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor

# Adiciona a raiz ao path para encontrar o pacote 'core'
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import configuracao, financeiro, dss_engine, data_processor
from dss import dss

@dataclass
class Alternativa:
    descricao: str
    comandos_dss: list[str]
    custo_inicial_usd: float
    custo_manutencao_anual_usd: float = 0.0
    vida_util_anos: int = 15


def _worker_avaliar_alternativa(args: tuple) -> dict:
    """
    Worker de topo de módulo para ProcessPoolExecutor (exigido pelo pickle com spawn).
    Cada processo cria seu próprio engine DSS via rodar_cenario → DSSSimulation.
    Recebe apenas tipos serializáveis; nenhum objeto DSS trafega entre processos.
    """
    dss_file_path, alternativa, indicadores_base, alt_idx = args
    c = configuracao.CRESCIMENTO
    fatores = [1.0, 1.0 + c, 1.0 + 2 * c]

    # Pasta temporária única por alternativa para evitar escrita concorrente
    def _out(fator: float) -> str:
        fator_str = f"{fator:.2f}".replace(".", "p")
        return str(configuracao.RESULTADOS_DIR / f"_temp_alt{alt_idx}_{fator_str}")

    print(f"\n>>> Avaliando: {alternativa.descricao}")
    beneficios = []
    for fator, base in zip(fatores, indicadores_base):
        resultado_proposta = rodar_cenario(
            dss_file_path=dss_file_path,
            comandos_modificacao=alternativa.comandos_dss,
            fator_carga=fator,
            output_folder=_out(fator),
        )
        ind_proposta = extrair_indicadores(
            resultado_proposta,
            limite_min_pu=configuracao.LIMITE_MIN_PU,
            limite_max_pu=configuracao.LIMITE_MAX_PU,
        )
        ben = financeiro.beneficio_anual(
            delta_perdas_dia_kwh=base["perdas_dia_kwh"] - ind_proposta["perdas_dia_kwh"],
            delta_compensacao_mensal_usd=base["compensacao_mensal_usd"] - ind_proposta["compensacao_mensal_usd"],
            preco_compra_usd_mwh=configuracao.PRECO_COMPRA,
        )
        beneficios.append(ben)

    residual = financeiro.valor_residual_linear(alternativa.custo_inicial_usd, alternativa.vida_util_anos, 3)
    fluxos = financeiro.montar_fluxos(
        alternativa.custo_inicial_usd,
        alternativa.custo_manutencao_anual_usd,
        beneficios[0], beneficios[1], beneficios[2],
        residual,
    )
    vpl_resultado = financeiro.vpl(fluxos, configuracao.TAXA_DESCONTO)

    return {
        "descricao": alternativa.descricao,
        "custo_inicial_usd": alternativa.custo_inicial_usd,
        "vpl_usd": vpl_resultado,
        "atrativo": vpl_resultado > 0,
    }


def rodar_cenario(
    dss_file_path: str,
    comandos_modificacao: list[str],
    fator_carga: float = 1.0,
    considerar_pv: bool = True,
    total_horas: int = 24,
    limite_bt_kv: float = 1.0,
    limite_min_pu: float = configuracao.LIMITE_MIN_PU,
    limite_max_pu: float = configuracao.LIMITE_MAX_PU,
    output_folder: str | None = None,
) -> dict:
    if output_folder is None:
        base = configuracao.RESULTADOS_DIR
        fator_str = f"{fator_carga:.2f}".replace(".", "p")
        output_folder = str(base / f"_temp_cenario_{fator_str}")

    simulacao = dss_engine.DSSSimulation(dss_file=dss_file_path, pv_system=considerar_pv)

    if fator_carga != 1.0:
        simulacao.text.Command = f"Set LoadMult={fator_carga}"
        
    for cmd in comandos_modificacao:
        simulacao.text.Command = cmd

    analisador = data_processor.DailyNetworkAnalyzer(
        simulador=simulacao,
        total_hours=total_horas,
        low_voltage_kv=limite_bt_kv,
        lower_v_pu=limite_min_pu,
        upper_v_pu=limite_max_pu,
        output_folder=output_folder
    )

    return analisador.run_analysis_and_export()

def extrair_indicadores(resultado: dict, limite_min_pu: float, limite_max_pu: float) -> dict:
    df_energy = resultado["dfEnergySummary"]
    df_voltages = resultado["dfVoltages"]
    df_meter_hour = resultado["dfMeterByHour"]

    medidor = configuracao.MEDIDOR_SUBESTACAO.lower()
    df_medidor = df_energy[df_energy["meterName"].str.lower() == medidor]

    if not df_medidor.empty:
        energia_dia_kwh = df_medidor["totalEnergyKWh"].iloc[0]
        perdas_dia_kwh = df_medidor["totalLossesKWh"].iloc[0]
    else:
        energia_dia_kwh = df_energy["totalEnergyKWh"].iloc[0] if not df_energy.empty else 0.0
        perdas_dia_kwh = df_energy["totalLossesKWh"].iloc[0] if not df_energy.empty else 0.0

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
        "df_meter_by_hour": df_meter_hour,
    }

def main():
    print("=" * 80)
    print("ETAPA 01 — SIMULAÇÃO BASE E ALTERNATIVAS (CRELUZ)")
    print("=" * 80)

    # 1. Caso base para os 3 anos
    print("\n[01.01] Rodando caso base (3 anos)...")
    indicadores_base = []
    c = configuracao.CRESCIMENTO
    for ano, fator in enumerate([1.0, 1.0 + c, 1.0 + 2 * c], start=1):
        print(f"      Ano {ano} (fator {fator})...")
        out_folder = str(configuracao.RESULTADOS_DIR / f"ano{ano}")
        res = rodar_cenario(configuracao.MASTER_DSS, [], fator, output_folder=out_folder)
        indicadores_base.append(extrair_indicadores(res, configuracao.LIMITE_MIN_PU, configuracao.LIMITE_MAX_PU))

    # 2. Diagnóstico financeiro Ano 1
    ind_1 = indicadores_base[0]
    resumo = financeiro.resumo_financeiro_caso_base(ind_1["energia_dia_kwh"], ind_1["perdas_dia_kwh"], ind_1["compensacao_mensal_usd"], df_meter_by_hour=ind_1["df_meter_by_hour"])
    
    print("\n[01.02] Diagnóstico financeiro (Ano 1):")
    print(f"  Energia Fornecida : {resumo['energia_fornecida_mwh_mes']:.2f} MWh/mês")
    print(f"  Perdas            : {resumo['energia_perdas_mwh_mes']:.2f} MWh/mês ({resumo['percentual_perdas_pct']:.2f}%)")
    print(f"  Resultado Operac. : USD {resumo['resultado_operacional_mensal_usd']:,.2f}/mês")

    # 3. Avaliação de alternativas
    alts_config = configuracao.config["alternativas"]
    alts = [Alternativa(a["descricao"], a["comandos_dss"], a["custo_inicial_usd"], a.get("custo_manutencao_anual_usd", 0.0), a.get("vida_util_anos", 15)) for a in alts_config if a["comandos_dss"]]

    if not alts:
        print("\n[AVISO] Nenhuma alternativa configurada.")
        return

    print(f"\n[01.03] Avaliando {len(alts)} alternativa(s) em paralelo...")
    worker_args = [
        (configuracao.MASTER_DSS, alt, indicadores_base, idx)
        for idx, alt in enumerate(alts)
    ]
    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=len(alts), mp_context=ctx) as executor:
        futures = [executor.submit(_worker_avaliar_alternativa, args) for args in worker_args]
        resultados = [f.result() for f in futures]

    # 4. Tabela Final
    print(f"\n{'=' * 80}\n[01.04] RESULTADOS COMPARATIVOS (VPL)\n{'=' * 80}")
    for r in sorted(resultados, key=lambda x: x["vpl_usd"], reverse=True):
        print(f"  {r['descricao']:<40} | VPL: USD {r['vpl_usd']:>12,.2f}")
    print("=" * 80)

if __name__ == "__main__":
    main()
