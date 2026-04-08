# 10_exportar_rede_svg.py
# Gera SVGs em camadas para sobreposição em mapa:
#   rede_linhas_mt.svg     — linhas de média tensão
#   rede_linhas_bt.svg     — linhas de baixa tensão
#   rede_trafos.svg        — transformadores (tamanho proporcional ao kVA)
#   rede_gd.svg            — PVSystems (proporcional ao Pmpp)
#   rede_problemas.svg     — trafos com sobrecarga + barramentos com sobretensão
#   rede_completa.svg      — tudo junto

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
from dss import dss

COORDS_CSV = HERE / "dss" / "buscoords.csv"

# ---------------------------------------------------------------------------
# 1. Carrega coordenadas
# ---------------------------------------------------------------------------
coords = {}
with open(COORDS_CSV) as f:
    header = f.readline()  # PAC,long,lat
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

print(f"Coordenadas carregadas: {len(coords)} barramentos")

# ---------------------------------------------------------------------------
# 2. Carrega circuito
# ---------------------------------------------------------------------------
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=12"
worst_case_mult = 1.0 + 2 * config["simulacao"]["crescimento_carga"]
dss.Text.Command = f"Set LoadMult={worst_case_mult}"
circuit = dss.ActiveCircuit
circuit.Solution.Solve()

# ---------------------------------------------------------------------------
# 3. Coleta dados dos elementos
# ---------------------------------------------------------------------------

# --- Linhas MT ---
linhas_mt = []
linhas_bt = []
circuit.SetActiveClass("Line")
idx = circuit.Lines.First
while idx > 0:
    b1 = circuit.Lines.Bus1.split(".")[0].lower()
    b2 = circuit.Lines.Bus2.split(".")[0].lower()
    if b1 in coords and b2 in coords:
        circuit.SetActiveBus(b1)
        kv = circuit.ActiveBus.kVBase
        entry = (coords[b1], coords[b2], circuit.Lines.IsSwitch)
        if kv > 1.0:
            linhas_mt.append(entry)
        else:
            linhas_bt.append(entry)
    idx = circuit.Lines.Next

print(f"Linhas MT com coords: {len(linhas_mt)}")
print(f"Linhas BT com coords: {len(linhas_bt)}")

# --- Transformadores ---
trafos = []
circuit.SetActiveClass("Transformer")
idx = circuit.Transformers.First
while idx > 0:
    nome = circuit.Transformers.Name
    kva = circuit.Transformers.kVA
    circuit.SetActiveElement(f"Transformer.{nome}")
    buses = list(circuit.ActiveCktElement.BusNames)
    # Usa barramento BT (secundário) para posicionar
    bus_bt = buses[1].split(".")[0].lower() if len(buses) > 1 else ""
    bus_mt = buses[0].split(".")[0].lower()
    # Carregamento atual (hora 12, LoadMult=1.2)
    powers = circuit.ActiveCktElement.Powers
    n = circuit.ActiveCktElement.NumPhases
    pct = 0.0
    if len(powers) >= n * 2 and kva > 0:
        p = sum(powers[0 : n * 2 : 2])
        q = sum(powers[1 : n * 2 + 1 : 2])
        pct = 100 * (p**2 + q**2) ** 0.5 / kva
    # Posição: usa BT se disponível, senão MT
    pos = coords.get(bus_bt) or coords.get(bus_mt)
    if pos:
        trafos.append({"nome": nome, "kva": kva, "pct": pct, "pos": pos})
    idx = circuit.Transformers.Next

print(f"Transformadores com coords: {len(trafos)}")

# --- PVSystems ---
pvs = []
idx = circuit.PVSystems.First
while idx > 0:
    nome = circuit.PVSystems.Name
    pmpp = circuit.PVSystems.Pmpp
    bus_pv = circuit.ActiveCktElement.BusNames[0].split(".")[0].lower()
    if bus_pv in coords:
        pvs.append({"nome": nome, "pmpp": pmpp, "pos": coords[bus_pv]})
    idx = circuit.PVSystems.Next

print(f"PVSystems com coords: {len(pvs)}")

# Detecção dinâmica de problemas (Vmax > 1.050 ou Vmin < 0.921)
BUSES_SOBRETENSAO = []
all_bus = list(circuit.AllBusNames)
for bname in all_bus:
    circuit.SetActiveBus(bname)
    kv = circuit.ActiveBus.kVBase
    if 0.05 < kv <= 1.0:
        vmag = circuit.ActiveBus.VMagAngle
        if len(vmag) >= 1:
            vpu = vmag[0] / (kv * 1000)
            if (vpu > 1.050 or vpu < 0.921) and bname not in BUSES_SOBRETENSAO:
                BUSES_SOBRETENSAO.append(bname)

TRAFOS_SOBRECARGA = [TRAFO_CRITICO]

