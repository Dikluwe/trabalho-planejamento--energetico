# 11_graficos_svg.py
# Gera SVGs dos gráficos para o relatório IEEE
# Todos com fundo branco, proporção adequada para duas colunas IEEE (~8cm × 6cm)

import sys
from pathlib import Path
import math

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pandas as pd
import json

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# ---------------------------------------------------------------------------
# Carregamento de Parâmetros (Arquivo JSON)
# ---------------------------------------------------------------------------

CONFIG_FILE = HERE / "parametros.json"
if not CONFIG_FILE.exists():
    print(f"ERRO: Arquivo de configuração {CONFIG_FILE.name} não encontrado.")
    sys.exit(1)

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

TRAFO_ALVO = config["graficos"]["trafo_critico"]
MEDIDOR_SUB = config["graficos"]["medidor_subestacao"]
OUTPUT_FOLDER_BASE = config["caminhos"]["output_base"]

# Dimensões padrão IEEE duas colunas (em pixels @96dpi ≈ 300px × 225px)
# Usamos unidades SVG arbitrárias — o importante é a proporção 4:3
W, H   = 400, 300
PAD    = dict(top=30, right=20, bottom=50, left=60)
PW     = W - PAD["left"] - PAD["right"]   # área de plot largura
PH     = H - PAD["top"]  - PAD["bottom"]  # área de plot altura

CORES = {
    "ano1":    "#2c7bb6",
    "ano2":    "#f4a300",
    "ano3":    "#d7191c",
    "limite":  "#333333",
    "gd":      "#f39c12",
    "sub":     "#2980b9",
    "perdas":  "#e74c3c",
    "carga":   "#27ae60",
    "tap":     "#8e44ad",
    "grade":   "#e8e8e8",
    "texto":   "#222222",
}

FONT = "font-family='Arial,sans-serif'"

# ---------------------------------------------------------------------------
# Helpers de desenho SVG
# ---------------------------------------------------------------------------

def esc(x, xmin, xmax):
    """Escala valor x para pixels (horizontal)."""
    return PAD["left"] + (x - xmin) / (xmax - xmin) * PW

def esc_y(y, ymin, ymax):
    """Escala valor y para pixels (vertical, invertido)."""
    return PAD["top"] + PH - (y - ymin) / (ymax - ymin) * PH

def svg_base(titulo="", subtitulo=""):
    linhas = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" style="background:white">',
        # Grade de fundo
        f'<rect x="{PAD["left"]}" y="{PAD["top"]}" width="{PW}" height="{PH}" '
        f'fill="white" stroke="#cccccc" stroke-width="0.5"/>',
    ]
    if titulo:
        linhas.append(f'<text x="{W//2}" y="18" text-anchor="middle" '
                      f'{FONT} font-size="11" font-weight="bold" '
                      f'fill="{CORES["texto"]}">{titulo}</text>')
    if subtitulo:
        linhas.append(f'<text x="{W//2}" y="28" text-anchor="middle" '
                      f'{FONT} font-size="8" fill="#666">{subtitulo}</text>')
    return linhas

def grade_h(linhas, yvals, ymin, ymax, fmt="{:.0f}"):
    for y in yvals:
        yp = esc_y(y, ymin, ymax)
        linhas.append(f'<line x1="{PAD["left"]}" y1="{yp:.1f}" '
                      f'x2="{PAD["left"]+PW}" y2="{yp:.1f}" '
                      f'stroke="{CORES["grade"]}" stroke-width="0.8"/>')
        linhas.append(f'<text x="{PAD["left"]-4}" y="{yp+3:.1f}" '
                      f'text-anchor="end" {FONT} font-size="8" '
                      f'fill="#555">{fmt.format(y)}</text>')

def eixo_x_labels(linhas, xvals, labels, ybase, rot=0):
    for xv, lb in zip(xvals, labels):
        xp = xv if isinstance(xv, float) and xv > PAD["left"] else xv
        if rot:
            linhas.append(f'<text x="{xp:.1f}" y="{ybase+4}" '
                          f'text-anchor="end" {FONT} font-size="8" fill="#555" '
                          f'transform="rotate({rot},{xp:.1f},{ybase+4})">{lb}</text>')
        else:
            linhas.append(f'<text x="{xp:.1f}" y="{ybase+10}" '
                          f'text-anchor="middle" {FONT} font-size="8" fill="#555">{lb}</text>')

