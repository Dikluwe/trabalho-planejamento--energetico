# Crystalline Lineage
# @layer L3
# @updated 2026-04-05

"""
Avalia o ranking de melhores pontos para instalação de GD.
Refatorado para alta performance: circuito carregado uma vez, GDs injetadas dinamicamente via 'Edit'.
"""

import sys
from pathlib import Path

# 1. Ajuste do PATH absoluto (Sempre no topo)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 2. Imports locais e dependências
from dss import dss
from core import configuracao

# 3. Definição de variáveis globais
MASTER = configuracao.MASTER_DSS

def main():
    circuit = configuracao.inicializar_dss(dss, MASTER)

    print(f"\n{'=' * 80}")
    print(f"[09.01] RANKING DE GD — MELHOR LOCAL PARA INJEÇÃO")
    print(f"{'=' * 80}")

    # Coleta perdas base
    circuit.Solution.Solve()
    loss_base = circuit.Losses[0] / 1000.0

    results = []

    # Escaneia todos os barramentos MT para testar injeção de 100kW
    buses_mt = []
    for b in circuit.AllBusNames:
        circuit.SetActiveBus(b)
        if circuit.ActiveBus.kVBase > 1.0:  # Apenas MT
            buses_mt.append(b)

    print(f"  Testando {len(buses_mt)} barramentos para injeção de 100kW...")

    # Cria o gerador de teste uma ÚNICA VEZ (desabilitado inicialmente)
    dss.Text.Command = (
        "New Generator.GD_TEST phases=3 kv=23.1 kw=100 pf=1.0 model=1 enabled=no"
    )

    for b in buses_mt:
        # Usa interface de objeto (muito mais rápido que dss.Text)
        circuit.Generators.Name = "GD_TEST"
        circuit.ActiveCktElement.BusNames = [b]
        circuit.ActiveCktElement.Properties("enabled").Val = "yes"

        circuit.Solution.Solve()
        if not circuit.Solution.Converged:
            circuit.ActiveCktElement.Properties("enabled").Val = "no"
            continue

        loss_new = circuit.Losses[0] / 1000.0
        reduction = loss_base - loss_new
        results.append({"bus": b, "reduction": reduction})

        # Desabilita via objeto
        circuit.ActiveCktElement.Properties("enabled").Val = "no"

    # Ordena e mostra top 10
    results.sort(key=lambda x: x["reduction"], reverse=True)

    print("\n  Top 10 barramentos para redução de perdas:")
    for res in results[:10]:
        print(f"    {res['bus']:<15} {res['reduction']:>10.3f} kW")

    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
