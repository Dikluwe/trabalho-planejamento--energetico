# 06_novo_trafo_paralelo.py
# Avalia a instalação de um novo trafo em paralelo com o trf_6_4910a
# para dividir a carga do consumidor uc632607

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dss import dss

import json
with open(HERE / "parametros.json", "r") as f:
    config = json.load(f)

MASTER = str(HERE / config["caminhos"]["dss_file"])
TRAFO_ALVO = config.get("graficos", {}).get("trafo_critico", "trf_6_4910a")

TAXA_DESCONTO = config["economico"]["taxa_desconto"]
CUSTO_PERDAS  = config["economico"]["preco_compra_usd_mwh"]
TARIFA_VENDA  = config["economico"]["tarifa_venda_usd_mwh"]
TUSD          = config["economico"]["tusd_usd_mwh"]

# A vida útil base da alternativa (ex: trafo novo dura mto, mas a avaliação é 15 anos)
VIDA_UTIL     = 15
DEGRADACAO_GD = config["simulacao"]["degradacao_gd"]

# Custo de um trafo novo 30 kVA instalado em zona rural (Brasil)
# Inclui trafo, poste, ferragens, instalação
CUSTO_TRAFO_30KVA  = 6000.0
CUSTO_TRAFO_45KVA  = 7500.0

def carregar(loadmult=1.0, cmds_extras=None):
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{MASTER}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    dss.Text.Command = f"Set LoadMult={loadmult}"
    if cmds_extras:
        for cmd in cmds_extras:
            dss.Text.Command = cmd
    return dss.ActiveCircuit

def trafo_loading_max(circuit, nome, kva):
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

def perdas_dia(circuit):
    total = 0.0
    for h in range(24):
        circuit.Solution.Solve()
        total += circuit.Losses[0] / 1000.0
    return total

def vmin_bt(circuit):
    all_bus = list(circuit.AllBusNames)
    vmin = 999.0
    for h in range(24):
        circuit.Solution.Solve()
        for bname in all_bus:
            circuit.SetActiveBus(bname)
            kv = circuit.ActiveBus.kVBase
            if 0.05 < kv <= 1.0:
                vmag = circuit.ActiveBus.VMagAngle
                if len(vmag) >= 1:
                    nn = circuit.ActiveBus.NumNodes
                    vbase = kv * 1000 if nn < 3 else kv * 1000 / 3**0.5
                    vpu = vmag[0] / vbase
                    if 0.01 < vpu < vmin:
                        vmin = vpu
    return vmin if vmin < 999 else 0.0

# ---------------------------------------------------------------------------
# Inspeciona o ramal do trf_6_4910a para entender a topologia
# ---------------------------------------------------------------------------
print("\n" + "="*70)
print("[06.01] TOPOLOGIA DO RAMAL trf_6_4910a")
print("="*70)

circuit = carregar(1.0)

# Barramento secundário do trafo
circuit.SetActiveElement("Transformer.trf_6_4910a")
buses_trafo = list(circuit.ActiveCktElement.BusNames)
bus_mt = buses_trafo[0].split(".")[0]
bus_bt = buses_trafo[1].split(".")[0]
print(f"\n  Barramento MT (primário) : {bus_mt}")
print(f"  Barramento BT (secundário): {bus_bt}")

# Cargas no ramal
loads = circuit.Loads
idx = loads.First
cargas_ramal = []
while idx > 0:
    circuit.SetActiveElement(f"Load.{loads.Name}")
    bus = circuit.ActiveCktElement.BusNames[0].split(".")[0]
    if bus_bt in bus or bus in bus_bt:
        cargas_ramal.append({
            "nome": loads.Name,
            "bus":  bus,
            "kw":   loads.kW,
            "kvar": loads.kvar,
            "kv":   loads.kV,
        })
    idx = loads.Next