# ---------------------------------------------------------------------------
# 4. Funções de geração SVG
# ---------------------------------------------------------------------------


def bbox(elementos_coords):
    """Calcula bounding box de uma lista de (lon, lat)."""
    xs = [c[0] for c in elementos_coords if c]
    ys = [c[1] for c in elementos_coords if c]
    return min(xs), max(xs), min(ys), max(ys)


def projeto(lon, lat, xmin, ymin, xmax, ymax, W, H, margin=20):
    """Projeta lon/lat para coordenadas SVG (Y invertido)."""
    # Escala mantendo proporção
    dx = xmax - xmin
    dy = ymax - ymin
    scale = (
        min((W - 2 * margin) / dx, (H - 2 * margin) / dy) if dx > 0 and dy > 0 else 1
    )
    cx = margin + (lon - xmin) * scale
    cy = H - margin - (lat - ymin) * scale  # inverte Y
    return cx, cy


def gerar_svg(nome_arquivo, camadas_fn, W=1200, H=1200):
    """Gera um arquivo SVG chamando funções de camada."""
    # Calcula bbox global
    all_coords = list(coords.values())
    xmin, xmax, ymin, ymax = bbox(all_coords)

    linhas_svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" '
        f'style="background:transparent">',
        "  <defs>",
        '    <marker id="arrow" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">',
        '      <path d="M0,0 L6,3 L0,6 Z" fill="#333"/>',
        "    </marker>",
        "  </defs>",
    ]

    def p(lon, lat):
        return projeto(lon, lat, xmin, ymin, xmax, ymax, W, H)

    for fn in camadas_fn:
        linhas_svg.extend(fn(p))

    linhas_svg.append("</svg>")

    path = HERE / "Resultados" / "graficos" / nome_arquivo
    with open(path, "w") as f:
        f.write("\n".join(linhas_svg))
    print(f"  Gerado: {nome_arquivo}")
    return path


# ---------------------------------------------------------------------------
# 5. Camadas individuais
# ---------------------------------------------------------------------------


def camada_linhas_mt(p):
    els = ["  <!-- Linhas MT -->", '  <g id="linhas_mt" opacity="0.8">']
    for c1, c2, is_sw in linhas_mt:
        x1, y1 = p(c1[0], c1[1])
        x2, y2 = p(c2[0], c2[1])
        cor = "#888888" if is_sw else "#1a1a2e"
        dash = 'stroke-dasharray="4,4"' if is_sw else ""
        els.append(
            f'    <line x1="{x1:.1f}" y1="{y1:.1f}" '
            f'x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{cor}" stroke-width="1.2" {dash}/>'
        )
    els.append("  </g>")
    return els


def camada_linhas_bt(p):
    els = ["  <!-- Linhas BT -->", '  <g id="linhas_bt" opacity="0.5">']
    for c1, c2, is_sw in linhas_bt:
        x1, y1 = p(c1[0], c1[1])
        x2, y2 = p(c2[0], c2[1])
        els.append(
            f'    <line x1="{x1:.1f}" y1="{y1:.1f}" '
            f'x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#aaaaaa" stroke-width="0.6"/>'
        )
    els.append("  </g>")
    return els


def camada_trafos(p):
    els = ["  <!-- Transformadores -->", '  <g id="transformadores">']
    for t in trafos:
        cx, cy = p(t["pos"][0], t["pos"][1])
        r = max(2, min(8, t["kva"] / 30))  # raio proporcional ao kVA
        cor = (
            "#e74c3c" if t["pct"] > 100 else ("#e67e22" if t["pct"] > 80 else "#2ecc71")
        )
        tip = f"{t['nome']} | {t['kva']:.0f} kVA | {t['pct']:.1f}%"
        els.append(
            f'    <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
            f'fill="{cor}" stroke="white" stroke-width="0.5" opacity="0.85">'
            f"<title>{tip}</title></circle>"
        )
    els.append("  </g>")
    return els


def camada_gd(p):
    els = ["  <!-- PVSystems (GD Fotovoltaica) -->", '  <g id="gd_fotovoltaica">']
    for pv in pvs:
        cx, cy = p(pv["pos"][0], pv["pos"][1])
        r = max(3, min(10, pv["pmpp"] / 8))
        tip = f"{pv['nome']} | {pv['pmpp']:.0f} kW"
        # Triângulo apontando para cima (símbolo solar)
        dx, dy = r, r * 1.15
        pts = f"{cx:.1f},{cy - dy:.1f} {cx - dx:.1f},{cy + dy * 0.5:.1f} {cx + dx:.1f},{cy + dy * 0.5:.1f}"
        els.append(
            f'    <polygon points="{pts}" '
            f'fill="#f39c12" stroke="#e67e22" stroke-width="0.8" opacity="0.9">'
            f"<title>{tip}</title></polygon>"
        )
    els.append("  </g>")
    return els


