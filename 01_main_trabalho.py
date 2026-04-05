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
  2.- [x] Criar `parametros.json` com valores atuais do script [Finais/parametros.json](file:///home/dikluwe/Documentos/Antigravity/planejamento-energetico/Finais/parametros.json)
- [x] Modificar `01_main_trabalho.py` para carregar o JSON
- [x] Refatorar a criação da lista `ALTERNATIVAS` em `01_main_trabalho.py`
- [ ] Validar importações e dependências nos módulos `00_*.py`
- [ ] Testar execução completa do script
- [ ] Criar Walkthrough final
"""

import sys
from pathlib import Path

# Garante que Main.py e os módulos novos estão no path
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import Main as professor
import importlib.util
import json

def load_module(name, filename):
    path = HERE / filename
    if not path.exists():
        print(f"ERRO: Arquivo {filename} não encontrado em {HERE}")
        sys.exit(1)
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    # Injeta no sys.modules para que outros scripts possam importar pelo nome curto
    sys.modules[name] = module 
    spec.loader.exec_module(module)
    return module

# Importa módulos com prefixo numérico de forma que as interdependências funcionem
financeiro = load_module("financeiro", "00_financeiro.py")
expansao = load_module("expansao", "00_expansao.py")

from expansao import Alternativa


# ---------------------------------------------------------------------------
# Carregamento de Parâmetros (Arquivo JSON)
# ---------------------------------------------------------------------------

CONFIG_FILE = HERE / "parametros.json"
if not CONFIG_FILE.exists():
    print(f"ERRO: Arquivo de configuração {CONFIG_FILE.name} não encontrado.")
    sys.exit(1)

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

# Configuração de caminhos e arquivos
DSS_FILE = str(HERE / config["caminhos"]["dss_file"])
OUTPUT_BASE = str(HERE / config["caminhos"]["output_base"])

# Parâmetros econômicos
TAXA_DESCONTO = config["economico"]["taxa_desconto"]
TARIFA_VENDA_USD_MWH = config["economico"]["tarifa_venda_usd_mwh"]
PRECO_COMPRA_USD_MWH = config["economico"]["preco_compra_usd_mwh"]
TUSD_USD_MWH = config["economico"]["tusd_usd_mwh"]

# Limites técnicos
LIMITE_MIN_PU = config["tecnico"]["limite_min_pu"]
LIMITE_MAX_PU = config["tecnico"]["limite_max_pu"]

# ---------------------------------------------------------------------------
# Alternativas de intervenção (Carregadas dinamicamente)
# ---------------------------------------------------------------------------

ALTERNATIVAS: list[Alternativa] = []

for alt_data in config["alternativas"]:
    alt = Alternativa(
        descricao=alt_data["descricao"],
        comandos_dss=alt_data["comandos_dss"],
        custo_inicial_usd=alt_data["custo_inicial_usd"],
        custo_manutencao_anual_usd=alt_data.get("custo_manutencao_anual_usd", 0.0),
        vida_util_anos=alt_data.get("vida_util_anos", 15)
    )
    ALTERNATIVAS.append(alt)


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("TRABALHO 1a — PLANEJAMENTO ENERGÉTICO (CRELUZ)")
    print("=" * 80)

    # 1. Caso base para os 3 anos de crescimento
    print("\n[01.01] Rodando caso base para os 3 anos de crescimento de carga...")
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

    print("\n[01.02] Diagnóstico financeiro do caso base (Ano 1 — carga nominal):")
    print(f"  Energia fornecida/mês  : {resumo['energia_fornecida_mwh_mes']:.2f} MWh")
    print(f"  Perdas/mês             : {resumo['energia_perdas_mwh_mes']:.2f} MWh ({resumo['percentual_perdas_pct']:.2f}%)")
    print(f"  Faturamento/mês        : USD {resumo['faturamento_mensal_usd']:,.2f}")
    print(f"  Custo perdas/mês       : USD {resumo['custo_perdas_mensal_usd']:,.2f}")
    print(f"  Compensação PRODIST/mês: USD {resumo['compensacao_prodist_mensal_usd']:,.2f}")
    print(f"  Resultado operacional  : USD {resumo['resultado_operacional_mensal_usd']:,.2f}")

    # 3. Filtra alternativas com comandos DSS definidos
    alternativas_ativas = [a for a in ALTERNATIVAS if a.comandos_dss]

    if not alternativas_ativas:
        print("\n[01.AVISO] Nenhuma alternativa tem comandos DSS definidos.")
        print("        Rode o caso base primeiro, identifique os elementos críticos")
        print("        nos CSVs de saída e preencha os comandos na lista ALTERNATIVAS.")
        print("\n        Arquivos gerados em:", OUTPUT_BASE + "_ano1")
        print("        Consulte: LineSummary.csv e TransformerSummary.csv")
        return

    # 4. Avalia cada alternativa
    print(f"\n[01.03] Avaliando {len(alternativas_ativas)} alternativa(s) de intervenção...")
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