# Também busca cargas nas linhas downstream
circuit.SetActiveClass("Line")
lines = circuit.Lines
linhas_bt = []
idx = lines.First
while idx > 0:
    b1 = lines.Bus1.split(".")[0]
    b2 = lines.Bus2.split(".")[0]
    if b1 == bus_bt or b2 == bus_bt:
        linhas_bt.append({"nome": lines.Name, "b1": b1, "b2": b2,
                          "length": lines.Length * 1000})
    idx = lines.Next

print(f"\n  Linhas BT conectadas ao secundário:")
for l in linhas_bt:
    print(f"    Line.{l['nome']}  {l['b1']} → {l['b2']}  {l['length']:.1f}m")

print(f"\n  Cargas no barramento {bus_bt}:")
for c in cargas_ramal:
    print(f"    Load.{c['nome']}  {c['kw']:.2f} kW  {c['kvar']:.2f} kvar  {c['kv']} kV")

# Busca cargas nos barramentos das linhas BT
for linha in linhas_bt:
    bus_down = linha["b2"] if linha["b1"] == bus_bt else linha["b1"]
    loads2 = circuit.Loads
    idx2 = loads2.First
    while idx2 > 0:
        circuit.SetActiveElement(f"Load.{loads2.Name}")
        if circuit.ActiveCktElement.BusNames[0].split(".")[0] == bus_down:
            cargas_ramal.append({
                "nome": loads2.Name,
                "bus":  bus_down,
                "kw":   loads2.kW,
                "kvar": loads2.kvar,
                "kv":   loads2.kV,
            })
            print(f"    Load.{loads2.Name}  bus={bus_down}  "
                  f"{loads2.kW:.2f} kW  {loads2.kvar:.2f} kvar")
        idx2 = loads2.Next

kw_total  = sum(c["kw"]   for c in cargas_ramal)
kvar_total = sum(c["kvar"] for c in cargas_ramal)
kva_total  = (kw_total**2 + kvar_total**2)**0.5
print(f"\n  Carga total do ramal: {kw_total:.2f} kW / {kvar_total:.2f} kvar "
      f"/ {kva_total:.2f} kVA")
print(f"  Trafo atual: 30 kVA → {100*kva_total/30:.1f}% de carregamento estático")

# ---------------------------------------------------------------------------
# Modela novo trafo em paralelo
# Estratégia: divide a carga entre os dois trafos
# Trafo 1 (existente): alimenta medidor 1 (load com menor kW)
# Trafo 2 (novo 30 kVA): alimenta medidor 2 (load com maior kW)
# Ambos conectados ao mesmo barramento MT (9051 via smt_14449)
# ---------------------------------------------------------------------------
print(f"\n{'='*70}")
print("[06.02] MODELAGEM — NOVO TRAFO 30 kVA EM PARALELO")
print("="*70)

# Identifica as duas cargas (dois medidores de uc632607)
if len(cargas_ramal) >= 2:
    cargas_sorted = sorted(cargas_ramal, key=lambda x: x["kw"])
    carga_menor = cargas_sorted[0]
    carga_maior = cargas_sorted[-1]
else:
    carga_menor = cargas_ramal[0]
    carga_maior = cargas_ramal[0]

print(f"\n  Divisão proposta:")
print(f"    Trafo existente (30 kVA): Load.{carga_menor['nome']} "
      f"({carga_menor['kw']:.2f} kW)")
print(f"    Trafo novo (30 kVA)     : Load.{carga_maior['nome']} "
      f"({carga_maior['kw']:.2f} kW)")

# Novo barramento BT para o segundo trafo
novo_bus_bt = "et6_4910b"
kv_bt = 0.38  # mesma tensão do trafo existente

# Comandos DSS para instalar novo trafo e mover a carga maior
kv_mt  = 23.1
# Descobre kV do trafo existente
circuit.SetActiveElement("Transformer.trf_6_4910a")
circuit.Transformers.Name = "trf_6_4910a"
kv_sec = circuit.Transformers.kV  # tensão do winding atual