def label_eixo(linhas, xlabel="", ylabel=""):
    yb = PAD["top"] + PH + 38
    if xlabel:
        linhas.append(f'<text x="{PAD["left"] + PW//2}" y="{yb}" '
                      f'text-anchor="middle" {FONT} font-size="9" fill="#444">{xlabel}</text>')
    if ylabel:
        cx = 12
        cy = PAD["top"] + PH//2
        linhas.append(f'<text x="{cx}" y="{cy}" text-anchor="middle" '
                      f'{FONT} font-size="9" fill="#444" '
                      f'transform="rotate(-90,{cx},{cy})">{ylabel}</text>')

def svg_fim():
    return ['</svg>']

def salvar(nome, linhas):
    pasta_graficos = HERE / "graficos"
    pasta_graficos.mkdir(exist_ok=True)
    path = pasta_graficos / nome
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(linhas))
    print(f"  {nome:<40} {path.stat().st_size//1024:>4} KB")

# ---------------------------------------------------------------------------
# Carregamento de dados a partir dos arquivos CSV (Consumo de resultados)
# ---------------------------------------------------------------------------

print("Carregando resultados dos arquivos CSV...")

perfil_trafos = {1: [], 2: [], 3: []}
perfil_sub    = []
perfil_gd     = []
perfil_perd   = []
perfil_carga  = []
perfil_vmin   = []
perfil_vmax   = []

for ano in [1, 2, 3]:
    folder = HERE / f"{OUTPUT_FOLDER_BASE}_ano{ano}"
    if not folder.exists():
        print(f"ERRO: Pasta {folder.name} não encontrada.")
        sys.exit(1)

    # 1. Carregamento do Transformador Crítico
    df_trafo_hr = pd.read_csv(folder / "TransformersLoadingByHour.csv")
    df_trafo_target = df_trafo_hr[df_trafo_hr["transformer"] == TRAFO_ALVO]
    perfil_trafos[ano] = df_trafo_target["loadingPct"].tolist()

    if ano == 1:
        # 2. Balanço Energético (Subestação, Perdas, GD)
        df_meters = pd.read_csv(folder / "EnergyMetersByHour.csv")
        
        # Agrupa perdas de todos os medidores por hora
        perfil_perd = df_meters.groupby("hour")["deltaActiveLossesKWh"].sum().tolist()
        
        # Energia da Subestação (medidor de entrada)
        df_sub = df_meters[df_meters["meterName"] == MEDIDOR_SUB]
        perfil_sub = df_sub["deltaActiveEnergyKWh"].tolist()
        
        # GD: Soma de PVSystems (restante que não é sub nem perdas técnicas internas)
        # Mais simples: o sistema tem um totalEnergyKWh no EnergySummary.
        # Vamos tentar somar os medidores que têm 'gd' no nome
        df_gd = df_meters[df_meters["meterName"].str.contains("gd", case=False)]
        if not df_gd.empty:
            perfil_gd = df_gd.groupby("hour")["deltaActiveEnergyKWh"].sum().tolist()
        else:
            # Caso não encontre medidores com "gd", tenta inferir (Subestação costuma ser a fonte)
            # ou usa 0 se não houver GD no cenário base
            perfil_gd = [0.0] * 24
            
        # Carga total do ponto de vista da rede: Subestação + GD - Perdas
        # (Aproximação: toda energia injetada vai para carga ou perdas)
        perfil_carga = [s + g - p for s, g, p in zip(perfil_sub, perfil_gd, perfil_perd)]

        # 3. Tensão BT Min/Max
        df_volt = pd.read_csv(folder / "VoltagesByHour.csv")
        df_bt = df_volt[df_volt["voltageLevel"] == "LV"]
        perfil_vmin = df_bt.groupby("hour")["voltagePu"].min().tolist()
        perfil_vmax = df_bt.groupby("hour")["voltagePu"].max().tolist()

print("  Dados carregados.")

horas = list(range(1, 25))

# GRÁFICO 1 — Carregamento do transformador (24h, 3 anos)
# ===========================================================================
print("\nGerando gráficos...")
ls = svg_base(f"Carregamento do Transformador {TRAFO_ALVO}",
              "Perfil diário — Anos 1, 2 e 3")

ymin, ymax = 0, 115
grade_h(ls, [20,40,60,80,100], ymin, ymax)

