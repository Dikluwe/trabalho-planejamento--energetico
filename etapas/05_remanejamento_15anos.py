# Crystalline Lineage
# @layer L3
# @updated 2026-04-05

"""
Estudo de horizonte de 15 anos para carregamento de transformadores.
Otimizado para performance: Redirect único inicial fora do loop.
"""

import sys
import pandas as pd
from dss import dss
from core import configuracao

MASTER = configuracao.MASTER_DSS
CRESCIMENTO = configuracao.CRESCIMENTO
DEGRADACAO_GD = 0.007  # 0.7% ao ano


def rodar_ano_multi(circuit, fator_carga: float, fator_gd: float) -> pd.DataFrame:
    """Coleta carregamento de todos os trafos para um cenário de carga/geração."""

import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

    dss.Text.Command = f"Set LoadMult={fator_carga}"

    # Aplica degradação da GD
    circuit.SetActiveClass("PVSystem")
    idx = circuit.ActiveClass.First
    while idx > 0:
        nome = circuit.ActiveCktElement.Name
        # Original Pmpp (1.0) * fator_gd
        # Simplificação: assume que o valor base no DSS é 1.0 ou nominal
        dss.Text.Command = f"Edit PVSystem.{nome} irradiance={fator_gd}"
        idx = circuit.ActiveClass.Next

    circuit.Solution.Solve()
    if not circuit.Solution.Converged:
        raise RuntimeError(f"FALHA DE CONVERGÊNCIA: Carga {fator_carga}, GD {fator_gd}")

    # Coleta dados
    res = []
    circuit.SetActiveClass("Transformer")
    idx = circuit.ActiveClass.First
    while idx > 0:
        trafo = circuit.ActiveCktElement
        nome = trafo.Name
        kva = float(trafo.Properties("kVA").Val)
        s = configuracao.calcular_potencia_aparente(circuit, nome)
        res.append({"trafo": nome, "loading": 100 * s / kva if kva > 0 else 0})
        idx = circuit.ActiveClass.Next

    return pd.DataFrame(res)


def main():
    circuit = configuracao.inicializar_dss(dss, MASTER)

    print(f"\n{'=' * 80}")
    print(f"[05.05] ESTUDO DE LONGUÍSSIMO PRAZO — 15 ANOS")
    print(
        f"Crescimento: {CRESCIMENTO * 100:.1f}%/ano | Degradação GD: {DEGRADACAO_GD * 100:.1f}%/ano"
    )
    print(f"{'=' * 80}")

    timeline = []
    for ano in range(1, 16):
        f_carga = 1.0 + CRESCIMENTO * (ano - 1)
        f_gd = 1.0 - DEGRADACAO_GD * (ano - 1)
        df = rodar_ano_multi(circuit, f_carga, f_gd)
        df["ano"] = ano
        timeline.append(df)

    full_df = pd.concat(timeline)
    # Pivot para visualização clara
    pivot = full_df.pivot(index="trafo", columns="ano", values="loading")

    # Filtra trafos que excedem 80% em algum momento
    criticos = pivot[pivot.max(axis=1) > 80]

    print("\nTransformadores que atingirão Alerta (>80%) ou Sobrecarga (>100%):")
    print(criticos.round(1))
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
