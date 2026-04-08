# 10_exportar_rede_svg_geo.py
# Gera SVGs com coordenadas lon/lat nativas no viewBox
# Compatível com QGIS (importar como vetorial), Leaflet (svgOverlay),
# Inkscape (importar com escala geográfica) e qualquer ferramenta GIS

import sys
from pathlib import Path
import math

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import json

with open(HERE / "parametros.json", "r") as f:
    config = json.load(f)
MASTER = str(HERE / config["caminhos"]["dss_file"])
TRAFO_CRITICO = config.get("graficos", {}).get("trafo_critico", "trf_6_4910a")
COORDS_CSV = HERE / "dss" / "buscoords.csv"

from dss import dss

# ---------------------------------------------------------------------------
# 1. Carrega coordenadas
# ---------------------------------------------------------------------------
coords = {}
with open(COORDS_CSV) as f:
    f.readline()  # header PAC,long,lat
    for line in f:
        parts = line.strip().split(",")
        if len(parts) >= 3:
            bus = parts[0].strip().lower()
            try:
                lon = float(parts[1])
                lat = float(parts[2])
                coords[bus] = (lon, lat)
            except ValueError:
                pass

print(f"Coordenadas: {len(coords)} barramentos")

# Bounding box real da rede
lons = [c[0] for c in coords.values()]
lats = [c[1] for c in coords.values()]
LON_MIN, LON_MAX = min(lons), max(lons)
LAT_MIN, LAT_MAX = min(lats), max(lats)
DLON = LON_MAX - LON_MIN
DLAT = LAT_MAX - LAT_MIN

print(f"Bounding box:")
print(f"  Longitude: {LON_MIN:.6f} → {LON_MAX:.6f}  (Δ={DLON:.6f}°)")
print(f"  Latitude : {LAT_MIN:.6f} → {LAT_MAX:.6f}  (Δ={DLAT:.6f}°)")

# ---------------------------------------------------------------------------
# 2. Projeção: lon/lat → SVG com Y invertido
# O SVG usa viewBox="LON_MIN LAT_MIN_SVG DLON DLAT"
# Y no SVG cresce para baixo, latitude cresce para cima → inverte
#
# Coordenada SVG:
#   x = lon          (direto)
#   y = LAT_MAX - (lat - LAT_MIN) = LAT_MAX + LAT_MIN - lat
#     = LAT_MIN + LAT_MAX - lat
#
# viewBox = "LON_MIN LAT_MIN DLON DLAT"
# (após inversão, LAT_MIN no SVG corresponde ao LAT_MAX geográfico)
# ---------------------------------------------------------------------------


def geo2svg(lon, lat):
    """Converte lon/lat para coordenada SVG (Y invertido)."""
    x = lon
    y = LAT_MIN + LAT_MAX - lat  # inversão do eixo Y
    return x, y


# ViewBox: origem no canto superior esquerdo do mapa
VB_X = LON_MIN
VB_Y = LAT_MIN  # após inversão, LAT_MIN é o topo do SVG
VB_W = DLON
VB_H = DLAT

# Stroke-width em graus (escala geográfica)
# ~0.0001° ≈ 11m — bom para linhas de rede
SW_MT = DLON * 0.0008  # linha MT
SW_BT = DLON * 0.0004  # linha BT
R_TRAFO = DLON * 0.0012  # raio base do trafo
R_GD = DLON * 0.0015  # tamanho base da GD

print(f"\nEscalas SVG (em graus):")
print(f"  stroke-width MT : {SW_MT:.6f}°")
print(f"  stroke-width BT : {SW_BT:.6f}°")
print(f"  raio trafo base : {R_TRAFO:.6f}°")

# ---------------------------------------------------------------------------
# 3. Carrega circuito e coleta elementos
# ---------------------------------------------------------------------------
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=12"
worst_case_mult = 1.0 + 2 * config["simulacao"]["crescimento_carga"]
dss.Text.Command = f"Set LoadMult={worst_case_mult}"
circuit = dss.ActiveCircuit
circuit.Solution.Solve()

