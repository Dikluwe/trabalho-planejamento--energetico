#!/bin/bash
# renomear.sh
# Renomeia os scripts do trabalho ENG10008 para nomenclatura organizada
# Execute a partir da pasta Finais/:
#   bash renomear.sh
#
# Estrutura de nomes:
#   00_*.py  — módulos base (sem saída direta)
#   01_*.py  — análise principal (entrega)
#   02_*.py  — diagnóstico do trafo crítico
#   03_*.py  — análise de capacitores
#   04_*.py  — análises complementares
#   05_*.py  — análises avançadas e longo prazo
#   06_*.py  — alternativas adicionais
#   07_*.py  — análises finais
#   debug_*  — scripts de depuração (podem ser deletados)

set -e
PASTA="$(pwd)"
echo "Renomeando scripts em: $PASTA"
echo ""

# Verifica se está na pasta certa
if [ ! -f "Master.dss" ]; then
    echo "ERRO: execute a partir da pasta Finais/ (onde está o Master.dss)"
    exit 1
fi

rename_file() {
    local OLD="$1"
    local NEW="$2"
    if [ -f "$OLD" ]; then
        mv "$OLD" "$NEW"
        echo "  OK  $OLD → $NEW"
    else
        echo "  --  $OLD (não encontrado)"
    fi
}

echo "=== MÓDULOS BASE ==="
rename_file "financeiro.py"              "00_financeiro.py"
rename_file "expansao.py"               "00_expansao.py"

echo ""
echo "=== ANÁLISE PRINCIPAL ==="
rename_file "main_trabalho.py"          "01_main_trabalho.py"

echo ""
echo "=== DIAGNÓSTICO DO TRAFO CRÍTICO ==="
rename_file "analisar_trafo.py"         "02_analisar_trafo.py"
rename_file "analisar_linha.py"         "02_analisar_linha.py"
rename_file "horizonte_tap.py"          "02_horizonte_tap.py"
rename_file "remanejamento_trafo.py"    "02_remanejamento_trafo.py"
rename_file "impacto_tap_bt.py"         "02_impacto_tap_bt.py"

echo ""
echo "=== ANÁLISE DE CAPACITORES ==="
rename_file "diagnosticar.py"           "03_diagnosticar_capcontrol.py"
rename_file "testar_capcontrol.py"      "03_testar_capcontrol.py"
rename_file "mapear_reativo.py"         "03_mapear_reativo.py"
rename_file "melhor_ponto_capacitor.py" "03_melhor_ponto_capacitor.py"
rename_file "comparar_capcontrol.py"    "03_comparar_capcontrol.py"

echo ""
echo "=== ANÁLISES COMPLEMENTARES ==="
rename_file "analise_complementar.py"   "04_perfil_tensao_trafos_gd.py"
rename_file "analise_avancada.py"       "04_pior_caso_duracao_degradacao.py"

echo ""
echo "=== ANÁLISES AVANÇADAS E LONGO PRAZO ==="
rename_file "remanejamento_longo_prazo.py" "05_remanejamento_15anos.py"
rename_file "analise_extra.py"          "05_regulador_crescimento_assimetrico.py"
rename_file "analise_montecarlo_gd.py"  "05_montecarlo_despacho_gd.py"

echo ""
echo "=== ALTERNATIVAS ADICIONAIS ==="
rename_file "recondutoramento.py"       "06_recondutoramento.py"
rename_file "novo_trafo.py"             "06_novo_trafo_paralelo.py"

echo ""
echo "=== ANÁLISES FINAIS ==="
rename_file "analise_456.py"            "07_expansao_gd_fluxo_n1.py"
rename_file "analise_final.py"          "07_perfil_tensao_balanco_sensibilidade.py"
rename_file "analise_fp095.py"          "07_analise_fp095.py"
rename_file "analise_final2.py"         "07_arrhenius_breakeven_prodist.py"

echo ""
echo "=== SCRIPTS DE DEPURAÇÃO (podem ser deletados) ==="
for f in debug_*.py debug_raiz*.py; do
    if [ -f "$f" ]; then
        echo "  >>  $f (depuração — deletar se quiser)"
    fi
done

echo ""
echo "Renomeação concluída."
echo ""
echo "Ordem de execução recomendada:"
echo "  uv run python 01_main_trabalho.py"
echo "  uv run python 04_perfil_tensao_trafos_gd.py"
echo "  uv run python 04_pior_caso_duracao_degradacao.py"
echo "  uv run python 05_remanejamento_15anos.py"
echo "  uv run python 06_recondutoramento.py"
echo "  uv run python 06_novo_trafo_paralelo.py"
echo "  uv run python 05_regulador_crescimento_assimetrico.py"
echo "  uv run python 07_expansao_gd_fluxo_n1.py"
echo "  uv run python 07_perfil_tensao_balanco_sensibilidade.py"
echo "  uv run python 07_analise_fp095.py"
echo "  uv run python 07_arrhenius_breakeven_prodist.py"
echo "  uv run python 05_montecarlo_despacho_gd.py"
echo "  uv run python 02_impacto_tap_bt.py"
