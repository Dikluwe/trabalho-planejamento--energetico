# Crystalline Lineage
# @layer L3
# @updated 2026-04-05

"""
Estudo de horizonte de 15 anos para carregamento de transformadores.
Otimizado para performance: Redirect único inicial fora do loop.
"""

import sys
from pathlib import Path

# 1. Ajuste do PATH absoluto (Sempre no topo, antes de qualquer importação externa ou interna)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 2. Imports de bibliotecas e pacotes locais
import pandas as pd
from dss import dss
from core import configuracao
import json

# 3. Definição das variáveis globais
MASTER = configuracao.MASTER_DSS
CRESCIMENTO = configuracao.CRESCIMENTO
DEGRADACAO_GD = 0.007  # 0.7% ao ano

def rodar_ano_multi(circuit, fator_carga: float, fator_gd: float) -> pd.DataFrame:
    """Coleta pico de carregamento diário de todos os trafos para um cenário de carga/geração."""
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    dss.Text.Command = f"Set LoadMult={fator_carga}"

    # Aplica degradação da GD
    circuit.SetActiveClass("PVSystem")
    idx = circuit.ActiveClass.First
    while idx > 0:
        nome = circuit.ActiveCktElement.Name
        dss.Text.Command = f"Edit PVSystem.{nome} irradiance={fator_gd}"
        idx = circuit.ActiveClass.Next

    # Simula 24 horas e registra o pico de carregamento por trafo
    peak_loading: dict = {}
    circuit.Solution.dblHour = 0.0

    for _ in range(24):
        circuit.Solution.Solve()
        if not circuit.Solution.Converged:
            raise RuntimeError(f"FALHA DE CONVERGÊNCIA: Carga {fator_carga}, GD {fator_gd}")

        circuit.SetActiveClass("Transformer")
        idx = circuit.ActiveClass.First
        while idx > 0:
            trafo = circuit.ActiveCktElement
            nome = trafo.Name
            kva = float(trafo.Properties("kVA").Val)
            s = configuracao.calcular_potencia_aparente(circuit, nome)
            loading = 100 * s / kva if kva > 0 else 0
            if loading > peak_loading.get(nome, 0):
                peak_loading[nome] = loading
            idx = circuit.ActiveClass.Next

    return pd.DataFrame(
        [{"trafo": nome, "loading": loading} for nome, loading in peak_loading.items()]
    )


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