# Linha de limite 100%
y100 = esc_y(100, ymin, ymax)
ls.append(f'<line x1="{PAD["left"]}" y1="{y100:.1f}" '
          f'x2="{PAD["left"]+PW}" y2="{y100:.1f}" '
          f'stroke="{CORES["limite"]}" stroke-width="1" '
          f'stroke-dasharray="4,3"/>')
ls.append(f'<text x="{PAD["left"]+PW-2}" y="{y100-3:.1f}" '
          f'text-anchor="end" {FONT} font-size="7" fill="{CORES["limite"]}">100%</text>')

# Curvas
for ano, cor in [(1, CORES["ano1"]), (2, CORES["ano2"]), (3, CORES["ano3"])]:
    pts = " ".join(f"{esc(h,1,24):.1f},{esc_y(v,ymin,ymax):.1f}"
                   for h, v in zip(horas, perfil_trafos[ano]))
    ls.append(f'<polyline points="{pts}" fill="none" stroke="{cor}" '
              f'stroke-width="1.5"/>')

# Rótulos eixo X
xb = PAD["top"] + PH
eixo_x_labels(ls,
    [esc(h, 1, 24) for h in [1,4,7,10,13,16,19,22,24]],
    ["1h","4h","7h","10h","13h","16h","19h","22h","24h"],
    PAD["top"] + PH)

label_eixo(ls, "Hora do dia", "Carregamento (%)")

# Legenda
for i, (ano, cor, label) in enumerate([(1,CORES["ano1"],"Ano 1 (×1,0)"),
                                         (2,CORES["ano2"],"Ano 2 (×1,1)"),
                                         (3,CORES["ano3"],"Ano 3 (×1,2)")]):
    lx = PAD["left"] + 10 + i*110
    ly = PAD["top"] + 8
    ls.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+18}" y2="{ly}" '
              f'stroke="{cor}" stroke-width="1.5"/>')
    ls.append(f'<text x="{lx+22}" y="{ly+3}" {FONT} font-size="8" '
              f'fill="{CORES["texto"]}">{label}</text>')

ls.extend(svg_fim())
salvar("grafico_carregamento_trafo.svg", ls)

# ===========================================================================
# GRÁFICO 2 — Balanço energético hora a hora
# ===========================================================================
ls = svg_base("Balanço Energético — Ano 1",
              "Subestação · GD Solar · Perdas")

ymin, ymax = 0, 1150
grade_h(ls, [200,400,600,800,1000], ymin, ymax, "{:.0f}")

# Área: carga total (sub + gd - perdas)
pts_carga  = " ".join(f"{esc(h,1,24):.1f},{esc_y(v,ymin,ymax):.1f}"
                      for h, v in zip(horas, perfil_carga))
pts_base   = f"{esc(24,1,24):.1f},{esc_y(0,ymin,ymax):.1f} {esc(1,1,24):.1f},{esc_y(0,ymin,ymax):.1f}"
ls.append(f'<polygon points="{pts_carga} {pts_base}" '
          f'fill="{CORES["carga"]}" fill-opacity="0.15" stroke="none"/>')
ls.append(f'<polyline points="{pts_carga}" fill="none" '
          f'stroke="{CORES["carga"]}" stroke-width="1.5"/>')

# Linha subestação
pts_sub = " ".join(f"{esc(h,1,24):.1f},{esc_y(v,ymin,ymax):.1f}"
                   for h, v in zip(horas, perfil_sub))
ls.append(f'<polyline points="{pts_sub}" fill="none" '
          f'stroke="{CORES["sub"]}" stroke-width="1.5"/>')

# Linha GD
pts_gd = " ".join(f"{esc(h,1,24):.1f},{esc_y(v,ymin,ymax):.1f}"
                  for h, v in zip(horas, perfil_gd))
ls.append(f'<polyline points="{pts_gd}" fill="none" '
          f'stroke="{CORES["gd"]}" stroke-width="1.5" stroke-dasharray="4,2"/>')

# Eixo X
eixo_x_labels(ls,
    [esc(h,1,24) for h in [1,4,7,10,13,16,19,22,24]],
    ["1h","4h","7h","10h","13h","16h","19h","22h","24h"],
    PAD["top"]+PH)
label_eixo(ls, "Hora do dia", "Potência (kW)")

