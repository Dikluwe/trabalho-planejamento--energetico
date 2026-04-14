import sys
import csv
from pathlib import Path

# Configuração de caminhos
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import configuracao

def gerar_balanco_financeiro():
    print("=" * 70)
    print("ETAPA 15 — BALANÇO FINANCEIRO DINÂMICO (CRELUZ)")
    print("=" * 70)

    # Parâmetros Econômicos
    TARIFA = configuracao.TARIFA_VENDA   # 150 USD/MWh
    CUSTO_P = configuracao.PRECO_COMPRA  # 35 USD/MWh
    
    def ler_ano(ano):
        caminho = ROOT / "resultados" / f"ano{ano}" / "DailyNetworkSummary.csv"
        if not caminho.exists():
            return None
        with open(caminho, "r", encoding="utf-8") as f:
            return next(csv.DictReader(f))

    print(f"\n{'Ano':<5} | {'Energia (MWh/m)':<15} | {'Faturamento (USD)':<18} | {'Perdas (USD)':<12} | {'Margem Oper.':<12}")
    print("-" * 75)

    for ano in [1, 2, 3]:
        dados = ler_ano(ano)
        if not dados:
            continue
            
        e_dia = float(dados["totalEnergyKWh"])
        p_dia = float(dados["totalLossesKWh"])
        
        e_mes_mwh = (e_dia * 30) / 1000
        p_mes_mwh = (p_dia * 30) / 1000
        
        faturamento = e_mes_mwh * TARIFA
        custo_perdas = p_mes_mwh * CUSTO_P
        valor_liquido = faturamento - custo_perdas
        margem = (valor_liquido / faturamento) * 100 if faturamento > 0 else 0
        
        print(f"Ano {ano:<1} | {e_mes_mwh:>15.2f} | {faturamento:>18,.2f} | {custo_perdas:>12,.2f} | {margem:>11.2f}%")

    print("-" * 75)
    print(f"\nPremissas: Venda = {TARIFA} USD/MWh | Compra Perdas = {CUSTO_P} USD/MWh")
    print("Ref: Módulo Financeiro Crystalline L1")
    print("=" * 70)

if __name__ == "__main__":
    gerar_balanco_financeiro()
