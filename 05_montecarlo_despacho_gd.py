# 05_montecarlo_despacho_gd.py
# 1. Monte Carlo — distribuição do ano de sobrecarga do trf_6_4910a
# 2. Despacho ótimo da GD — FP variável vs FP fixo 0,92

import sys
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dss import dss

import json
with open(HERE / "parametros.json", "r") as f:
    config = json.load(f)

MASTER = str(HERE / config["caminhos"]["dss_file"])
DEGRADACAO_GD = config["simulacao"]["degradacao_gd"]
N_SIMULACOES  = 100
SEED          = 42

def carregar(loadmult=1.0, cmds=None):
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{MASTER}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    dss.Text.Command = f"Set LoadMult={loadmult}"
    if cmds:
        for c in cmds: dss.Text.Command = c
    return dss.ActiveCircuit

def trafo_pct_max(circuit, nome, kva, n_horas=24):
    """Carregamento máximo em n_horas horas."""
    pmax = 0.0
    for _ in range(n_horas):
        circuit.Solution.Solve()
        circuit.SetActiveElement(f"Transformer.{nome}")
        pw = circuit.ActiveCktElement.Powers
        n  = circuit.ActiveCktElement.NumPhases
        if len(pw) >= n*2:
            p = sum(pw[0:n*2:2]); q = sum(pw[1:n*2+1:2])
            pmax = max(pmax, 100*(p**2+q**2)**0.5/kva)
    return pmax

# ===========================================================================
# 1. MONTE CARLO — ANO DE SOBRECARGA DO trf_6_4910a
# ===========================================================================
print("\n" + "="*70)
print("[05.01] MONTE CARLO — ANO DE SOBRECARGA DO trf_6_4910a")
print("="*70)
print(f"\n  Parâmetros:")
print(f"  Simulações : {N_SIMULACOES}")
print(f"  Crescimento: uniforme entre 5% e 15%/ano")
print(f"  Degradação GD: {DEGRADACAO_GD*100:.1f}%/ano (fixo)")
print(f"  Limite de sobrecarga: 100%")
print(f"  Horizonte máximo: 15 anos")

random.seed(SEED)

ano_sobrecarga = []  # ano em que cada simulação ultrapassa 100%
nunca_sobrecarrega = 0

for sim in range(N_SIMULACOES):
    # Crescimento uniforme entre 5% e 15% ao ano
    taxa = random.uniform(0.05, 0.15)
    ano_sob = None

    for ano in range(1, 16):
        mult    = 1.0 + (ano - 1) * taxa
        gd_fat  = max(0.5, 1.0 - (ano - 1) * DEGRADACAO_GD)

        circuit = carregar(mult)
        circuit.PVSystems.First
        idx = circuit.PVSystems.First
        while idx > 0:
            circuit.PVSystems.Irradiance = gd_fat
            idx = circuit.PVSystems.Next

        pct = trafo_pct_max(circuit, "trf_6_4910a", 30)
        if pct > 100:
            ano_sob = ano
            break

    if ano_sob:
        ano_sobrecarga.append(ano_sob)
    else:
        nunca_sobrecarrega += 1

# Estatísticas
from collections import Counter
contagem = Counter(ano_sobrecarga)
total_com_sob = len(ano_sobrecarga)

print(f"\n  Resultados ({N_SIMULACOES} simulações):")
print(f"  Simulações com sobrecarga até Ano 15: {total_com_sob} ({100*total_com_sob/N_SIMULACOES:.0f}%)")
print(f"  Simulações sem sobrecarga até Ano 15: {nunca_sobrecarrega} ({100*nunca_sobrecarrega/N_SIMULACOES:.0f}%)")

print(f"\n  Distribuição do ano de sobrecarga:")
print(f"  {'Ano':>5} {'Ocorrências':>13} {'% simulações':>14} {'% acumulado':>13}")
print(f"  {'-'*48}")
acum = 0
for ano in range(1, 16):
    cnt = contagem.get(ano, 0)
    acum += cnt
    pct_sim = 100 * cnt / N_SIMULACOES
    pct_acum = 100 * acum / N_SIMULACOES
    if cnt > 0:
        bar = "█" * int(pct_sim / 2)
        print(f"  {ano:>5} {cnt:>13} {pct_sim:>13.1f}% {pct_acum:>12.1f}%  {bar}")