linhas_mt, linhas_bt = [], []
circuit.SetActiveClass("Line")
idx = circuit.Lines.First
while idx > 0:
    b1 = circuit.Lines.Bus1.split(".")[0].lower()
    b2 = circuit.Lines.Bus2.split(".")[0].lower()
    if b1 in coords and b2 in coords:
        circuit.SetActiveBus(b1)
        kv = circuit.ActiveBus.kVBase
        isw = circuit.Lines.IsSwitch
        entry = (coords[b1], coords[b2], isw)
        if kv > 1.0:
            linhas_mt.append(entry)
        else:
            linhas_bt.append(entry)
    idx = circuit.Lines.Next

trafos = []
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
        pct = 100 * (p**2 + q**2) ** 0.5 / kva
    pos = coords.get(bus_bt) or coords.get(bus_mt)
    if pos:
        trafos.append({"nome": nome, "kva": kva, "pct": pct, "pos": pos})
    idx = circuit.Transformers.Next

pvs = []
idx = circuit.PVSystems.First
while idx > 0:
    nome = circuit.PVSystems.Name
    pmpp = circuit.PVSystems.Pmpp
    bus_pv = circuit.ActiveCktElement.BusNames[0].split(".")[0].lower()
    if bus_pv in coords:
        pvs.append({"nome": nome, "pmpp": pmpp, "pos": coords[bus_pv]})
    idx = circuit.PVSystems.Next

# Detecção dinâmica de problemas no cenário de pior caso simulado
BUSES_SOBRETENSAO = []
all_bus = list(circuit.AllBusNames)
for bname in all_bus:
    circuit.SetActiveBus(bname)
    kv = circuit.ActiveBus.kVBase
    if 0.05 < kv <= 1.0:
        vmag = circuit.ActiveBus.VMagAngle
        if len(vmag) >= 1:
            vpu = vmag[0] / (kv * 1000)
            if vpu > 1.050 or vpu < 0.921:
                BUSES_SOBRETENSAO.append(bname)

TRAFOS_SOBRECARGA = [TRAFO_CRITICO]

print(f"Linhas MT: {len(linhas_mt)}  BT: {len(linhas_bt)}")
print(f"Trafos: {len(trafos)}  PVSystems: {len(pvs)}")

# ---------------------------------------------------------------------------
# 4. Gerador de SVG georreferenciado
# ---------------------------------------------------------------------------


def svg_header(titulo=""):
    """Cabeçalho SVG com viewBox em coordenadas geográficas."""
    return [
        f'<?xml version="1.0" encoding="UTF-8"?>',
        f"<!-- Rede CRELUZ — Alimentador 1_REDE2_1 -->",
        f"<!-- Coordenadas: WGS84 lon/lat -->",
        f"<!-- BBox: lon [{LON_MIN:.6f}, {LON_MAX:.6f}] lat [{LAT_MIN:.6f}, {LAT_MAX:.6f}] -->",
        f"<!-- Para importar no QGIS: Layer > Add Layer > Add Vector Layer (SVG) -->",
        f"<!-- Para usar no Leaflet: L.svgOverlay(svg, [[{LAT_MIN:.6f},{LON_MIN:.6f}],[{LAT_MAX:.6f},{LON_MAX:.6f}]]) -->",
        f'<svg xmlns="http://www.w3.org/2000/svg"',
        f'     xmlns:xlink="http://www.w3.org/1999/xlink"',
        f'     viewBox="{VB_X:.8f} {VB_Y:.8f} {VB_W:.8f} {VB_H:.8f}"',
        f'     width="1200" height="{int(1200 * DLAT / DLON)}"',
        f'     style="background:transparent">',
        f"  <title>{titulo}</title>",
    ]


def svg_footer():
    return ["</svg>"]


