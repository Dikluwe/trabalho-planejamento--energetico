import sys
import subprocess
from pathlib import Path
import time
from datetime import datetime

HERE = Path(__file__).resolve().parent
RESULTADOS_DIR = HERE / "Resultados"
LOG_FILE = RESULTADOS_DIR / "relatorio_tecnico_completo.txt"

# Garante que as subpastas base existam
RESULTADOS_DIR.mkdir(exist_ok=True)
(RESULTADOS_DIR / "graficos").mkdir(exist_ok=True)

# Listagem sequencial de execução (DAG)
PIPELINE = [
    (
        "[00.01] FASE 1: SIMULAÇÃO BASE E MÓDULOS NUCLEARES",
        [
            "main_trabalho.py"  # Renomeado conforme diretriz
        ],
    ),
    (
        "[00.02] FASE 2: ORQUESTRAÇÃO DE SOLUÇÕES (ATUALIZAÇÃO DE BANCO)",
        [
            "03_melhor_ponto_capacitor.py",
        ],
    ),
    (
        "[00.03] FASE 3: ESTUDOS E DIMENSIONAMENTOS (LENDO JSON)",
        [
            "02_analisar_trafo.py",
            "02_analisar_linha.py",
            "02_horizonte_tap.py",
            "02_impacto_tap_bt.py",
            "02_remanejamento_trafo.py",
            "03_diagnosticar_capcontrol.py",
            "03_testar_capcontrol.py",
            "03_comparar_capcontrol.py",
            "04_perfil_tensao_trafos_gd.py",
            "04_pior_caso_duracao_degradacao.py",
            "05_montecarlo_despacho_gd.py",
            "05_regulador_crescimento_assimetrico.py",
            "05_remanejamento_15anos.py",
            "06_novo_trafo_paralelo.py",
            "06_recondutoramento.py",
            "07_analise_fp095.py",
            "07_arrhenius_breakeven_prodist.py",
            "07_expansao_gd_fluxo_n1.py",
            "07_perfil_tensao_balanco_sensibilidade.py",
            "08_sobretensao.py",
            "09_ranking_gd.py",
        ],
    ),
    (
        "[00.04] FASE 4: EXPORTADORES E RENDERIZADORES GRAFICOS",
        [
            "10_exportar_geojson.py",
            "10_exportar_rede_svg.py",
            "10_exportar_rede_svg_geo.py",
            "11_graficos_svg.py",
        ],
    ),
]


class LoggerMultiStream:
    """Interceptor para fazer 'tee' (mandar para console e arquivo simultaneamente)."""

    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.logfile = open(filepath, "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.logfile.write(message)
        self.flush()

    def flush(self):
        self.terminal.flush()
        self.logfile.flush()


def log(msg=""):
    print(msg)


def rodar_script(nome_script):
    caminho = HERE / nome_script
    if not caminho.exists():
        log(f"      [ERRO] Script não encontrado: {nome_script}")
        return False

    log(f"\n[{datetime.now().strftime('%H:%M:%S')}] >>> Executando {nome_script} ...")
    inicio = time.time()

    # Roda usando o executável do Python ATUAL (mais robusto que uv run explícito)
    # Garante que o ambiente virtual atual seja usado
    comando = [sys.executable, nome_script]

    try:
        # Usa Popen para capturar output em tempo real e enviar para o LoggerMultiStream
        processo = subprocess.Popen(
            comando,
            cwd=str(HERE),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )

        # Lê a saída em tempo real
        for linha in processo.stdout:
            sys.stdout.write(f"      {linha}")
            sys.stdout.flush()

        processo.wait()

        if processo.returncode != 0:
            log(
                f"      [FALHA] O script {nome_script} retornou código {processo.returncode}"
            )
            return False

        tempo = time.time() - inicio
        log(f"      [OK] Finalizado {nome_script} em {tempo:.2f}s")
        return True
    except Exception as e:
        log(f"      [ERRO CRÍTICO] Falha ao executar {nome_script}: {e}")
        return False


def main():
    sys.stdout = LoggerMultiStream(LOG_FILE)
    sys.stderr = sys.stdout

    log("=" * 80)
    log(
        f"PIPELINE DE PLANEJAMENTO ENERGÉTICO INICIADA — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    log("=" * 80)
    log(f"Os relatórios e prints estão sendo salvos em: {LOG_FILE}\n")

    t_global = time.time()
    erros = 0

    for fase_titulo, scripts in PIPELINE:
        log("\n" + "=" * 80)
        log(f"   {fase_titulo}")
        log("=" * 80)

        for script in scripts:
            sucesso = rodar_script(script)
            if not sucesso:
                erros += 1
                log(
                    f"\n[!] Falha ao executar {script}. Execução interrompida para inspeção."
                )
                return 1

    tempo_total = time.time() - t_global

    log("\n" + "=" * 80)
    if erros == 0:
        log(f"[00.05] PIPELINE CONCLUÍDA COM SUCESSO EM {tempo_total:.2f} SEGUNDOS")
    else:
        log(f"PIPELINE FINALIZADA COM {erros} ERRO(S)")
    log("=" * 80)


if __name__ == "__main__":
    exit(main())