if ano_sobrecarga:
    anos_ord = sorted(ano_sobrecarga)
    p10 = anos_ord[int(0.10 * len(anos_ord))]
    p50 = anos_ord[int(0.50 * len(anos_ord))]
    p90 = anos_ord[int(0.90 * len(anos_ord))]
    print(f"\n  Percentis do ano de sobrecarga:")
    print(f"    P10 (10% das simulações sobrecarga antes): Ano {p10}")
    print(f"    P50 (mediana)                            : Ano {p50}")
    print(f"    P90 (90% das simulações sobrecarga antes): Ano {p90}")
    print(f"\n  Interpretação:")
    print(f"  Com crescimento de carga entre 5% e 15%/ano,")
    print(f"  há {100*total_com_sob/N_SIMULACOES:.0f}% de probabilidade de sobrecarga até o Ano 15.")
    print(f"  Em 50% dos cenários a sobrecarga ocorre até o Ano {p50}.")
    print(f"  A intervenção (tap) é recomendada independente da taxa de crescimento.")

# ===========================================================================
# 2. DESPACHO ÓTIMO DA GD — FP VARIÁVEL vs FP FIXO 0,92
# ===========================================================================
print(f"\n{'='*70}")
print("[05.02] DESPACHO ÓTIMO DA GD — FATOR DE POTÊNCIA VARIÁVEL")
print("="*70)

print(f"\n  Comparação de estratégias de FP nos PVSystems (Ano 1, LoadMult=1.0):")
print(f"  A. FP fixo 0,92 (configuração atual)")
print(f"  B. FP unitário (1,0) — sem injeção de reativo")
print(f"  C. FP 0,95 capacitivo — injeção reduzida de reativo")
print(f"  D. FP 0,90 capacitivo — injeção máxima de reativo")

all_bus = None

resultados_fp = {}

for label, pf in [
    ("A — FP 0,92 (atual)",        0.92),
    ("B — FP 1,00 (só ativo)",     1.00),
    ("C — FP 0,95 capacitivo",     0.95),
    ("D — FP 0,90 capacitivo",     0.90),
]:
    circuit = carregar(1.0)

    if all_bus is None:
        all_bus = list(circuit.AllBusNames)

    # Aplica FP em todos os PVSystems
    idx = circuit.PVSystems.First
    while idx > 0:
        circuit.PVSystems.PF = pf
        idx = circuit.PVSystems.Next

    perdas_dia = 0.0
    vmin_bt    = 999.0
    vmax_bt    = 0.0
    q_inj_dia  = 0.0

    for h in range(24):
        circuit.Solution.Solve()
        perdas_dia += circuit.Losses[0] / 1000.0

        # Q injetado pela GD
        idx2 = circuit.PVSystems.First
        while idx2 > 0:
            circuit.SetActiveElement(
                f"PVSystem.{circuit.PVSystems.Name}")
            pw = circuit.ActiveCktElement.Powers
            n  = circuit.ActiveCktElement.NumPhases
            if len(pw) >= n*2:
                q_inj_dia += abs(sum(pw[1:n*2+1:2]))
            idx2 = circuit.PVSystems.Next

        for bname in all_bus:
            circuit.SetActiveBus(bname)
            kv = circuit.ActiveBus.kVBase
            if 0.05 < kv <= 1.0:
                vmag = circuit.ActiveBus.VMagAngle
                if len(vmag) >= 1:
                    nn = circuit.ActiveBus.NumNodes
                    vb = kv*1000 if nn < 3 else kv*1000/3**0.5
                    vpu = vmag[0]/vb
                    if 0.01 < vpu:
                        vmin_bt = min(vmin_bt, vpu)
                        vmax_bt = max(vmax_bt, vpu)

    resultados_fp[label] = {
        "perdas": perdas_dia,
        "vmin":   vmin_bt if vmin_bt < 999 else 0,
        "vmax":   vmax_bt,
        "q_inj":  q_inj_dia,
    }

print(f"\n  {'Estratégia':<26} {'Perdas kWh':>11} {'Vmin BT':>9} {'Vmax BT':>9} {'Q GD kvarh':>11}")
print(f"  {'-'*70}")
ref_perdas = resultados_fp["A — FP 0,92 (atual)"]["perdas"]
for label, r in resultados_fp.items():
    delta = r["perdas"] - ref_perdas
    delta_str = f"({delta:+.1f})" if label != "A — FP 0,92 (atual)" else ""
    print(f"  {label:<26} {r['perdas']:>8.1f} {delta_str:<5} "
          f"{r['vmin']:>9.4f} {r['vmax']:>9.4f} {r['q_inj']:>11.1f}")

melhor = min(resultados_fp.items(), key=lambda x: x[1]["perdas"])
print(f"\n  Menor perda: {melhor[0]} ({melhor[1]['perdas']:.1f} kWh/dia)")
print(f"\n  Interpretação:")
print(f"  FP unitário elimina injeção de reativo e pode reduzir perdas")
print(f"  se a rede já está supercompensada (FP > 0,95 globalmente).")
print(f"  FP < 0,92 injeta mais reativo, útil apenas se houver déficit local.")
print(f"  Resultado define se o controle de Q dos inversores é benéfico")
print(f"  para esta rede sem custo adicional de equipamento.")
print("="*70)