# Trafo existente é trifásico 23.1kV / 0.38kV
# Novo trafo: mesmas especificações, barramento BT separado
cmds_novo_trafo_30 = [
    f"New Transformer.TRF_6_4910b phases=3 windings=2 "
    f"buses=[{bus_mt}.1.2.3 {novo_bus_bt}.1.2.3] "
    f"conns=[wye wye] kvs=[{kv_mt:.4f} 0.38] "
    f"kvas=[30 30] xhl=2 %Rs=[0.5 0.5]",
    f"Edit Load.{carga_maior['nome']} bus1={novo_bus_bt}",
]

cmds_novo_trafo_45 = [
    f"New Transformer.TRF_6_4910b phases=3 windings=2 "
    f"buses=[{bus_mt}.1.2.3 {novo_bus_bt}.1.2.3] "
    f"conns=[wye wye] kvs=[{kv_mt:.4f} 0.38] "
    f"kvas=[45 45] xhl=2 %Rs=[0.5 0.5]",
    f"Edit Load.{carga_maior['nome']} bus1={novo_bus_bt}",
]

print(f"\n{'='*70}")
print("[06.03] COMPARAÇÃO — CASO BASE vs NOVO TRAFO 30 kVA vs NOVO TRAFO 45 kVA")
print("="*70)
print(f"\n  {'':>4} {'':>20} {'trf_4910a':>10} {'trf_4910b':>10} "
      f"{'Perdas kWh':>11} {'VminBT':>8}")
print(f"  {'-'*68}")

resultados = {}

for ano, mult, gd_f in [
    (1, 1.0, 1.0),
    (2, 1.1, 1.0 - DEGRADACAO_GD),
    (3, 1.2, 1.0 - 2*DEGRADACAO_GD),
]:
    gd_cmds = []
    if gd_f != 1.0:
        # Prepara degradação GD — aplica depois do carregar
        pass

    for label, cmds, kva_novo, custo in [
        ("base",    [],                   0,    0),
        ("novo 30", cmds_novo_trafo_30,  30, CUSTO_TRAFO_30KVA),
        ("novo 45", cmds_novo_trafo_45,  45, CUSTO_TRAFO_45KVA),
    ]:
        circuit = carregar(mult, cmds if cmds else None)
        if gd_f != 1.0:
            circuit.SetActiveClass("PVSystem")
            idx = circuit.ActiveClass.First
            while idx > 0:
                nome = circuit.ActiveCktElement.Name.split(".")[1]
                dss.Text.Command = f"Edit PVSystem.{nome} irradiance={gd_f:.4f}"
                idx = circuit.ActiveClass.Next

        # Lê os dois trafos e perdas num único loop de 24h
        pct_a = 0.0
        pct_b = 0.0
        perd  = 0.0
        vmin_val = 999.0
        all_bus = list(circuit.AllBusNames)
        for h in range(24):
            circuit.Solution.Solve()
            perd += circuit.Losses[0] / 1000.0

            circuit.SetActiveElement(f"Transformer.{TRAFO_ALVO}")
            powers = circuit.ActiveCktElement.Powers
            n = circuit.ActiveCktElement.NumPhases
            if len(powers) >= n * 2:
                p = sum(powers[0:n*2:2])
                q = sum(powers[1:n*2+1:2])
                pct_a = max(pct_a, 100*(p**2+q**2)**0.5/30)

            if label != "base":
                circuit.SetActiveElement("Transformer.trf_6_4910b")
                powers2 = circuit.ActiveCktElement.Powers
                n2 = circuit.ActiveCktElement.NumPhases
                if len(powers2) >= n2 * 2:
                    p2 = sum(powers2[0:n2*2:2])
                    q2 = sum(powers2[1:n2*2+1:2])
                    pct_b = max(pct_b, 100*(p2**2+q2**2)**0.5/kva_novo)

            for bname in all_bus:
                circuit.SetActiveBus(bname)
                kv = circuit.ActiveBus.kVBase
                if 0.05 < kv <= 1.0:
                    vmag = circuit.ActiveBus.VMagAngle
                    if len(vmag) >= 1:
                        nn = circuit.ActiveBus.NumNodes
                        vbase = kv*1000 if nn < 3 else kv*1000/3**0.5
                        vpu = vmag[0] / vbase
                        if 0.01 < vpu < vmin_val:
                            vmin_val = vpu

        vmin = vmin_val if vmin_val < 999 else 0.0

        key = (ano, label)
        resultados[key] = {
            "pct_a": pct_a, "pct_b": pct_b,
            "perdas": perd, "vmin": vmin,
            "custo": custo,
        }

        pct_b_str = f"{pct_b:.1f}" if pct_b > 0 else "—"
        print(f"  {ano:>4} {label:>20} {pct_a:>10.1f} {pct_b_str:>10} "
              f"{perd:>11.1f} {vmin:>8.4f}")
    print()

