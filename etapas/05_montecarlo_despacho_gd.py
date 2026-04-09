# 05_montecarlo_despacho_gd.py
# 1. Monte Carlo — distribuição do ano de sobrecarga do trf_6_4910a
# 2. Despacho ótimo da GD — FP variável vs FP fixo 0,92

import sys
import random
import multiprocessing
from pathlib import Path
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

# 1. Ajuste do PATH absoluto (Sempre no topo)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 2. Imports locais e de bibliotecas dependentes
from dss import dss
from core import configuracao

# 3. Parâmetros centralizados
config = configuracao.config
DEGRADACAO_GD = config["simulacao"]["degradacao_gd"]
N_SIMULACOES = 100
SEED = 42
TRAFO_KVA = 30  # kVA nominal do trf_6_4910a

CENARIOS_FP = [
    ("A — FP 0,92 (atual)", 0.92),
    ("B — FP 1,00 (só ativo)", 1.00),
    ("C — FP 0,95 capacitivo", 0.95),
    ("D — FP 0,90 capacitivo", 0.90),
]


def trafo_pct_max(circuit, nome, kva, n_horas=24):
    """Carregamento máximo em n_horas horas."""
    circuit.Solution.dblHour = 0.0
    pmax = 0.0
    for _ in range(n_horas):
        circuit.Solution.Solve()
        circuit.SetActiveElement(f"Transformer.{nome}")
        pw = circuit.ActiveCktElement.Powers
        n = circuit.ActiveCktElement.NumPhases
        if len(pw) >= n * 2:
            p = sum(pw[0 : n * 2 : 2])
            q = sum(pw[1 : n * 2 + 1 : 2])
            pmax = max(pmax, 100 * (p**2 + q**2) ** 0.5 / kva)
    return pmax


def _worker_mc_sim(args: tuple) -> int | None:
    """
    Worker do Monte Carlo: simula um cenário de taxa de crescimento fixa.
    Cada processo cria seu próprio motor DSS via configuracao.carregar.
    Retorna o primeiro ano de sobrecarga ou None se não sobrecarregar até o ano 15.
    """
    taxa, master_dss, trafo_nome, trafo_kva, degradacao_gd = args
    circuit = configuracao.carregar(dss, 1.0, master=master_dss)

    for ano in range(1, 16):
        mult = 1.0 + (ano - 1) * taxa
        gd_fat = max(0.5, 1.0 - (ano - 1) * degradacao_gd)
        dss.Text.Command = f"Set LoadMult={mult}"
        idx = circuit.PVSystems.First
        while idx > 0:
            circuit.PVSystems.Irradiance = gd_fat
            idx = circuit.PVSystems.Next
        pct = trafo_pct_max(circuit, trafo_nome, trafo_kva)
        if pct > 100:
            return ano
    return None


def _worker_fp_scenario(args: tuple) -> tuple:
    """
    Worker de despacho FP: simula uma estratégia de fator de potência.
    Cada processo cria seu próprio motor DSS via configuracao.carregar.
    Retorna (label, dict com métricas).
    """
    label, pf, master_dss = args
    circuit = configuracao.carregar(dss, 1.0, master=master_dss)
    all_bus = list(circuit.AllBusNames)

    idx = circuit.PVSystems.First
    while idx > 0:
        circuit.PVSystems.PF = pf
        idx = circuit.PVSystems.Next

    perdas_dia = 0.0
    vmin_bt = 999.0
    vmax_bt = 0.0
    q_inj_dia = 0.0

    circuit.Solution.dblHour = 0.0
    for _ in range(24):
        circuit.Solution.Solve()
        perdas_dia += circuit.Losses[0] / 1000.0

        idx2 = circuit.PVSystems.First
        while idx2 > 0:
            circuit.SetActiveElement(f"PVSystem.{circuit.PVSystems.Name}")
            pw = circuit.ActiveCktElement.Powers
            n = circuit.ActiveCktElement.NumPhases
            if len(pw) >= n * 2:
                q_inj_dia += abs(sum(pw[1 : n * 2 + 1 : 2]))
            idx2 = circuit.PVSystems.Next

        for bname in all_bus:
            circuit.SetActiveBus(bname)
            kv = circuit.ActiveBus.kVBase
            if 0.05 < kv <= 1.0:
                vmag = circuit.ActiveBus.VMagAngle
                if len(vmag) >= 1:
                    nn = circuit.ActiveBus.NumNodes
                    vb = kv * 1000 if nn < 3 else kv * 1000 / 3**0.5
                    vpu = vmag[0] / vb
                    if 0.01 < vpu:
                        vmin_bt = min(vmin_bt, vpu)
                        vmax_bt = max(vmax_bt, vpu)

    return label, {
        "perdas": perdas_dia,
        "vmin": vmin_bt if vmin_bt < 999 else 0,
        "vmax": vmax_bt,
        "q_inj": q_inj_dia,
    }


