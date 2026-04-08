from pathlib import Path

def BuildDefaultPaths():
    """
    Identifica a pasta onde este arquivo (utils.py) está localizado e
    monta os caminhos dos arquivos com base na pasta atual.
    """
    # Identifica a pasta onde este arquivo (utils.py) está localizado
    current_folder = Path(__file__).resolve().parent
    
    # Monta os caminhos dos arquivos com base na pasta atual
    dss_file_path = current_folder / "dss" / "Master.dss"
    output_folder_path = current_folder / "Resultados"
    csv_folder_path = current_folder / "dss" / "buscoords.csv"
    
    # NOVO: Caminho para o arquivo de log
    log_file_path = current_folder / "simulacao.log"
    
    return dss_file_path, output_folder_path, csv_folder_path, log_file_path
