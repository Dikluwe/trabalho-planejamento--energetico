# analisar_trafo.py
# Extrai todas as cargas conectadas ao trf_6_4910a e barramentos downstream

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dss import dss

import json
config_file = HERE / "parametros.json"
with open(config_file, "r") as f:
    config = json.load(f)

MASTER = str(HERE / config["caminhos"]["dss_file"])
TRAFO_ALVO = config["graficos"]["trafo_critico"]
# Deriva o bus a partir do nome "trf_6_4910a" => "et6_4910" (heurística do projeto)
BUS_SECUNDARIO = "et" + TRAFO_ALVO.split("trf_")[1].split("a")[0]
BUS_SECUNDARIO = "et" + TRAFO_ALVO.split("trf_")[1].split("a")[0]
if "trf_6_4910a" in TRAFO_ALVO:
    BUS_SECUNDARIO = "et6_4910"


# ---------------------------------------------------------------------------
# 1. Carrega a rede
# ---------------------------------------------------------------------------
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'

circuit = dss.ActiveCircuit

print(f"\n{'='*60}")
print(f"[02.01] ANÁLISE DO TRANSFORMADOR: {TRAFO_ALVO.upper()}")
print(f"{'='*60}")

# ---------------------------------------------------------------------------
# 2. Dados do transformador
# ---------------------------------------------------------------------------
circuit.Transformers.Name = TRAFO_ALVO
kva_nominal = circuit.Transformers.kVA
circuit.SetActiveElement(f"Transformer.{TRAFO_ALVO}")
bus_prim = circuit.ActiveCktElement.BusNames[0].split(".")[0].lower()
bus_sec  = circuit.ActiveCktElement.BusNames[1].split(".")[0].lower()

print(f"\nPotência nominal : {kva_nominal} kVA")
print(f"Barramento MT    : {bus_prim}")
print(f"Barramento BT    : {bus_sec}")

# ---------------------------------------------------------------------------
# 3. Monta grafo de adjacência da rede (apenas linhas, sem switches)
# ---------------------------------------------------------------------------
adj = {}  # {bus: [bus_vizinho, ...]}

circuit.SetActiveClass("Line")
lines = circuit.Lines
idx = lines.First
while idx > 0:
    if not lines.IsSwitch:
        b1 = lines.Bus1.split(".")[0].lower()
        b2 = lines.Bus2.split(".")[0].lower()
        adj.setdefault(b1, []).append(b2)
        adj.setdefault(b2, []).append(b1)
    idx = lines.Next

# ---------------------------------------------------------------------------
# 4. BFS a partir do barramento secundário para encontrar todos os nós
#    downstream (até encontrar outro transformador)
# ---------------------------------------------------------------------------
# Conjunto de barramentos primários de transformadores (são "paredes" do BFS)
bus_prim_trafos = set()
trafo_names = list(circuit.Transformers.AllNames)
for tn in trafo_names:
    circuit.Transformers.Name = tn
    circuit.SetActiveElement(f"Transformer.{tn}")
    bp = circuit.ActiveCktElement.BusNames[0].split(".")[0].lower()
    bus_prim_trafos.add(bp)

# BFS
visitados = set()
fila = [bus_sec]
visitados.add(bus_sec)

while fila:
    atual = fila.pop(0)
    for viz in adj.get(atual, []):
        if viz not in visitados and viz not in bus_prim_trafos:
            visitados.add(viz)
            fila.append(viz)

print(f"\nBarramentos alimentados por este trafo: {len(visitados)}")

# ---------------------------------------------------------------------------
# 5. Cargas conectadas a esses barramentos
# ---------------------------------------------------------------------------
circuit.SetActiveClass("Load")
loads = circuit.Loads

cargas = []
idx = loads.First
while idx > 0:
    bus_carga = circuit.ActiveCktElement.BusNames[0].split(".")[0].lower()
    if bus_carga in visitados:
        cargas.append({
            "nome": loads.Name,
            "bus": bus_carga,
            "kW": loads.kW,
            "kvar": loads.kvar,
            "kVA": (loads.kW**2 + loads.kvar**2)**0.5,
            "fases": loads.Phases,
        })
    idx = loads.Next

total_kw   = sum(c["kW"]  for c in cargas)
total_kvar = sum(c["kvar"] for c in cargas)
total_kva  = (total_kw**2 + total_kvar**2)**0.5

print(f"Número de cargas : {len(cargas)}")
print(f"\nCarga total instalada:")
print(f"  P total  : {total_kw:.2f} kW")
print(f"  Q total  : {total_kvar:.2f} kvar")
print(f"  S total  : {total_kva:.2f} kVA")
print(f"  Trafo    : {kva_nominal:.0f} kVA")
print(f"  Carregamento nominal: {100*total_kva/kva_nominal:.1f}%")

print(f"\nDetalhamento das cargas:")
print(f"  {'Nome':<30} {'Bus':<15} {'kW':>8} {'kvar':>8} {'kVA':>8} {'Fases':>6}")
print(f"  {'-'*75}")
for c in sorted(cargas, key=lambda x: x["kVA"], reverse=True):
    print(f"  {c['nome']:<30} {c['bus']:<15} {c['kW']:>8.2f} {c['kvar']:>8.2f} {c['kVA']:>8.2f} {c['fases']:>6}")

# ---------------------------------------------------------------------------
# 6. Geração distribuída nos mesmos barramentos
# ---------------------------------------------------------------------------
circuit.SetActiveClass("PVSystem")
pvs_list = list(circuit.ActiveClass.AllNames)

gd = []
for pv_name in pvs_list:
    circuit.SetActiveElement(f"PVSystem.{pv_name}")
    bus_pv = circuit.ActiveCktElement.BusNames[0].split(".")[0].lower()
    if bus_pv in visitados:
        # kW instalado via propriedade Pmpp
        circuit.SetActiveClass("PVSystem")
        # Lê potência via elemento ativo
        powers = circuit.ActiveCktElement.Powers
        n_fases = circuit.ActiveCktElement.NumPhases
        p_kw = abs(sum(powers[0:n_fases*2:2]))
        gd.append({"nome": pv_name, "bus": bus_pv, "kW_inst": p_kw})

if gd:
    print(f"\nGeração distribuída neste ramal:")
    for g in gd:
        print(f"  {g['nome']:<30} {g['bus']:<15} {g['kW_inst']:>8.2f} kW")
    print(f"  Total GD: {sum(g['kW_inst'] for g in gd):.2f} kW")
else:
    print(f"\nNenhuma GD conectada a este ramal.")

print(f"\n{'='*60}\n")