def main():
    # ===========================================================================
    # 1. MONTE CARLO — ANO DE SOBRECARGA DO trf_6_4910a
    # ===========================================================================
    print("\n" + "=" * 70)
    print("[05.01] MONTE CARLO — ANO DE SOBRECARGA DO trf_6_4910a")
    print("=" * 70)
    print(f"\n  Parâmetros:")
    print(f"  Simulações : {N_SIMULACOES}")
    print(f"  Crescimento: uniforme entre 5% e 15%/ano")
    print(f"  Degradação GD: {DEGRADACAO_GD * 100:.1f}%/ano (fixo)")
    print(f"  Limite de sobrecarga: 100%")
    print(f"  Horizonte máximo: 15 anos")

    # Pré-gera todas as taxas com a mesma semente para garantir reprodutibilidade
    random.seed(SEED)
    taxas = [random.uniform(0.05, 0.15) for _ in range(N_SIMULACOES)]

    trafo_nome = configuracao.TRAFO_CRITICO
    worker_args = [
        (taxa, configuracao.MASTER_DSS, trafo_nome, TRAFO_KVA, DEGRADACAO_GD)
        for taxa in taxas
    ]

    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(mp_context=ctx) as executor:
        resultados_mc = list(executor.map(_worker_mc_sim, worker_args))

    ano_sobrecarga = [r for r in resultados_mc if r is not None]
    nunca_sobrecarrega = sum(1 for r in resultados_mc if r is None)
    contagem = Counter(ano_sobrecarga)
    total_com_sob = len(ano_sobrecarga)

    print(f"\n  Resultados ({N_SIMULACOES} simulações):")
    print(
        f"  Simulações com sobrecarga até Ano 15: {total_com_sob} ({100 * total_com_sob / N_SIMULACOES:.0f}%)"
    )
    print(
        f"  Simulações sem sobrecarga até Ano 15: {nunca_sobrecarrega} ({100 * nunca_sobrecarrega / N_SIMULACOES:.0f}%)"
    )

    print(f"\n  Distribuição do ano de sobrecarga:")
    print(f"  {'Ano':>5} {'Ocorrências':>13} {'% simulações':>14} {'% acumulado':>13}")
    print(f"  {'-' * 48}")
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
        print(
            f"  há {100 * total_com_sob / N_SIMULACOES:.0f}% de probabilidade de sobrecarga até o Ano 15."
        )
        print(f"  Em 50% dos cenários a sobrecarga ocorre até o Ano {p50}.")
        print(f"  A intervenção (tap) é recomendada independente da taxa de crescimento.")

    # ===========================================================================
    # 2. DESPACHO ÓTIMO DA GD — FP VARIÁVEL vs FP FIXO 0,92
    # ===========================================================================
    print(f"\n{'=' * 70}")
    print("[05.02] DESPACHO ÓTIMO DA GD — FATOR DE POTÊNCIA VARIÁVEL")
    print("=" * 70)

    print(f"\n  Comparação de estratégias de FP nos PVSystems (Ano 1, LoadMult=1.0):")
    print(f"  A. FP fixo 0,92 (configuração atual)")
    print(f"  B. FP unitário (1,0) — sem injeção de reativo")
    print(f"  C. FP 0,95 capacitivo — injeção reduzida de reativo")
    print(f"  D. FP 0,90 capacitivo — injeção máxima de reativo")

    fp_args = [(label, pf, configuracao.MASTER_DSS) for label, pf in CENARIOS_FP]

    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=len(CENARIOS_FP), mp_context=ctx) as executor:
        futures = [executor.submit(_worker_fp_scenario, args) for args in fp_args]
        resultados_fp = dict(f.result() for f in futures)

    print(
        f"\n  {'Estratégia':<26} {'Perdas kWh':>11} {'Vmin BT':>9} {'Vmax BT':>9} {'Q GD kvarh':>11}"
    )
    print(f"  {'-' * 70}")
    ref_perdas = resultados_fp["A — FP 0,92 (atual)"]["perdas"]
    for label, _ in CENARIOS_FP:
        r = resultados_fp[label]
        delta = r["perdas"] - ref_perdas
        delta_str = f"({delta:+.1f})" if label != "A — FP 0,92 (atual)" else ""
        print(
            f"  {label:<26} {r['perdas']:>8.1f} {delta_str:<5} "
            f"{r['vmin']:>9.4f} {r['vmax']:>9.4f} {r['q_inj']:>11.1f}"
        )

    melhor = min(resultados_fp.items(), key=lambda x: x[1]["perdas"])
    print(f"\n  Menor perda: {melhor[0]} ({melhor[1]['perdas']:.1f} kWh/dia)")
    print(f"\n  Interpretação:")
    print(f"  FP unitário elimina injeção de reativo e pode reduzir perdas")
    print(f"  se a rede já está supercompensada (FP > 0,95 globalmente).")
    print(f"  FP < 0,92 injeta mais reativo, útil apenas se houver déficit local.")
    print(f"  Resultado define se o controle de Q dos inversores é benéfico")
    print(f"  para esta rede sem custo adicional de equipamento.")
    print("=" * 70)


if __name__ == "__main__":
    main()
