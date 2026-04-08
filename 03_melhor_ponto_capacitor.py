# Crystalline Lineage
# @layer L3
# @updated 2026-04-05

"""
Identifica o barramento com maior déficit reativo noturno
onde um capacitor automático teria benefício mínimo real.
Refatorado para alta performance e estabilidade de controle.
"""

import sys
import json
from dss import dss
from fase_00 import configuracao

MASTER = configuracao.MASTER_DSS
HORAS_NOTURNAS = list(range(0, 6)) + list(range(19, 24))


def main():
    print("\n" + "=" * 80)
    print("[03.01] ANÁLISE NOTURNA DE REATIVO — MELHOR PONTO PARA CAPACITOR AUTOMÁTICO")
    print("=" * 80)

    # ---------------------------------------------------------------------------
    # PASSO 1 — Mapeamento de Q noturno/diurno por linha MT
    # ---------------------------------------------------------------------------
    circuit = configuracao.inicializar_dss(dss, MASTER)

    q_noturno = {}
    q_diurno = {}
    q_max_noc = {}
    bus2_linha = {}

    circuit.Solution.dblHour = 0.0
    for h in range(24):
        circuit.Solution.Solve()
        if not circuit.Solution.Converged:
            raise RuntimeError(f"FALHA DE CONVERGÊNCIA: Passo 1, Hora {h}")

        circuit.SetActiveClass("Line")
        idx = circuit.ActiveClass.First
        while idx > 0:
            lines = circuit.ActiveCktElement
            if not dss.ActiveCircuit.ActiveCktElement.Properties(
                "Switch"
            ).Val.lower() == "true" and not lines.Name.lower().startswith(
                "line.resist"
            ):
                nome = lines.Name
                b1 = lines.BusNames[0].split(".")[0]
                b2 = lines.BusNames[1].split(".")[0]

                circuit.SetActiveBus(b1)
                if circuit.ActiveBus.kVBase > 1.0:  # Apenas MT
                    powers = lines.Powers
                    n = lines.NumPhases
                    if len(powers) >= n * 2:
                        q = abs(sum(powers[1 : n * 2 + 1 : 2]))
                        if nome not in q_noturno:
                            q_noturno[nome] = 0.0
                            q_diurno[nome] = 0.0
                            q_max_noc[nome] = 0.0
                            bus2_linha[nome] = b2
                        if h in HORAS_NOTURNAS:
                            q_noturno[nome] += q / len(HORAS_NOTURNAS)
                            q_max_noc[nome] = max(q_max_noc[nome], q)
                        else:
                            q_diurno[nome] += q / (24 - len(HORAS_NOTURNAS))
            idx = circuit.ActiveClass.Next

    top15 = sorted(q_noturno.items(), key=lambda x: x[1], reverse=True)[:15]
    if not top15:
        print("ERRO: Nenhuma linha MT encontrada para análise.")
        return

    melhor_nome = top15[0][0]
    melhor_bus = bus2_linha[melhor_nome]
    melhor_q_max = q_max_noc[melhor_nome]

    # Dimensionamento estável (Histerese ampliada p/ evitar hunting)
    cap_kvar = max(50, int(melhor_q_max * 0.4 / 50) * 50)
    cap_kvar = min(cap_kvar, 600)
    onsetting = int(melhor_q_max * 0.85)  # Liga apenas com 85% do pico
    offsetting = int(melhor_q_max * 0.10)  # Desliga com 10%

    print(f"MELHOR CANDIDATO: barramento {melhor_bus} via {melhor_nome}")
    print(f"  Q noturno maximo: {melhor_q_max:.1f} kvar")
    print(f"  Capacitor sugerido: {cap_kvar} kvar (Automatico)")

    # --- ATUALIZAÇÃO DO JSON ---
    config_data = configuracao.config
    config_data["capacitor_alvo"] = {
        "barramento": melhor_bus,
        "linha_referencia": melhor_nome,
        "kvar_calculado": cap_kvar,
        "onsetting_sugerido": onsetting,
        "offsetting_sugerido": offsetting,
    }
    with open(configuracao.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)

    # ---------------------------------------------------------------------------
    # PASSO 2 — Referência e Teste (Estável)
    # ---------------------------------------------------------------------------
    # Roda sem capacitor
    configuracao.inicializar_dss(dss, MASTER)
    perdas_ref = []
    circuit.Solution.dblHour = 0.0
    for h in range(24):
        circuit.Solution.Solve()
        perdas_ref.append(circuit.Losses[0] / 1000.0)

    # Roda com capacitor estável
    configuracao.inicializar_dss(dss, MASTER)
    dss.Text.Command = "Set maxcontroliter=1000"
    dss.Text.Command = "Set ControlMode=Static"
    dss.Text.Command = (
        f"New Capacitor.CAPX bus1={melhor_bus} phases=3 kvar={cap_kvar} kv=23.1"
    )
    # Delay e DelayOff são os nomes exatos desse dss-python
    dss.Text.Command = f"New CapControl.CCX element={melhor_nome} terminal=1 capacitor=CAPX type=kvar onsetting={onsetting} offsetting={offsetting} Delay=30 DelayOff=30"

    delta_total = 0.0
    print(f"\nTeste de Redução de Perdas (Diário):")
    circuit.Solution.dblHour = 0.0
    for h in range(24):
        circuit.Solution.Solve()
        if not circuit.Solution.Converged:
            print(f"Erro: O fluxo de carga não convergiu na hora {h}.")
            sys.exit(1)

        perdas_com = circuit.Losses[0] / 1000.0
        delta = perdas_ref[h] - perdas_com
        delta_total += delta

    print(f"  Economia de energia estimada: {delta_total * 365 / 1000:.2f} MWh/ano")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
