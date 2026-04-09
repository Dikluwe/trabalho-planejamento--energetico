# Crystalline Lineage
# @layer L2
# @updated 2026-04-05

"""
Identifica a linha com maior carregamento relativo (%) da rede.
Refatorado para a nova estrutura de dados dss-python.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
from dss import dss
from core import configuracao


MASTER = configuracao.MASTER_DSS


def main():
    circuit = configuracao.inicializar_dss(dss, MASTER)

    print(f"\n{'=' * 80}")
    print(f"[02.05] ANÁLISE DE LINHAS — CARREGAMENTO MÁXIMO")
    print(f"{'=' * 80}")

    max_loading = 0.0
    pior_linha = ""

    # Garante que o circuito foi resolvido antes de ler correntes
    circuit.Solution.Solve()

    circuit.SetActiveClass("Line")
    idx = circuit.ActiveClass.First
    while idx > 0:
        el = circuit.ActiveCktElement
        nome = el.Name

        # CurrentsMagAng retorna [mag1, ang1, mag2, ang2, ...]
        # Pegamos apenas as magnitudes (indices pares) do primeiro terminal
        mags_ang = el.CurrentsMagAng
        num_phases = el.NumPhases

        # Limit de corrente (NormAmps)
        limit = float(el.Properties("normamps").Val)

        if limit > 0 and len(mags_ang) >= num_phases * 2:
            # Pega magnitudes das fases no Terminal 1
            mags = mags_ang[0 : num_phases * 2 : 2]
            current = max(mags)
            loading = 100 * current / limit

            if loading > max_loading:
                max_loading = loading
                pior_linha = nome

        idx = circuit.ActiveClass.Next

    print(f"  Pior Linha: {pior_linha}")
    print(f"  Carregamento: {max_loading:.2f}%")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