# Legenda
items = [
    (CORES["carga"], "Consumo total", False),
    (CORES["sub"],   "Subestação",    False),
    (CORES["gd"],    "GD Solar",      True),
]
for i, (cor, label, dash) in enumerate(items):
    lx = PAD["left"] + 5 + i*115
    ly = PAD["top"] + 9
    da = 'stroke-dasharray="4,2"' if dash else ''
    ls.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+18}" y2="{ly}" '
              f'stroke="{cor}" stroke-width="1.5" {da}/>')
    ls.append(f'<text x="{lx+22}" y="{ly+3}" {FONT} font-size="8" '
              f'fill="{CORES["texto"]}">{label}</text>')

ls.extend(svg_fim())
salvar("grafico_balanco_energetico.svg", ls)

# ===========================================================================
# GRÁFICO 3 — Perfil de tensão BT (banda min-max, 24h)
# ===========================================================================
ls = svg_base("Perfil de Tensão BT — 24 horas",
              "Vmin e Vmax dos barramentos BT (Ano 1, LoadMult=1,0)")

ymin, ymax = 0.90, 1.10
grade_h(ls, [0.90,0.921,0.95,1.00,1.05,1.061,1.10], ymin, ymax, "{:.3f}")

# Faixas PRODIST
def faixa(ls, y1, y2, cor, alpha, label=""):
    yp1 = esc_y(y1, ymin, ymax)
    yp2 = esc_y(y2, ymin, ymax)
    h_px = abs(yp1 - yp2)
    ls.append(f'<rect x="{PAD["left"]}" y="{min(yp1,yp2):.1f}" '
              f'width="{PW}" height="{h_px:.1f}" '
              f'fill="{cor}" fill-opacity="{alpha}" stroke="none"/>')
    if label:
        ls.append(f'<text x="{PAD["left"]+PW-2}" y="{min(yp1,yp2)+10:.1f}" '
                  f'text-anchor="end" {FONT} font-size="7" '
                  f'fill="{cor}" fill-opacity="0.8">{label}</text>')

faixa(ls, 0.90,  0.871, "#e74c3c", 0.15, "crítica")
faixa(ls, 0.921, 0.90,  "#e67e22", 0.12, "precária")
faixa(ls, 1.050, 1.061, "#e67e22", 0.12)
faixa(ls, 1.061, 1.10,  "#e74c3c", 0.15)

# Linha adequada inferior e superior
for ylim in [0.921, 1.050]:
    yp = esc_y(ylim, ymin, ymax)
    ls.append(f'<line x1="{PAD["left"]}" y1="{yp:.1f}" '
              f'x2="{PAD["left"]+PW}" y2="{yp:.1f}" '
              f'stroke="#e67e22" stroke-width="0.8" stroke-dasharray="3,2"/>')

# Banda min-max
pts_max = " ".join(f"{esc(h,1,24):.1f},{esc_y(v,ymin,ymax):.1f}"
                   for h, v in zip(horas, perfil_vmax))
pts_min_rev = " ".join(f"{esc(h,1,24):.1f},{esc_y(v,ymin,ymax):.1f}"
                       for h, v in zip(reversed(horas), reversed(perfil_vmin)))
ls.append(f'<polygon points="{pts_max} {pts_min_rev}" '
          f'fill="{CORES["sub"]}" fill-opacity="0.15" stroke="none"/>')

pts_vmax = " ".join(f"{esc(h,1,24):.1f},{esc_y(v,ymin,ymax):.1f}"
                    for h, v in zip(horas, perfil_vmax))
pts_vmin = " ".join(f"{esc(h,1,24):.1f},{esc_y(v,ymin,ymax):.1f}"
                    for h, v in zip(horas, perfil_vmin))
ls.append(f'<polyline points="{pts_vmax}" fill="none" '
          f'stroke="{CORES["ano3"]}" stroke-width="1.2"/>')
ls.append(f'<polyline points="{pts_vmin}" fill="none" '
          f'stroke="{CORES["sub"]}" stroke-width="1.2"/>')

eixo_x_labels(ls,
    [esc(h,1,24) for h in [1,4,7,10,13,16,19,22,24]],
    ["1h","4h","7h","10h","13h","16h","19h","22h","24h"],
    PAD["top"]+PH)
label_eixo(ls, "Hora do dia", "Tensão (pu)")

