# Crystalline Lineage
# @layer L2
# @updated 2026-04-05

"""
Analisa o carregamento e tensões nos terminais do transformador crítico.
Refatorado para usar API nativa de identificação de barramentos (BusNames).
"""

import sys
import pandas as pd
from dss import dss
from fase_00 import configuracao

# Configurações centralizadas
MASTER = configuracao.MASTER_DSS
TRAFO_ALVO = configuracao.TRAFO_CRITICO


def main():
    circuit = configuracao.inicializar_dss(dss, MASTER)

    # Identificação DINÂMICA dos barramentos (Correção Sugerida!)
    circuit.SetActiveElement(f"Transformer.{TRAFO_ALVO}")
    if not circuit.ActiveCktElement:
        raise RuntimeError(f"Transformador {TRAFO_ALVO} não encontrado.")

    bus_prim = circuit.ActiveCktElement.BusNames[0].split(".")[0].lower()
    bus_sec = circuit.ActiveCktElement.BusNames[1].split(".")[0].lower()

    print(f"\n{'=' * 80}")
    print(f"[02.04] ANÁLISE DINÂMICA — {TRAFO_ALVO.upper()}")
    print(f"  Barramento Primário   (MT): {bus_prim}")
    print(f"  Barramento Secundário (BT): {bus_sec}")
    print(f"{'=' * 80}")

    # Coleta de dados (Exemplo simplificado de diagnóstico)
    pmax = 0.0
    v_min_bt = 2.0

    for h in range(24):
        circuit.Solution.Solve()
        if not circuit.Solution.Converged:
            raise RuntimeError(f"FALHA DE CONVERGÊNCIA: Hora {h}")

        circuit.SetActiveElement(f"Transformer.{TRAFO_ALVO}")
        # Carregamento
        powers = circuit.ActiveCktElement.Powers
        s = (sum(powers[0:6:2]) ** 2 + sum(powers[1:6:2]) ** 2) ** 0.5
        pmax = max(pmax, s)

        # Tensão no secundário
        circuit.SetActiveBus(bus_sec)
        v_pu = circuit.ActiveBus.puVmagAngle
        v_min_bt = min(v_min_bt, min(v_pu[0:6:2]))

    print(f"  Potência Máxima: {pmax:.2f} kVA")
    print(f"  Tensão Mínima  : {v_min_bt:.4f} pu")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
