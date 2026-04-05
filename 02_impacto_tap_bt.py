# impacto_tap_bt.py
# Quantifica o impacto do tap no perfil de tensão BT
# Compara caso base vs tap nos dois trafos — faixas PRODIST Tabela 5

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dss import dss
import json

with open(HERE / "parametros.json", "r") as f:
    config = json.load(f)

MASTER = str(HERE / config["caminhos"]["dss_file"])

# Faixas PRODIST Tabela 5 — BT 220/127V e 380/220V
# Adequada: 0,921–1,050 pu
# Precária:  0,871–0,921 pu
# Crítica:   < 0,871 ou > 1,061 pu

def classificar(vpu):
    if vpu > 1.061 or vpu < 0.871:
        return "crítica"
    elif vpu < 0.921:
        return "precária"
    else:
        return "adequada"

def carregar(loadmult=1.0, cmds=None):
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{MASTER}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    dss.Text.Command = f"Set LoadMult={loadmult}"
    if cmds:
        for c in cmds: dss.Text.Command = c
    return dss.ActiveCircuit

def perfil_bt(circuit):
    """Coleta tensão mínima diária por barramento BT."""
    all_bus = list(circuit.AllBusNames)
    v_min = {}

    for h in range(24):
        circuit.Solution.Solve()
        for nome in all_bus:
            circuit.SetActiveBus(nome)
            kv = circuit.ActiveBus.kVBase
            if 0.05 < kv <= 1.0:
                vmag = circuit.ActiveBus.VMagAngle
                if len(vmag) < 1: continue
                nn = circuit.ActiveBus.NumNodes
                vb = kv*1000  # kVBase já é tensão de fase nesta rede
                vpu = vmag[0] / vb
                if vpu < 0.01: continue
                if nome not in v_min or vpu < v_min[nome]:
                    v_min[nome] = vpu
    return v_min

def resumo_faixas(v_min):
    cont = {"adequada": 0, "precária": 0, "crítica": 0}
    for vpu in v_min.values():
        cont[classificar(vpu)] += 1
    total = sum(cont.values())
    return cont, total

CMD_TAP = [
    "Edit Transformer.TRF_6_4910A wdg=1 tap=1.0333",
    "Edit Transformer.TRF_11_305A wdg=1 tap=1.0333",
]

print("\n" + "="*70)
print("[02.04] IMPACTO DO TAP NO PERFIL DE TENSÃO BT — PRODIST TABELA 5")
print("="*70)

for ano, mult in [(ano, 1.0 + (ano-1)*config["simulacao"]["crescimento_carga"]) for ano in (1, 2, 3)]:
    print(f"\n{'─'*70}")
    print(f"ANO {ano} — LoadMult={mult}")
    print(f"{'─'*70}")

    # Caso base
    c_base = carregar(mult)
    v_base = perfil_bt(c_base)
    cont_base, total = resumo_faixas(v_base)

    # Com tap
    c_tap = carregar(mult, CMD_TAP)
    v_tap  = perfil_bt(c_tap)
    cont_tap, _ = resumo_faixas(v_tap)

    print(f"\n  {'Faixa PRODIST':<12} {'Base':>8} {'%':>6} {'C/tap':>8} {'%':>6} {'Δ':>6}")
    print(f"  {'-'*50}")
    for faixa in ["adequada", "precária", "crítica"]:
        b = cont_base[faixa]
        t = cont_tap[faixa]
        d = t - b
        d_str = f"{d:+d}" if d != 0 else "—"
        print(f"  {faixa:<12} {b:>8} {100*b/total:>5.1f}% {t:>8} {100*t/total:>5.1f}% {d_str:>6}")
    print(f"  {'Total BT':<12} {total:>8}")

    # Barramentos que mudam de faixa
    pioram = []
    melhoram = []
    for nome in v_base:
        if nome not in v_tap: continue
        f_base = classificar(v_base[nome])
        f_tap  = classificar(v_tap[nome])
        if f_tap != f_base:
            ordem = {"adequada": 0, "precária": 1, "crítica": 2}
            if ordem[f_tap] > ordem[f_base]:
                pioram.append((nome, v_base[nome], v_tap[nome], f_base, f_tap))
            else:
                melhoram.append((nome, v_base[nome], v_tap[nome], f_base, f_tap))

    if melhoram:
        print(f"\n  Barramentos que melhoram de faixa com o tap:")
        for nome, vb, vt, fb, ft in sorted(melhoram, key=lambda x: x[1]):
            print(f"    {nome:<25} {vb:.4f}→{vt:.4f} pu  {fb}→{ft}")

    if pioram:
        print(f"\n  Barramentos que pioram de faixa com o tap:")
        for nome, vb, vt, fb, ft in sorted(pioram, key=lambda x: x[1]):
            print(f"    {nome:<25} {vb:.4f}→{vt:.4f} pu  {fb}→{ft}")

    if not melhoram and not pioram:
        print(f"\n  Nenhum barramento muda de faixa PRODIST com o tap.")

    trafo = config["graficos"]["trafo_critico"]
    
    # Tensão no secundário do trafo alvo (derivado ou hardcoded caso específico)
    bus_sec = "et6_4910" if trafo == "trf_6_4910a" else f"et{trafo.split('_')[1]}"
    
    v_et6_base = v_base.get(bus_sec, v_base.get("uc632607", None))
    v_et6_tap  = v_tap.get(bus_sec,  v_tap.get("uc632607", None))

    if v_et6_base is not None and v_et6_tap is not None:
        print(f"\n  Tensão no secundário do {trafo} (consumidor):")
        print(f"    Caso base : {v_et6_base:.4f} pu  ({v_et6_base*220:.1f} V)  [{classificar(v_et6_base)}]")
        print(f"    Com tap   : {v_et6_tap:.4f} pu  ({v_et6_tap*220:.1f} V)  [{classificar(v_et6_tap)}]")
        print(f"    Variação  : {(v_et6_tap-v_et6_base)*100:+.2f}%")

print(f"\n{'='*70}")
print("CONCLUSÃO")
print("="*70)
print(f"""
  O tap nos dois trafos reduz o carregamento do trf_6_4910a mas abaixa
  a tensão no secundário desse trafo. O impacto nas faixas PRODIST
  quantifica se essa redução de tensão é aceitável regulatoriamente.

  Faixa adequada BT (PRODIST Tabela 5): 0,921–1,050 pu
  Faixa precária BT: 0,871–0,921 pu (DRC — compensação devida)
  Faixa crítica BT: < 0,871 pu (DRP — compensação maior)
""")