# Legenda
ls.append(f'<line x1="{PAD["left"]+5}" y1="{PAD["top"]+9}" '
          f'x2="{PAD["left"]+23}" y2="{PAD["top"]+9}" '
          f'stroke="{CORES["ano3"]}" stroke-width="1.2"/>')
ls.append(f'<text x="{PAD["left"]+27}" y="{PAD["top"]+12}" '
          f'{FONT} font-size="8" fill="{CORES["texto"]}">Vmax</text>')
ls.append(f'<line x1="{PAD["left"]+65}" y1="{PAD["top"]+9}" '
          f'x2="{PAD["left"]+83}" y2="{PAD["top"]+9}" '
          f'stroke="{CORES["sub"]}" stroke-width="1.2"/>')
ls.append(f'<text x="{PAD["left"]+87}" y="{PAD["top"]+12}" '
          f'{FONT} font-size="8" fill="{CORES["texto"]}">Vmin</text>')

ls.extend(svg_fim())
salvar("grafico_tensao_bt.svg", ls)

# ===========================================================================
# GRÁFICO 4 — VPL × Taxa de desconto
# ===========================================================================
taxas  = [0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.25, 0.30,
           0.40, 0.50, 0.54]
BEN    = {1: 860.66, 2: 836.44, 3: 733.02}
CAPEX  = config["alternativas"][1]["custo_inicial_usd"]
VU     = 25

def calc_vpl(taxa):
    residual = CAPEX * (VU - 3) / VU
    fs = [-CAPEX, BEN[1], BEN[2], BEN[3] + residual]
    return sum(f/(1+taxa)**t for t, f in enumerate(fs))

vpls = [calc_vpl(t) for t in taxas]

ls = svg_base("Sensibilidade do VPL à Taxa de Desconto",
              "Alternativa: Tap nos dois transformadores")

ymin_v = min(vpls) - 100
ymax_v = max(vpls) + 100
grade_h(ls, [v for v in range(-500, 2500, 500) if ymin_v <= v <= ymax_v], ymin_v, ymax_v)

# Linha VPL=0
y0 = esc_y(0, ymin_v, ymax_v)
ls.append(f'<line x1="{PAD["left"]}" y1="{y0:.1f}" '
          f'x2="{PAD["left"]+PW}" y2="{y0:.1f}" '
          f'stroke="#333" stroke-width="0.8" stroke-dasharray="3,2"/>')

# Ponto TIR (~54%)
tir_idx = taxas.index(0.54)
xtir = esc(taxas[tir_idx]*100, taxas[0]*100, taxas[-1]*100)
ls.append(f'<circle cx="{xtir:.1f}" cy="{y0:.1f}" r="4" '
          f'fill="{CORES["ano3"]}" stroke="white" stroke-width="1"/>')
ls.append(f'<text x="{xtir+6:.1f}" y="{y0-5:.1f}" '
          f'{FONT} font-size="8" fill="{CORES["ano3"]}">TIR≈54%</text>')

# Curva VPL
pts = " ".join(f"{esc(t*100,taxas[0]*100,taxas[-1]*100):.1f},{esc_y(v,ymin_v,ymax_v):.1f}"
               for t, v in zip(taxas, vpls))
ls.append(f'<polyline points="{pts}" fill="none" '
          f'stroke="{CORES["tap"]}" stroke-width="2"/>')

# Marca taxa base 14%
x14 = esc(14, taxas[0]*100, taxas[-1]*100)
v14 = calc_vpl(0.14)
y14 = esc_y(v14, ymin_v, ymax_v)
ls.append(f'<circle cx="{x14:.1f}" cy="{y14:.1f}" r="4" '
          f'fill="{CORES["tap"]}" stroke="white" stroke-width="1"/>')
ls.append(f'<text x="{x14+5:.1f}" y="{y14-5:.1f}" '
          f'{FONT} font-size="8" fill="{CORES["tap"]}">14% → VPL={v14:.0f}</text>')

# Eixo X
eixo_x_labels(ls,
    [esc(t*100, taxas[0]*100, taxas[-1]*100) for t in [0.06,0.10,0.14,0.20,0.30,0.40,0.54]],
    ["6%","10%","14%","20%","30%","40%","54%"],
    PAD["top"]+PH)
label_eixo(ls, "Taxa de desconto (%)", "VPL (USD)")