def linhas_mt_svg():
    els = ['  <g id="linhas_mt" opacity="0.9">']
    for c1, c2, is_sw in linhas_mt:
        x1, y1 = geo2svg(c1[0], c1[1])
        x2, y2 = geo2svg(c2[0], c2[1])
        cor = "#888" if is_sw else "#1a1a2e"
        dash = f'stroke-dasharray="{SW_MT * 3:.8f},{SW_MT * 3:.8f}"' if is_sw else ""
        els.append(
            f'    <line x1="{x1:.8f}" y1="{y1:.8f}" '
            f'x2="{x2:.8f}" y2="{y2:.8f}" '
            f'stroke="{cor}" stroke-width="{SW_MT:.8f}" {dash}/>'
        )
    els.append("  </g>")
    return els


def linhas_bt_svg():
    els = ['  <g id="linhas_bt" opacity="0.5">']
    for c1, c2, _ in linhas_bt:
        x1, y1 = geo2svg(c1[0], c1[1])
        x2, y2 = geo2svg(c2[0], c2[1])
        els.append(
            f'    <line x1="{x1:.8f}" y1="{y1:.8f}" '
            f'x2="{x2:.8f}" y2="{y2:.8f}" '
            f'stroke="#bbbbbb" stroke-width="{SW_BT:.8f}"/>'
        )
    els.append("  </g>")
    return els


def trafos_svg():
    els = ['  <g id="transformadores">']
    for t in trafos:
        cx, cy = geo2svg(t["pos"][0], t["pos"][1])
        r = R_TRAFO * max(0.5, min(3.0, math.log10(max(1, t["kva"]))))
        cor = (
            "#e74c3c" if t["pct"] > 100 else ("#e67e22" if t["pct"] > 80 else "#27ae60")
        )
        tip = f"{t['nome']} | {t['kva']:.0f} kVA | {t['pct']:.1f}%"
        els.append(
            f'    <circle cx="{cx:.8f}" cy="{cy:.8f}" r="{r:.8f}" '
            f'fill="{cor}" stroke="white" stroke-width="{r * 0.15:.8f}" '
            f'opacity="0.85"><title>{tip}</title></circle>'
        )
    els.append("  </g>")
    return els


def gd_svg():
    els = ['  <g id="gd_fotovoltaica">']
    for pv in pvs:
        cx, cy = geo2svg(pv["pos"][0], pv["pos"][1])
        r = R_GD * max(0.8, min(4.0, pv["pmpp"] / 15))
        # Triângulo equilátero apontando para cima
        pts = (
            f"{cx:.8f},{cy - r:.8f} "
            f"{cx - r * 0.866:.8f},{cy + r * 0.5:.8f} "
            f"{cx + r * 0.866:.8f},{cy + r * 0.5:.8f}"
        )
        tip = f"{pv['nome']} | {pv['pmpp']:.0f} kW"
        els.append(
            f'    <polygon points="{pts}" '
            f'fill="#f39c12" stroke="#d68910" stroke-width="{r * 0.1:.8f}" '
            f'opacity="0.9"><title>{tip}</title></polygon>'
        )
    els.append("  </g>")
    return els


