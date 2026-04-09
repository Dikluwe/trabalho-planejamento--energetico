# Crystalline Lineage
# @layer L3
# @updated 2026-04-05

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
TRAFO_ALVO = configuracao.TRAFO_CRITICO

def main():
    circuit = configuracao.inicializar_dss(dss, MASTER)

    # Identifica barramento MT e BT do trafo original
    circuit.SetActiveElement(f"Transformer.{TRAFO_ALVO}")
    bus_mt = circuit.ActiveCktElement.BusNames[0].split(".")[0]
    bus_bt = circuit.ActiveCktElement.BusNames[1].split(".")[0]

    print(f"\n{'=' * 80}")
    print(f"[06.01] MODELAGEM DE TRAFO PARALELO — {TRAFO_ALVO.upper()}")
    print(f"Buses: {bus_mt} (MT) <-> {bus_bt} (BT)")
    print(f"{'=' * 80}")

    # Simulação da instalação de um novo trafo idêntico em paralelo
    dss.Text.Command = f"New Transformer.trf_paralelo phases=3 windings=2 kva=30 kv=[23.1, 0.38] buses=[{bus_mt}, {bus_bt}]"

    circuit.Solution.Solve()
    if not circuit.Solution.Converged:
        raise RuntimeError("FALHA DE CONVERGÊNCIA: Trafo paralelo")

    circuit.SetActiveElement(f"Transformer.{TRAFO_ALVO}")
    p1 = configuracao.calcular_potencia_aparente(circuit, TRAFO_ALVO)

    circuit.SetActiveElement("Transformer.trf_paralelo")
    p2 = configuracao.calcular_potencia_aparente(circuit, "trf_paralelo")

    print(f"  Carregamento Trafo Antigo: {100 * p1 / 30:.2f}%")
    print(f"  Carregamento Trafo Novo  : {100 * p2 / 30:.2f}%")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
