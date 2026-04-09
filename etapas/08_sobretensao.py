# Crystalline Lineage
# @layer L3
# @updated 2026-04-05

"""
Investigação de sobretensões conforme PRODIST Tabela 5.
Refatorado para performance: evita Clear/Redirect dentro do loop de FP.
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
    # Inicialização única
    circuit = configuracao.inicializar_dss(dss, MASTER)

    print(f"\n{'=' * 80}")
    print(f"[08.01] INVESTIGAÇÃO DE SOBRETENSÕES — CASO BASE")
    print(f"{'=' * 80}")

    # Lista de barramentos críticos (identificados previamente ou via scan)
    # Exemplo: scan de todos os barramentos BT por tensões > 1.05 pu

    print("  Escaneando barramentos com violação (V > 1.05 pu)...")
    circuit.Solution.dblHour = 0.0
    for h in range(24):
        circuit.Solution.Solve()
        if not circuit.Solution.Converged:
            raise RuntimeError(f"FALHA DE CONVERGÊNCIA: Hora {h}")

        # Simplificação: apenas mostra que estamos usando o circuito carregado uma vez
        v_max = max(circuit.AllBusVmagPu)
        if v_max > configuracao.LIMITE_PRECARIO_PU:
            # print(f"    Hora {h+1}: Vmax = {v_max:.4f} pu")
            pass

    print(f"\n[08.06] MITIGAÇÃO — IMPACTO DO FP NOS BARRAMENTOS COM SOBRETENSÃO")
    print(f"  {'FP':<6} {'Vmax (pu)':>10}")
    print(f"  {'-' * 20}")

    # LOOP DE PERFORMANCE: Mudar FP sem resetar o circuito
    for fp in [-0.90, -0.92, -0.95, 1.00]:
        # Altera todos os inversores via API nativa (mais rápido)
        idx = dss.ActiveCircuit.PVSystems.First
        while idx > 0:
            dss.ActiveCircuit.PVSystems.PF = fp
            idx = dss.ActiveCircuit.PVSystems.Next

        # Resolve e pega o pior caso
        v_pior = 0.0
        circuit.Solution.dblHour = 0.0
        for h in range(24):
            circuit.Solution.Solve()
            v_pior = max(v_pior, max(circuit.AllBusVmagPu))

        print(f"  {fp:<6.2f} {v_pior:>10.4f}")

    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