ls.extend(svg_fim())
salvar("grafico_vpl_sensibilidade.svg", ls)

# ===========================================================================
# GRÁFICO 5 — Curva de duração de carga (trf_6_4910a)
# ===========================================================================
# Dados do 04_pior_caso_duracao_degradacao.py:
# >70%: Ano1=3h/dia, Ano2=5h/dia, Ano3=5h/dia
# >80%: Ano1=3h/dia, Ano2=3h/dia, Ano3=5h/dia
# >90%: Ano1=0,    Ano2=3h/dia, Ano3=3h/dia
# >100%: Ano1=0,  Ano2=0,     Ano3=2h/dia
# Extrapolado para h/ano (×365)

duracao = {
    ">70%":  [3*365, 5*365, 5*365],
    ">80%":  [3*365, 3*365, 5*365],
    ">90%":  [0,     3*365, 3*365],
    ">100%": [0,     0,     2*365],
}

ls = svg_base("Curva de Duração de Carga — trf_6\u20134910a",
              "Horas/ano acima do limiar de carregamento")

n_grupos = 4
n_barras = 3
bw       = PW / (n_grupos * (n_barras + 1))  # largura de cada barra
ymin_d, ymax_d = 0, 2000

grade_h(ls, [500, 1000, 1500], ymin_d, ymax_d)

cores_anos = [CORES["ano1"], CORES["ano2"], CORES["ano3"]]

for gi, (limiar, vals) in enumerate(duracao.items()):
    grupo_x = PAD["left"] + gi * (n_barras + 1) * bw + bw/2
    # Label do grupo
    lx = grupo_x + (n_barras/2) * bw
    ls.append(f'<text x="{lx:.1f}" y="{PAD["top"]+PH+10}" '
              f'text-anchor="middle" {FONT} font-size="8" fill="#555">{limiar}</text>')

    for ai, (v, cor) in enumerate(zip(vals, cores_anos)):
        bx = grupo_x + ai * bw
        bh = (v / ymax_d) * PH
        by = PAD["top"] + PH - bh
        ls.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw*0.85:.1f}" '
                  f'height="{bh:.1f}" fill="{cor}" fill-opacity="0.85" rx="1"/>')
        if v > 0:
            ls.append(f'<text x="{bx+bw*0.42:.1f}" y="{by-2:.1f}" '
                      f'text-anchor="middle" {FONT} font-size="7" '
                      f'fill="{cor}">{v}</text>')

label_eixo(ls, "Limiar de carregamento", "Horas/ano")

# Legenda
for i, (cor, label) in enumerate(zip(cores_anos, ["Ano 1","Ano 2","Ano 3"])):
    lx = PAD["left"] + 10 + i*80
    ly = PAD["top"] + 8
    ls.append(f'<rect x="{lx}" y="{ly-6}" width="14" height="8" '
              f'fill="{cor}" fill-opacity="0.85" rx="1"/>')
    ls.append(f'<text x="{lx+18}" y="{ly+1}" {FONT} font-size="8" '
              f'fill="{CORES["texto"]}">{label}</text>')

ls.extend(svg_fim())
salvar("grafico_duracao_carga.svg", ls)

# ===========================================================================
# GRÁFICO 6 — Ranking PVSystems (Vmax por barramento)
# ===========================================================================
pv_ranking = [
    ("gd.rs.000.912.708",  5,  0.9954),
    ("gd.rs.001.590.899", 18,  0.9959),
    ("gd.rs.000.622.799", 54,  0.9968),
    ("gd.rs.000.197.382", 50,  0.9966),
    ("gd.rs.001.255.347", 54,  0.9966),
    ("gd.rs.001.864.524", 51,  0.9944),
    ("gd.rs.001.922.364", 60,  0.9961),
    ("gd.rs.001.813.569", 11,  1.0023),
    ("gd.rs.002.201.608",  8,  1.0044),
    ("gd.rs.001.813.585",  6,  1.0070),
    ("gd.rs.000.097.832",  8,  1.0074),
    ("gd.rs.000.966.424",  5,  1.0114),
    ("gd.rs.000.818.905",  6,  1.0064),
    ("gd.rs.001.817.303", 15,  1.0140),
    ("gd.rs.001.522.672", 20,  1.0145),
    ("gd.rs.002.132.491",  8,  1.0190),
    ("gd.rs.001.675.278", 12,  1.0170),
    ("gd.rs.001.813.605", 18,  1.0185),
    ("gd.rs.001.593.160",  5,  1.0233),
    ("gd.rs.001.590.890",  8,  1.0234),
    ("gd.rs.000.859.130",  6,  1.0345),
    ("gd.rs.000.371.786", 15,  1.0545),
    ("gd.rs.001.675.269", 75,  1.0789),
]
# Ordena por Vmax crescente (melhor → pior)
pv_ranking.sort(key=lambda x: x[2])

