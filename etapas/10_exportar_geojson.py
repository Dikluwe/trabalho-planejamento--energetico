# 10_exportar_geojson.py
# Gera GeoJSON para importar no QGIS com posicionamento automático
# Camadas separadas: linhas_mt, linhas_bt, trafos, gd, problemas

import sys
import json
from pathlib import Path
import math

# 1. Ajuste do PATH absoluto sempre no topo
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 2. Imports locais e de pacotes
from dss import dss

# 3. Uso do ROOT para acessar os arquivos na raiz do projeto
with open(ROOT / "parametros.json", "r", encoding="utf-8") as f:
    config = json.load(f)

MASTER = str(ROOT / config["caminhos"]["dss_file"])
TRAFO_CRITICO = config.get("graficos", {}).get("trafo_critico", "trf_6_4910a")
LIMITE_PRECARIO_PU = config["tecnico"]["limite_precario_pu"]
LIMITE_CRITICO_PU = config["tecnico"]["limite_critico_pu"]
COORDS_CSV = ROOT / "dss" / "buscoords.csv"

# ---------------------------------------------------------------------------
# 1. Coordenadas
# ---------------------------------------------------------------------------
coords = {}
with open(COORDS_CSV) as f:
    f.readline()
    for line in f:
        parts = line.strip().split(",")
        if len(parts) >= 3:
            bus = parts[0].strip().lower()
            try:
                coords[bus] = (float(parts[1]), float(parts[2]))  # lon, lat
            except ValueError:
                pass

print(f"Coordenadas: {len(coords)} barramentos")

# ---------------------------------------------------------------------------
# 2. Circuito
# ---------------------------------------------------------------------------
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=12"
worst_case_mult = 1.0 + 2 * config["simulacao"]["crescimento_carga"]
dss.Text.Command = f"Set LoadMult={worst_case_mult}"
circuit = dss.ActiveCircuit
circuit.Solution.Solve()

# Detecção dinâmica de problemas no pior caso
worst_case_mult = 1.0 + 2 * config["simulacao"]["crescimento_carga"]
dss.Text.Command = f"Set LoadMult={worst_case_mult}"
circuit.Solution.Solve()

BUSES_SOBRETENSAO = []
all_bus = list(circuit.AllBusNames)
for bname in all_bus:
    circuit.SetActiveBus(bname)
    kv = circuit.ActiveBus.kVBase
    if 0.05 < kv <= 1.0:
        vmag = circuit.ActiveBus.VMagAngle
        if len(vmag) >= 1:
            vpu = vmag[0] / (kv * 1000)
            if vpu > LIMITE_PRECARIO_PU or vpu < 0.921:
                BUSES_SOBRETENSAO.append(bname)

TRAFOS_SOBRECARGA = [TRAFO_CRITICO]

# ---------------------------------------------------------------------------
# 3. Coleta features
# ---------------------------------------------------------------------------


def feature_line(coords_list, props):
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords_list},
        "properties": props,
    }


def feature_point(lon, lat, props):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": props,
    }


feat_mt, feat_bt = [], []
circuit.SetActiveClass("Line")
idx = circuit.Lines.First
while idx > 0:
    b1 = circuit.Lines.Bus1.split(".")[0].lower()
    b2 = circuit.Lines.Bus2.split(".")[0].lower()
    if b1 in coords and b2 in coords:
        c1, c2 = coords[b1], coords[b2]
        circuit.SetActiveBus(b1)
        kv = circuit.ActiveBus.kVBase
        props = {
            "nome": circuit.Lines.Name,
            "is_switch": circuit.Lines.IsSwitch,
            "normAmps": circuit.Lines.NormAmps,
            "length_m": round(circuit.Lines.Length * 1000, 1),
            "kVBase": round(kv, 3),
        }
        line = feature_line([[c1[0], c1[1]], [c2[0], c2[1]]], props)
        if kv > 1.0:
            feat_mt.append(line)
        else:
            feat_bt.append(line)
    idx = circuit.Lines.Next