def problemas_svg():
    els = ['  <g id="problemas">']
    # Trafos sobrecarregados — X vermelho
    for t in trafos:
        if t["nome"].lower() in TRAFOS_SOBRECARGA:
            cx, cy = geo2svg(t["pos"][0], t["pos"][1])
            s = R_TRAFO * 2.5
            sw = s * 0.3
            tip = f"SOBRECARGA: {t['nome']} {t['pct']:.1f}%"
            els.append(f"    <g><title>{tip}</title>")
            els.append(
                f'    <line x1="{cx - s:.8f}" y1="{cy - s:.8f}" '
                f'x2="{cx + s:.8f}" y2="{cy + s:.8f}" '
                f'stroke="#c0392b" stroke-width="{sw:.8f}"/>'
            )
            els.append(
                f'    <line x1="{cx + s:.8f}" y1="{cy - s:.8f}" '
                f'x2="{cx - s:.8f}" y2="{cy + s:.8f}" '
                f'stroke="#c0392b" stroke-width="{sw:.8f}"/>'
            )
            els.append(f"    </g>")
    # Barramentos com sobretensão — diamante laranja
    for bus in BUSES_SOBRETENSAO:
        pos = coords.get(bus)
        if pos:
            cx, cy = geo2svg(pos[0], pos[1])
            s = R_TRAFO * 2.0
            pts = (
                f"{cx:.8f},{cy - s:.8f} "
                f"{cx + s:.8f},{cy:.8f} "
                f"{cx:.8f},{cy + s:.8f} "
                f"{cx - s:.8f},{cy:.8f}"
            )
            els.append(
                f'    <polygon points="{pts}" '
                f'fill="#e67e22" stroke="#a04000" stroke-width="{s * 0.15:.8f}" '
                f'opacity="0.9"><title>SOBRETENSÃO: {bus}</title></polygon>'
            )
    els.append("  </g>")
    return els


# ---------------------------------------------------------------------------
# 5. Gera os arquivos
# ---------------------------------------------------------------------------
def escrever_svg(nome, camadas, titulo=""):
    linhas = svg_header(titulo)
    for camada in camadas:
        linhas.extend(camada())
    linhas.extend(svg_footer())
    path = HERE / "Resultados" / "graficos" / nome
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))
    kb = path.stat().st_size / 1024
    print(f"  {nome:<35} {kb:>8.1f} KB")
    return path


print("\nGerando SVGs georreferenciados...")

svgs_gerados = []
svgs_gerados.append(
    escrever_svg(
        "rede_completa_geo.svg",
        [linhas_bt_svg, linhas_mt_svg, trafos_svg, gd_svg, problemas_svg],
        "CRELUZ — Alimentador 1_REDE2_1 — Rede Completa",
    )
)

svgs_gerados.append(
    escrever_svg("rede_linhas_mt_geo.svg", [linhas_mt_svg], "CRELUZ — Linhas MT")
)

svgs_gerados.append(
    escrever_svg("rede_linhas_bt_geo.svg", [linhas_bt_svg], "CRELUZ — Linhas BT")
)

svgs_gerados.append(
    escrever_svg("rede_trafos_geo.svg", [trafos_svg], "CRELUZ — Transformadores")
)

svgs_gerados.append(
    escrever_svg("rede_gd_geo.svg", [gd_svg], "CRELUZ — GD Fotovoltaica")
)

svgs_gerados.append(
    escrever_svg(
        "rede_problemas_geo.svg",
        [linhas_mt_svg, problemas_svg],
        "CRELUZ — Problemas identificados",
    )
)

# ---------------------------------------------------------------------------
# 6. Gera arquivo HTML com Leaflet para visualização imediata
# ---------------------------------------------------------------------------
html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>CRELUZ — Alimentador 1_REDE2_1</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    body {{ margin: 0; }}
    #map {{ height: 100vh; }}
    #controles {{
      position: absolute; top: 10px; right: 10px; z-index: 1000;
      background: white; padding: 12px; border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3); font-family: sans-serif;
      font-size: 13px; min-width: 180px;
    }}
    #controles h3 {{ margin: 0 0 10px 0; font-size: 14px; }}
    #controles label {{ display: block; margin: 4px 0; cursor: pointer; }}
    .legenda-cor {{
      display: inline-block; width: 14px; height: 14px;
      border-radius: 50%; margin-right: 6px; vertical-align: middle;
    }}
  </style>