def camada_problemas(p):
    els = ["  <!-- Elementos com problema -->", '  <g id="problemas">']

    # Trafos sobrecarregados — X vermelho
    for t in trafos:
        if t["nome"].lower() in TRAFOS_SOBRECARGA:
            cx, cy = p(t["pos"][0], t["pos"][1])
            s = 8
            tip = f"SOBRECARGA: {t['nome']} | {t['pct']:.1f}%"
            els.append(f"    <g><title>{tip}</title>")
            els.append(
                f'    <line x1="{cx - s:.1f}" y1="{cy - s:.1f}" '
                f'x2="{cx + s:.1f}" y2="{cy + s:.1f}" '
                f'stroke="#c0392b" stroke-width="2.5"/>'
            )
            els.append(
                f'    <line x1="{cx + s:.1f}" y1="{cy - s:.1f}" '
                f'x2="{cx - s:.1f}" y2="{cy + s:.1f}" '
                f'stroke="#c0392b" stroke-width="2.5"/>'
            )
            els.append(f"    </g>")

    # Barramentos com sobretensão — diamante laranja
    for bus in BUSES_SOBRETENSAO:
        pos = coords.get(bus)
        if pos:
            cx, cy = p(pos[0], pos[1])
            s = 7
            pts = f"{cx:.1f},{cy - s:.1f} {cx + s:.1f},{cy:.1f} {cx:.1f},{cy + s:.1f} {cx - s:.1f},{cy:.1f}"
            els.append(
                f'    <polygon points="{pts}" '
                f'fill="#e67e22" stroke="#d35400" stroke-width="1.5" opacity="0.9">'
                f"<title>SOBRETENSÃO: {bus}</title></polygon>"
            )

    els.append("  </g>")
    return els


def camada_legenda(p):
    """Legenda fixa no canto inferior esquerdo."""
    els = [
        "  <!-- Legenda -->",
        '  <g id="legenda" transform="translate(20, 1080)">',
        '    <rect x="0" y="-10" width="220" height="115" fill="white" '
        '          fill-opacity="0.85" rx="6" stroke="#ccc" stroke-width="1"/>',
        # Linhas MT
        '    <line x1="8" y1="8" x2="28" y2="8" stroke="#1a1a2e" stroke-width="1.5"/>',
        '    <text x="34" y="12" font-size="10" font-family="sans-serif">Linha MT</text>',
        # Linhas BT
        '    <line x1="8" y1="24" x2="28" y2="24" stroke="#aaa" stroke-width="1"/>',
        '    <text x="34" y="28" font-size="10" font-family="sans-serif">Linha BT</text>',
        # Trafo normal
        '    <circle cx="18" cy="44" r="5" fill="#2ecc71" stroke="white" stroke-width="0.5"/>',
        '    <text x="34" y="48" font-size="10" font-family="sans-serif">Trafo (&lt;80%)</text>',
        # Trafo alerta
        '    <circle cx="18" cy="60" r="5" fill="#e67e22" stroke="white" stroke-width="0.5"/>',
        '    <text x="34" y="64" font-size="10" font-family="sans-serif">Trafo (80-100%)</text>',
        # Trafo sobrecarga
        '    <circle cx="18" cy="76" r="5" fill="#e74c3c" stroke="white" stroke-width="0.5"/>',
        '    <text x="34" y="80" font-size="10" font-family="sans-serif">Trafo (&gt;100%)</text>',
        # GD
        '    <polygon points="18,86 11,100 25,100" fill="#f39c12" stroke="#e67e22" stroke-width="0.8"/>',
        '    <text x="34" y="97" font-size="10" font-family="sans-serif">GD Fotovoltaica</text>',
        "  </g>",
    ]
    return els


# ---------------------------------------------------------------------------
# 6. Gera os SVGs
# ---------------------------------------------------------------------------
print("\nGerando SVGs...")

svgs = []

# Rede completa
svgs.append(
    gerar_svg(
        "rede_completa.svg",
        [
            camada_linhas_bt,
            camada_linhas_mt,
            camada_trafos,
            camada_gd,
            camada_problemas,
            camada_legenda,
        ],
    )
)

# Só linhas MT
svgs.append(gerar_svg("rede_linhas_mt.svg", [camada_linhas_mt]))

# Só linhas BT
svgs.append(gerar_svg("rede_linhas_bt.svg", [camada_linhas_bt]))

# Só trafos
svgs.append(gerar_svg("rede_trafos.svg", [camada_trafos]))

# Só GD
svgs.append(gerar_svg("rede_gd.svg", [camada_gd]))

# Só problemas
svgs.append(
    gerar_svg(
        "rede_problemas.svg",
        [
            camada_linhas_mt,
            camada_problemas,
        ],
    )
)

print(f"\nTodos os SVGs gerados em {HERE}")
