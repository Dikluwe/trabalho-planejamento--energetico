# remanejamento_longo_prazo.py
# 1. Identifica todos os trafos que entram em sobrecarga no horizonte de 15 anos
# 2. Para cada um, encontra o melhor candidato para remanejamento
# 3. Calcula VPL em 3, 10 e 15 anos

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dss import dss

MASTER = str(HERE / "Master.dss")

DEGRADACAO_GD  = 0.007   # 0,7%/ano
CRESCIMENTO_CARGA = 0.10 # 10%/ano
TAXA_DESCONTO  = 0.14
TARIFA_VENDA   = 150.0   # USD/MWh
CUSTO_PERDAS   = 35.0    # USD/MWh
TUSD           = 90.0    # USD/MWh (compensação PRODIST)
CUSTO_REMANE   = 4000.0  # USD estimado (mão de obra + transporte zona rural)
VIDA_UTIL      = 15      # anos

def carregar(loadmult=1.0, gd_fator=1.0):
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{MASTER}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    dss.Text.Command = f"Set LoadMult={loadmult}"
    circuit = dss.ActiveCircuit
    if gd_fator != 1.0:
        circuit.SetActiveClass("PVSystem")
        idx = circuit.ActiveClass.First
        while idx > 0:
            nome = circuit.ActiveCktElement.Name.split(".")[1]
            dss.Text.Command = f"Edit PVSystem.{nome} irradiance={gd_fator:.4f}"
            idx = circuit.ActiveClass.Next
    return circuit

def trafo_loading_max(circuit, nome, kva):
    """Retorna carregamento máximo em 24h."""
    pmax = 0.0
    for h in range(24):
        circuit.Solution.Solve()
        circuit.SetActiveElement(f"Transformer.{nome}")
        powers = circuit.ActiveCktElement.Powers
        n = circuit.ActiveCktElement.NumPhases
        if len(powers) >= n * 2 and kva > 0:
            p = sum(powers[0:n*2:2])
            q = sum(powers[1:n*2+1:2])
            s = (p**2 + q**2)**0.5
            pmax = max(pmax, 100 * s / kva)
    return pmax

# ---------------------------------------------------------------------------
# PASSO 1 — Lê kVA e barramento de todos os trafos
# ---------------------------------------------------------------------------
circuit = carregar(1.0)
kva_trafo = {}
bus_trafo  = {}  # barramento MT do primário

circuit.SetActiveClass("Transformer")
idx = circuit.Transformers.First
while idx > 0:
    nome = circuit.Transformers.Name
    kva_trafo[nome] = circuit.Transformers.kVA
    circuit.SetActiveElement(f"Transformer.{nome}")
    buses = list(circuit.ActiveCktElement.BusNames)
    bus_trafo[nome] = buses[0].split(".")[0] if buses else ""
    idx = circuit.Transformers.Next

# ---------------------------------------------------------------------------
# PASSO 2 — Simula 15 anos e identifica quando cada trafo ultrapassa 80%
# ---------------------------------------------------------------------------
print("\n" + "="*70)
print("HORIZONTE DE 15 ANOS — CARREGAMENTO DOS TRANSFORMADORES")
print("="*70)
print(f"  Crescimento de carga: {CRESCIMENTO_CARGA*100:.0f}%/ano")
print(f"  Degradação GD      : {DEGRADACAO_GD*100:.1f}%/ano")

# Simula ano a ano até 15
trafo_ano_sobrecarga = {}  # {nome: primeiro_ano_>100%}
trafo_ano_alerta     = {}  # {nome: primeiro_ano_>80%}
trafo_carga_por_ano  = {}  # {nome: {ano: pct_max}}

print(f"\n  Trafos que ultrapassam 80% em algum ano (1-15):")
print(f"  {'Trafo':<25} {'kVA':>5}", end="")
for ano in range(1, 16):
    print(f" {ano:>4}", end="")
print()
print(f"  {'-'*100}")

for ano in range(1, 16):
    mult  = 1.0 + (ano - 1) * CRESCIMENTO_CARGA
    gd_f  = max(0.0, 1.0 - (ano - 1) * DEGRADACAO_GD)
    # Limita mult a valores razoáveis (rede colapsa acima de certo ponto)
    if mult > 3.0:
        break
    circuit = carregar(mult, gd_f)
    circuit.SetActiveClass("Transformer")
    idx = circuit.Transformers.First
    while idx > 0:
        nome = circuit.Transformers.Name
        kva  = kva_trafo.get(nome, circuit.Transformers.kVA)
        if kva > 0:
            circuit.SetActiveElement(f"Transformer.{nome}")
            # Lê apenas hora de pico (hora 12 aprox) para ser mais rápido
            # Roda 12 horas e pega o máximo
            pmax = 0.0
            for h in range(24):
                circuit.Solution.Solve()
                powers = circuit.ActiveCktElement.Powers
                n = circuit.ActiveCktElement.NumPhases
                if len(powers) >= n * 2:
                    p = sum(powers[0:n*2:2])
                    q = sum(powers[1:n*2+1:2])
                    s = (p**2 + q**2)**0.5
                    pmax = max(pmax, 100 * s / kva)
            if nome not in trafo_carga_por_ano:
                trafo_carga_por_ano[nome] = {}
            trafo_carga_por_ano[nome][ano] = pmax

            if pmax > 80 and nome not in trafo_ano_alerta:
                trafo_ano_alerta[nome] = ano
            if pmax > 100 and nome not in trafo_ano_sobrecarga:
                trafo_ano_sobrecarga[nome] = ano
        idx = circuit.Transformers.Next

# Filtra trafos com problema
trafos_problema = sorted(trafo_ano_alerta.keys(),
                         key=lambda x: trafo_ano_alerta[x])