feat_trafos = []
circuit.SetActiveClass("Transformer")
idx = circuit.Transformers.First
while idx > 0:
    nome = circuit.Transformers.Name
    kva = circuit.Transformers.kVA
    circuit.SetActiveElement(f"Transformer.{nome}")
    buses = list(circuit.ActiveCktElement.BusNames)
    bus_bt = buses[1].split(".")[0].lower() if len(buses) > 1 else ""
    bus_mt = buses[0].split(".")[0].lower()
    powers = circuit.ActiveCktElement.Powers
    n = circuit.ActiveCktElement.NumPhases
    pct = 0.0
    if len(powers) >= n * 2 and kva > 0:
        p = sum(powers[0 : n * 2 : 2])
        q = sum(powers[1 : n * 2 + 1 : 2])
        pct = round(100 * (p**2 + q**2) ** 0.5 / kva, 1)
    pos = coords.get(bus_bt) or coords.get(bus_mt)
    if pos:
        status = "sobrecarga" if pct > 100 else ("alerta" if pct > 80 else "normal")
        feat_trafos.append(
            feature_point(
                pos[0],
                pos[1],
                {
                    "nome": nome,
                    "kVA": kva,
                    "loading_pct": pct,
                    "status": status,
                    "bus_mt": bus_mt,
                    "bus_bt": bus_bt,
                },
            )
        )
    idx = circuit.Transformers.Next

feat_gd = []
idx = circuit.PVSystems.First
while idx > 0:
    nome = circuit.PVSystems.Name
    pmpp = circuit.PVSystems.Pmpp
    kva = circuit.PVSystems.kVArated
    bus_pv = circuit.ActiveCktElement.BusNames[0].split(".")[0].lower()
    if bus_pv in coords:
        pos = coords[bus_pv]
        feat_gd.append(
            feature_point(
                pos[0],
                pos[1],
                {
                    "nome": nome,
                    "Pmpp_kW": pmpp,
                    "kVA": kva,
                    "bus": bus_pv,
                },
            )
        )
    idx = circuit.PVSystems.Next

# Problemas: trafos sobrecarregados + barramentos com sobretensão
feat_prob = []
for t in feat_trafos:
    if t["properties"]["nome"].lower() in TRAFOS_SOBRECARGA:
        p = dict(t["properties"])
        p["tipo_problema"] = "sobrecarga_trafo"
        feat_prob.append(
            feature_point(
                t["geometry"]["coordinates"][0], t["geometry"]["coordinates"][1], p
            )
        )

for bus in BUSES_SOBRETENSAO:
    pos = coords.get(bus)
    if pos:
        feat_prob.append(
            feature_point(
                pos[0],
                pos[1],
                {
                    "nome": bus,
                    "tipo_problema": "sobretensao_bt",
                    "descricao": f"Vmax > {LIMITE_PRECARIO_PU:.3f} pu — violação PRODIST Tabela 5",
                },
            )
        )


# ---------------------------------------------------------------------------
# 4. Escreve GeoJSONs
# ---------------------------------------------------------------------------
def salvar_geojson(nome, features):
    gj = {"type": "FeatureCollection", "features": features}
    path = ROOT / "resultados" / nome
    with open(path, "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False, indent=2)
    kb = path.stat().st_size / 1024
    print(f"  {nome:<35} {len(features):>5} features  {kb:>8.1f} KB")
    return path


print("\nGerando GeoJSONs...")
arquivos = []
arquivos.append(salvar_geojson("rede_linhas_mt.geojson", feat_mt))
arquivos.append(salvar_geojson("rede_linhas_bt.geojson", feat_bt))
arquivos.append(salvar_geojson("rede_trafos.geojson", feat_trafos))
arquivos.append(salvar_geojson("rede_gd.geojson", feat_gd))
arquivos.append(salvar_geojson("rede_problemas.geojson", feat_prob))

print(f"""
Como importar no QGIS:
  1. Layer > Add Layer > Add Vector Layer
  2. Seleciona qualquer .geojson — o QGIS posiciona automaticamente em WGS84
  3. Repete para cada camada
  4. Para estilizar: duplo clique na camada > Symbology
     - Trafos: Categorized por "status" (normal/alerta/sobrecarga)
     - GD: tamanho proporcional ao campo "Pmpp_kW"
     - Problemas: Categorized por "tipo_problema"

Dica: arraste todos os .geojson de uma vez para a janela do QGIS.
""")
