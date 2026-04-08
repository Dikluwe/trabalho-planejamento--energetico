# Crystalline Lineage
# @layer L3
# @updated 2026-04-05

"""
Avalia o impacto de alterar o fator de potência das GDs para 0.95 capacitivo.
Refatorado para performance: circuito carregado uma única vez.
"""

import sys
from dss import dss
from core import configuracao

import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


MASTER = configuracao.MASTER_DSS


def set_fp(pf):
    idx = dss.ActiveCircuit.PVSystems.First
    while idx > 0:
        dss.ActiveCircuit.PVSystems.PF = pf
        idx = dss.ActiveCircuit.PVSystems.Next


def main():
    circuit = configuracao.inicializar_dss(dss, MASTER)

    print(f"\n{'=' * 80}")
    print(f"[07.01] ANÁLISE DE IMPACTO DE FATOR DE POTÊNCIA (FP 0.95 CAP)")
    print(f"{'=' * 80}")

    # Coleta tensões base (FP 1.0)
    v_max_base = 0.0
    circuit.Solution.dblHour = 0.0
    for h in range(24):
        circuit.Solution.Solve()
        if not circuit.Solution.Converged:
            raise RuntimeError(f"FALHA DE CONVERGÊNCIA: Base, Hora {h}")
        v_max_base = max(v_max_base, max(circuit.AllBusVmagPu))

    print(f"  Vmax Base (FP 1.0): {v_max_base:.4f} pu")

    # Aplica FP 0.95 em todos os inversores (Capacitivo p/ mitigar sobretensão)
    set_fp(-0.95)

    # Coleta novas tensões
    v_max_novo = 0.0
    circuit.Solution.dblHour = 0.0
    for h in range(24):
        circuit.Solution.Solve()
        if not circuit.Solution.Converged:
            raise RuntimeError(f"FALHA DE CONVERGÊNCIA: Novo FP, Hora {h}")
        v_max_novo = max(v_max_novo, max(circuit.AllBusVmagPu))

    print(f"  Vmax Novo (FP 0.95): {v_max_novo:.4f} pu")
    print(f"  Redução de Tensão  : {v_max_base - v_max_novo:.4f} pu")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