for nome in trafos_problema:
    kva = kva_trafo.get(nome, 0)
    print(f"  {nome:<25} {kva:>5.0f}", end="")
    for ano in range(1, 16):
        pct = trafo_carga_por_ano.get(nome, {}).get(ano, 0)
        if pct > 100:
            tag = f"{'!':>4}"
        elif pct > 80:
            tag = f"{'*':>4}"
        elif pct > 0:
            tag = f"{pct:>4.0f}"
        else:
            tag = f"{'--':>4}"
        print(tag, end="")
    sob = trafo_ano_sobrecarga.get(nome, "-")
    print(f"   → sobrecarga Ano {sob}")

print(f"\n  Legenda: número=% carregamento  *=>80%  !=sobrecarga(>100%)")
print(f"  Total trafos com alerta em 15 anos: {len(trafos_problema)}")

# ---------------------------------------------------------------------------
# PASSO 3 — Candidatos para remanejamento
# ---------------------------------------------------------------------------
print(f"\n{'='*70}")
print("CANDIDATOS PARA REMANEJAMENTO (baixo carregamento em todo horizonte)")
print("="*70)

# Trafos com carregamento máximo < 30% em todos os anos simulados
candidatos = []
for nome, anos in trafo_carga_por_ano.items():
    pmax_total = max(anos.values()) if anos else 0
    if pmax_total < 30 and kva_trafo.get(nome, 0) >= 30:
        candidatos.append((nome, kva_trafo[nome], pmax_total))

candidatos.sort(key=lambda x: x[2])

print(f"\n  {'Trafo':<25} {'kVA':>6} {'Carga máx 15a':>14} {'Barramento MT':>15}")
print(f"  {'-'*65}")
for nome, kva, pmax in candidatos[:20]:
    bus = bus_trafo.get(nome, "?")
    print(f"  {nome:<25} {kva:>6.0f} {pmax:>14.1f}% {bus:>15}")

# ---------------------------------------------------------------------------
# PASSO 4 — VPL do remanejamento em 3, 10 e 15 anos
# ---------------------------------------------------------------------------
print(f"\n{'='*70}")
print("VPL DO REMANEJAMENTO — trf_6_4910a substituído por trafo maior")
print("="*70)
print(f"\n  Custo estimado remanejamento: USD {CUSTO_REMANE:,.0f}")
print(f"  (inclui desmontagem, transporte e instalação em zona rural)")

# Estima benefício anual do remanejamento
# Benefício = evitar penalidade de sobrecarga + redução de perdas no trafo
# Aproximação: trafo sobrecarregado tem perdas adicionais estimadas
# e risco de falha com custo de substituição emergencial (USD 8.000–12.000)

# Usa os dados já calculados: sem remanejamento trf_6_4910a sobrecarga no Ano 3+
# Com remanejamento (45 kVA): carregamento cai ~33%, dentro do limite
# Benefício principal: evitar a substituição de emergência

CUSTO_EMERGENCIA  = 10000.0  # USD (substituição não planejada)
PROB_FALHA_ANO    = 0.15     # probabilidade de falha por ano em sobrecarga crônica
BENEFICIO_ANUAL_BASE = 200.0 # USD/ano — redução de perdas no trafo (estimativa)

print(f"\n  Premissas de risco:")
print(f"    Custo substituição emergencial  : USD {CUSTO_EMERGENCIA:,.0f}")
print(f"    Probabilidade de falha/ano      : {PROB_FALHA_ANO*100:.0f}% (sobrecarga crônica)")
print(f"    Valor esperado do risco/ano     : USD {CUSTO_EMERGENCIA*PROB_FALHA_ANO:,.0f}")
print(f"    Redução de perdas/ano (estimada): USD {BENEFICIO_ANUAL_BASE:,.0f}")

beneficio_sem_risco = BENEFICIO_ANUAL_BASE
beneficio_com_risco = BENEFICIO_ANUAL_BASE + CUSTO_EMERGENCIA * PROB_FALHA_ANO

print(f"\n  {'Horizonte':>12} {'VPL s/risco':>14} {'VPL c/risco':>14} {'Atrativo c/risco':>18}")
print(f"  {'-'*62}")

for horizonte in [3, 5, 10, 15]:
    # Anos com sobrecarga: a partir do Ano 3
    anos_sobrecarga = max(0, horizonte - 2)

    # VPL sem considerar risco de falha
    fluxos_sr = [-CUSTO_REMANE]
    for ano in range(1, horizonte + 1):
        ben = beneficio_sem_risco if ano >= 3 else 0
        if ano == horizonte:
            residual = CUSTO_REMANE * (VIDA_UTIL - horizonte) / VIDA_UTIL
            ben += residual
        fluxos_sr.append(ben)
    vpl_sr = sum(f / (1 + TAXA_DESCONTO)**t for t, f in enumerate(fluxos_sr))

    # VPL com risco de falha (benefício começa no Ano 3)
    fluxos_cr = [-CUSTO_REMANE]
    for ano in range(1, horizonte + 1):
        ben = beneficio_com_risco if ano >= 3 else 0
        if ano == horizonte:
            residual = CUSTO_REMANE * (VIDA_UTIL - horizonte) / VIDA_UTIL
            ben += residual
        fluxos_cr.append(ben)
    vpl_cr = sum(f / (1 + TAXA_DESCONTO)**t for t, f in enumerate(fluxos_cr))

    atrativo = "SIM" if vpl_cr > 0 else "NÃO"
    print(f"  {horizonte:>10} a {vpl_sr:>14,.0f} {vpl_cr:>14,.0f} {atrativo:>18}")

print(f"\n  Nota: VPL s/risco considera só redução de perdas.")
print(f"  VPL c/risco inclui valor esperado do risco de falha por sobrecarga.")
print("="*70)