# Gráfico horizontal com altura maior
W2, H2 = 400, 380
PH2 = H2 - PAD["top"] - PAD["bottom"] - 10
bh2 = PH2 / len(pv_ranking) * 0.75

ls = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W2}" height="{H2}" '
    f'viewBox="0 0 {W2} {H2}" style="background:white">',
    f'<text x="{W2//2}" y="18" text-anchor="middle" {FONT} '
    f'font-size="11" font-weight="bold" fill="{CORES["texto"]}">'
    f'Ranking PVSystems — Tensão Máxima</text>',
    f'<text x="{W2//2}" y="28" text-anchor="middle" {FONT} '
    f'font-size="8" fill="#666">Ano 1, hora de pico solar (LoadMult=1,0)</text>',
]

xmin_r, xmax_r = 0.980, 1.085
PW2 = W2 - PAD["left"] - 20

def escx(v): return PAD["left"] + (v-xmin_r)/(xmax_r-xmin_r)*PW2

# Grades verticais
for xv in [0.980, 0.990, 1.000, 1.010, 1.020, 1.030, 1.040, 1.050, 1.060, 1.070, 1.080]:
    xp = escx(xv)
    ls.append(f'<line x1="{xp:.1f}" y1="{PAD["top"]}" '
              f'x2="{xp:.1f}" y2="{PAD["top"]+PH2}" '
              f'stroke="{CORES["grade"]}" stroke-width="0.8"/>')
    ls.append(f'<text x="{xp:.1f}" y="{PAD["top"]+PH2+10}" '
              f'text-anchor="middle" {FONT} font-size="7" fill="#666">'
              f'{xv:.3f}</text>')

# Limites PRODIST
for xv, cor, label in [(1.050, "#e67e22", "precária"), (1.061, "#e74c3c", "crítica")]:
    xp = escx(xv)
    ls.append(f'<line x1="{xp:.1f}" y1="{PAD["top"]}" '
              f'x2="{xp:.1f}" y2="{PAD["top"]+PH2}" '
              f'stroke="{cor}" stroke-width="1" stroke-dasharray="3,2"/>')
    ls.append(f'<text x="{xp+2:.1f}" y="{PAD["top"]+8}" '
              f'{FONT} font-size="7" fill="{cor}">{label}</text>')

# Barras
for i, (nome, pmpp, vmax) in enumerate(pv_ranking):
    y_bar = PAD["top"] + i * (PH2/len(pv_ranking)) + 2
    cor = ("#e74c3c" if vmax > 1.061 else
           "#e67e22" if vmax > 1.050 else
           "#27ae60" if vmax < 1.000 else "#3498db")
    xb = escx(xmin_r)
    wb = escx(vmax) - xb
    ls.append(f'<rect x="{xb:.1f}" y="{y_bar:.1f}" width="{wb:.1f}" '
              f'height="{bh2:.1f}" fill="{cor}" fill-opacity="0.8" rx="1"/>')
    # Nome curto
    nome_curto = nome.replace("gd.rs.", "")
    ls.append(f'<text x="{xb-2:.1f}" y="{y_bar+bh2*0.75:.1f}" '
              f'text-anchor="end" {FONT} font-size="6.5" fill="#333">{nome_curto}</text>')
    # Pmpp
    ls.append(f'<text x="{escx(vmax)+3:.1f}" y="{y_bar+bh2*0.75:.1f}" '
              f'{FONT} font-size="6.5" fill="{cor}">{pmpp}kW</text>')

ls.append(f'<text x="{PAD["left"]+PW2//2}" y="{H2-5}" '
          f'text-anchor="middle" {FONT} font-size="9" fill="#444">Tensão máxima (pu)</text>')
ls.append('</svg>')
salvar("grafico_ranking_pvsystems.svg", ls)

print("\nTodos os gráficos gerados.")
