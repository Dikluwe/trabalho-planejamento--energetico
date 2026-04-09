# Crystalline Lineage
# @layer L3
# @updated 2026-04-08

"""
Avalia o ranking de melhores pontos para instalação de GD.
Refatorado para alta performance: circuito carregado uma vez por worker,
buses distribuídos em chunks para ProcessPoolExecutor.
"""

import sys
import math
import multiprocessing
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

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


def _worker_ranking_chunk(args: tuple) -> list:
    """
    Worker de ranking de GD: testa um subconjunto de barras MT e retorna
    a redução de perdas por injeção de 100 kW em cada barra.
    Cada processo carrega o circuito uma única vez e itera sobre seu chunk.
    Nunca recebe objetos DSS como argumento.
    """
    buses_chunk, loss_base, master_dss = args
    circuit = configuracao.inicializar_dss(dss, master_dss)
    circuit.Solution.Solve()

    dss.Text.Command = (
        "New Generator.GD_TEST phases=3 kv=23.1 kw=100 pf=1.0 model=1 enabled=no"
    )

    results = []
    for bus in buses_chunk:
        circuit.Generators.Name = "GD_TEST"
        circuit.ActiveCktElement.BusNames = [bus]
        circuit.ActiveCktElement.Properties("enabled").Val = "yes"

        circuit.Solution.Solve()
        if not circuit.Solution.Converged:
            circuit.ActiveCktElement.Properties("enabled").Val = "no"
            continue

        loss_new = circuit.Losses[0] / 1000.0
        reduction = loss_base - loss_new
        results.append({"bus": bus, "reduction": reduction})

        circuit.ActiveCktElement.Properties("enabled").Val = "no"

    return results


def main():
    print(f"\n{'=' * 80}")
    print(f"[09.01] RANKING DE GD — MELHOR LOCAL PARA INJEÇÃO")
    print(f"{'=' * 80}")

    # Calcula perdas base no processo principal (sem GD_TEST)
    circuit = configuracao.inicializar_dss(dss, MASTER)
    circuit.Solution.Solve()
    loss_base = circuit.Losses[0] / 1000.0

    buses_mt = []
    for b in circuit.AllBusNames:
        circuit.SetActiveBus(b)
        if circuit.ActiveBus.kVBase > 1.0:
            buses_mt.append(b)

    print(f"  Testando {len(buses_mt)} barramentos para injeção de 100kW...")

    n_workers = min(multiprocessing.cpu_count(), len(buses_mt))
    chunk_size = math.ceil(len(buses_mt) / n_workers)
    chunks = [buses_mt[i : i + chunk_size] for i in range(0, len(buses_mt), chunk_size)]

    worker_args = [(chunk, loss_base, MASTER) for chunk in chunks]

    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=n_workers, mp_context=ctx) as executor:
        futures = [executor.submit(_worker_ranking_chunk, args) for args in worker_args]
        all_results = [r for f in futures for r in f.result()]

    results = sorted(all_results, key=lambda x: x["reduction"], reverse=True)

    print("\n  Top 10 barramentos para redução de perdas:")
    for res in results[:10]:
        print(f"    {res['bus']:<15} {res['reduction']:>10.3f} kW")

    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
