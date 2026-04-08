import logging
from utils import BuildDefaultPaths
from dss_engine import DSSSimulation
from data_processor import DailyNetworkAnalyzer


def main():
    # 1. Define os caminhos dos arquivos (agora com 4 variáveis)
    dssFilePath, outputFolderPath, csvFolderPath, logFilePath = BuildDefaultPaths()

    # 2. Configura o sistema de log
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        handlers=[
            logging.FileHandler(
                logFilePath, mode="w", encoding="utf-8"
            ),  # Salva no arquivo
            logging.StreamHandler(),  # Mostra no terminal
        ],
    )

    # 3. Define os parâmetros básicos da simulação
    consider_pv = True
    total_hours = 24
    low_voltage_limit_kv = 1.0
    lower_voltage_pu = 0.95
    upper_voltage_pu = 1.05

    logging.info("Iniciando configuração do circuito no OpenDSS...")

    simulacao = DSSSimulation(dss_file=str(dssFilePath), pv_system=consider_pv)

    logging.info("Executando simulação e processando os dados...")

    analisador = DailyNetworkAnalyzer(
        simulador=simulacao,
        total_hours=total_hours,
        low_voltage_kv=low_voltage_limit_kv,
        lower_v_pu=lower_voltage_pu,
        upper_v_pu=upper_voltage_pu,
        output_folder=str(outputFolderPath),
    )

    resultados = analisador.run_analysis_and_export()

    logging.info("Simulação concluída com sucesso.")

    # Os resumos finais ainda podem usar print, pois são apenas tabelas visuais para o usuário final
    print("\nResumo diário da rede:\n")
    print(resultados["dfNetworkSummary"].to_string(index=False))

    print("\nTop 10 cabos mais carregados:\n")
    print(resultados["dfLineSummary"].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