# ---------------------------------------------------------------------------
# VPL dos dois cenários
# ---------------------------------------------------------------------------
print(f"{'='*70}")
print("VPL — NOVO TRAFO EM PARALELO")
print("="*70)

for label, kva_novo, custo in [("novo 30", 30, CUSTO_TRAFO_30KVA),
                                 ("novo 45", 45, CUSTO_TRAFO_45KVA)]:
    fluxos = [-custo]
    for ano in [1, 2, 3]:
        base = resultados[(ano, "base")]
        novo = resultados[(ano, label)]
        delta_perd = (base["perdas"] - novo["perdas"]) * 365 / 1000
        ben_anual  = delta_perd * CUSTO_PERDAS
        if ano == 3:
            ben_anual += custo * (VIDA_UTIL - 3) / VIDA_UTIL
        fluxos.append(ben_anual)
    vpl = sum(f / (1 + TAXA_DESCONTO)**t for t, f in enumerate(fluxos))
    print(f"\n  Trafo novo {kva_novo} kVA:")
    print(f"    CAPEX          : USD {custo:,.0f}")
    print(f"    VPL (3 anos)   : USD {vpl:,.0f}")
    print(f"    Atrativo       : {'SIM' if vpl > 0 else 'NÃO'}")
    print(f"    Carregamento trf_4910a Ano3: "
          f"{resultados[(3, label)]['pct_a']:.1f}%  "
          f"trf_4910b: {resultados[(3, label)]['pct_b']:.1f}%")

print(f"\n{'='*70}")
print("RESUMO COMPARATIVO FINAL — TODAS AS ALTERNATIVAS")
print("="*70)
print(f"  {'Alternativa':<42} {'CAPEX':>10} {'VPL':>10} {'Atrativo':>10}")
print(f"  {'-'*74}")
tabela = [
    ("Tap trf_6_4910a + trf_11_305a",      1500,   1283, True),
    ("Novo trafo 30 kVA paralelo",          6000,
     int(sum((resultados[(ano,"novo 30")]["perdas"]-resultados[(ano,"base")]["perdas"])
             *365/1000*CUSTO_PERDAS/(1.14**ano) for ano in [1,2,3])
         + 6000*(VIDA_UTIL-3)/VIDA_UTIL/(1.14**3) - 6000), False),
    ("Novo trafo 45 kVA paralelo",          7500,   0,    False),
    ("Recondutoramento da Linha Principal",          2207,  -914,  False),
    ("Capacitor automático 1200 kvar",     12246, -8008,  False),
    ("Capacitor fixo 600 kvar",             7031,-27727,  False),
]
for nome, capex, vpl, atr in tabela:
    print(f"  {nome:<42} {capex:>10,} {vpl:>10,} {'SIM' if atr else 'NÃO':>10}")
print("="*70)
