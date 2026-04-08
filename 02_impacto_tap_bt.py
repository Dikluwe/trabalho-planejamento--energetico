# Crystalline Lineage
# @layer L2
# @updated 2026-04-05

import sys
from dss import dss
from fase_00 import configuracao

MASTER = configuracao.MASTER_DSS
TRAFO_ALVO = configuracao.TRAFO_CRITICO


def main():
    circuit = configuracao.inicializar_dss(dss, MASTER)

    # Identifica o barramento secundário via API (BusNames[1])
    circuit.SetActiveElement(f"Transformer.{TRAFO_ALVO}")
    bus_sec = circuit.ActiveCktElement.BusNames[1].split(".")[0].lower()

    print(f"\n{'=' * 80}")
    print(f"[02.06] IMPACTO DO TAP NA TENSÃO BT — {TRAFO_ALVO.upper()}")
    print(f"Barramento Secundário: {bus_sec}")
    print(f"{'=' * 80}")

    for tap in [1.0, 1.025, 1.05]:
        dss.Text.Command = f"Edit Transformer.{TRAFO_ALVO} wdg=1 tap={tap}"
        circuit.Solution.Solve()
        if not circuit.Solution.Converged:
            raise RuntimeError(f"FALHA DE CONVERGÊNCIA: Tap {tap}")

        circuit.SetActiveBus(bus_sec)
        v_pu = circuit.ActiveBus.puVmagAngle
        print(f"  Tap {tap:.3f} | Tensão BT: {min(v_pu[0:6:2]):.4f} pu")

    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
