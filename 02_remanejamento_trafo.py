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
    
    print(f"\n{'='*80}")
    print(f"[02.07] ANÁLISE DE REMANEJAMENTO — {TRAFO_ALVO.upper()}")
    print(f"{'='*80}")

    # Identifica o barramento MT via API
    circuit.SetActiveElement(f"Transformer.{TRAFO_ALVO}")
    bus_mt = circuit.ActiveCktElement.BusNames[0].split(".")[0].lower()
    
    print(f"  Barramento MT: {bus_mt}")
    print(f"  Avaliando troca por transformador de 45 kVA...")
    
    dss.Text.Command = f"Edit Transformer.{TRAFO_ALVO} kVA=45"
    circuit.Solution.Solve()
    if not circuit.Solution.Converged:
        raise RuntimeError(f"FALHA DE CONVERGÊNCIA: Remanejamento 45kVA")
        
    powers = circuit.ActiveCktElement.Powers
    s = (sum(powers[0:6:2])**2 + sum(powers[1:6:2])**2)**0.5
    print(f"  Novo Carregamento (45 kVA): {100 * s / 45:.2f}%")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
