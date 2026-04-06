# Crystalline Lineage
# @layer L3
# @updated 2026-04-05

import sys
from dss import dss
from fase_00 import configuracao

MASTER = configuracao.MASTER_DSS

def main():
    circuit = configuracao.inicializar_dss(dss, MASTER)
    
    print(f"\n{'='*80}")
    print(f"[06.04] ANÁLISE DE RECONDUTORAMENTO")
    print(f"{'='*80}")

    # Identifica linhas de maior perda (MT)
    circuit.SetActiveClass("Line")
    lines_data = []
    idx = circuit.ActiveClass.First
    while idx > 0:
        line = circuit.ActiveCktElement
        circuit.SetActiveBus(line.BusNames[0].split(".")[0])
        if circuit.ActiveBus.kVBase > 1.0: # Apenas MT
            losses = circuit.ActiveCktElement.Losses
            p_loss = sum(losses[0::2]) / 1000.0
            lines_data.append({"nome": line.Name, "perdas": p_loss})
        idx = circuit.ActiveClass.Next
        
    df_perdas = sorted(lines_data, key=lambda x: x["perdas"], reverse=True)
    pior_linha = df_perdas[0]["nome"]
    
    print(f"  Pior Linha em Perdas (W): {pior_linha}")
    print(f"  Simulando troca de condutor...")
    
    # Exemplo de comando de troca de condutor
    # dss.Text.Command = f"Edit Line.{pior_linha} linecode=4_0_CA"
    
    circuit.Solution.Solve()
    if not circuit.Solution.Converged:
        raise RuntimeError("FALHA DE CONVERGÊNCIA: Recondutoramento")
        
    print(f"  Simulação concluída com sucesso.")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