</head>
<body>
<div id="map"></div>
<div id="controles">
  <h3>Camadas — CRELUZ</h3>
  <label><input type="checkbox" id="chk_mt" checked> Linhas MT</label>
  <label><input type="checkbox" id="chk_bt" checked> Linhas BT</label>
  <label><input type="checkbox" id="chk_trafos" checked>
    <span class="legenda-cor" style="background:#27ae60"></span>Trafos</label>
  <label><input type="checkbox" id="chk_gd" checked>
    <span class="legenda-cor" style="background:#f39c12; border-radius:0"></span>GD Solar</label>
  <label><input type="checkbox" id="chk_prob" checked>
    <span class="legenda-cor" style="background:#e74c3c"></span>Problemas</label>
  <hr/>
  <small>
    <b>Trafos:</b><br>
    🟢 &lt;80% &nbsp; 🟠 80-100% &nbsp; 🔴 &gt;100%<br>
    🔶 Sobretensão BT<br>
    ✕ Trafo sobrecarregado
  </small>
</div>
<script>
  const bounds = [[{LAT_MIN:.6f}, {LON_MIN:.6f}], [{LAT_MAX:.6f}, {LON_MAX:.6f}]];
  const center = [{(LAT_MIN + LAT_MAX) / 2:.6f}, {(LON_MIN + LON_MAX) / 2:.6f}];

  const map = L.map('map').setView(center, 13);

  const osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '© OpenStreetMap'
  }});
  const sat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    attribution: '© Esri'
  }});
  osm.addTo(map);
  L.control.layers({{"OSM": osm, "Satélite": sat}}).addTo(map);

  // Carrega e exibe cada SVG como overlay
  function svgOverlay(url, id) {{
    return fetch(url)
      .then(r => r.text())
      .then(svgText => {{
        const parser = new DOMParser();
        const doc = parser.parseFromString(svgText, 'image/svg+xml');
        const svg = doc.documentElement;
        const overlay = L.svgOverlay(svg, bounds, {{interactive: true}});
        overlay.id = id;
        return overlay;
      }});
  }}

  const camadas = {{}};

  Promise.all([
    svgOverlay('rede_linhas_bt_geo.svg',  'bt'),
    svgOverlay('rede_linhas_mt_geo.svg',  'mt'),
    svgOverlay('rede_trafos_geo.svg',     'trafos'),
    svgOverlay('rede_gd_geo.svg',         'gd'),
    svgOverlay('rede_problemas_geo.svg',  'prob'),
  ]).then(([bt, mt, trafos, gd, prob]) => {{
    camadas.bt     = bt.addTo(map);
    camadas.mt     = mt.addTo(map);
    camadas.trafos = trafos.addTo(map);
    camadas.gd     = gd.addTo(map);
    camadas.prob   = prob.addTo(map);
  }});

  // Controles de visibilidade
  document.getElementById('chk_mt').addEventListener('change', e => {{
    e.target.checked ? camadas.mt?.addTo(map) : camadas.mt?.remove();
  }});
  document.getElementById('chk_bt').addEventListener('change', e => {{
    e.target.checked ? camadas.bt?.addTo(map) : camadas.bt?.remove();
  }});
  document.getElementById('chk_trafos').addEventListener('change', e => {{
    e.target.checked ? camadas.trafos?.addTo(map) : camadas.trafos?.remove();
  }});
  document.getElementById('chk_gd').addEventListener('change', e => {{
    e.target.checked ? camadas.gd?.addTo(map) : camadas.gd?.remove();
  }});
  document.getElementById('chk_prob').addEventListener('change', e => {{
    e.target.checked ? camadas.prob?.addTo(map) : camadas.prob?.remove();
  }});
</script>
</body>
</html>"""

html_path = HERE / "Resultados" / "graficos" / "visualizar_rede.html"
with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"  {'visualizar_rede.html':<35} {html_path.stat().st_size / 1024:>8.1f} KB")

print(f"""
Pronto. Para visualizar:
  1. Abra a pasta Resultados/graficos/ no terminal
  2. python -m http.server 8080
  3. Acesse http://localhost:8080/visualizar_rede.html

Para usar no QGIS:
  Layer > Add Layer > Add Vector Layer > seleciona rede_completa_geo.svg
  (o QGIS lê o viewBox em graus e posiciona automaticamente)

Para usar no Inkscape com georreferenciamento:
  Abra qualquer *_geo.svg — o viewBox já está em lon/lat
""")
