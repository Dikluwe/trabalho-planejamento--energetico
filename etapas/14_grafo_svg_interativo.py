import sys
import importlib
import svgwrite
import networkx as nx
from pathlib import Path
from networkx.drawing.nx_pydot import graphviz_layout

# Configuração de caminhos do projeto
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import configuracao

# Carregamento dinâmico do script 12 para reaproveitar a extração técnica
try:
    visualizar_grafo = importlib.import_module("etapas.12_visualizar_grafo_hierarquico")
    gerar_arvore_com_ativos = visualizar_grafo.gerar_arvore_com_ativos
except ImportError:
    print("Erro: Não foi possível importar o script 12.")
    sys.exit(1)

def exportar_svg_high_performance():
    print(">>> Extraindo ativos e calculando layout hierárquico (Graphviz)...")
    arvore = gerar_arvore_com_ativos()
    
    # 1. Calcular Coordenadas (Layout)
    try:
        pos = graphviz_layout(arvore, prog='dot')
    except Exception as e:
        print(f"Erro ao calcular layout: {e}. Usando layout alternativo.")
        pos = nx.spring_layout(arvore)

    # 2. Normalização de Coordenadas
    x_coords = [p[0] for p in pos.values()]
    y_coords = [p[1] for p in pos.values()]
    min_x, max_x = min(x_coords), max(x_coords)
    min_y, max_y = min(y_coords), max(y_coords)
    
    width, height = 2100, 8100
    def scale(p):
        sx = (p[0] - min_x) / (max_x - min_x + 1) * 2000 + 50
        sy = height - ((p[1] - min_y) / (max_y - min_y + 1) * 8000 + 50)
        return sx, sy

    # 3. Inicializar Documento SVG
    caminho_svg = configuracao.RESULTADOS_DIR / "mapa_ativos_camadas.svg"
    dwg = svgwrite.Drawing(str(caminho_svg), profile='full', size=(width, height))

    # Injeção de CSS Corrigida (Interatividade e Contraste)
    dwg.defs.add(dwg.style("""
        .nome-ativo { 
            display: none; 
            font-family: sans-serif; 
            font-size: 14px; 
            fill: #ffffff; 
            font-weight: bold;
            pointer-events: none;
        }
        .bg-texto { 
            display: none; 
            fill: #000000; 
            fill-opacity: 0.8; 
            pointer-events: none;
        }
        .no-grupo:hover .nome-ativo, 
        .no-grupo:hover .bg-texto { 
            display: inline; 
        }
        .no-grupo:hover circle, .no-grupo:hover text.simbolo-chave { 
            stroke: #ffffff; 
            stroke-width: 2px; 
        }
        .btn-toggle { cursor: pointer; }
        .layer-off { opacity: 0.2 !important; text-decoration: line-through; }
    """))

    # Criando Camadas
    layer_mt_e = dwg.add(dwg.g(id='layer_mt_edges', stroke='#555555', stroke_opacity=0.4))
    layer_bt_e = dwg.add(dwg.g(id='layer_bt_edges', stroke='#88aadd', stroke_opacity=0.5))
    layer_chaves = dwg.add(dwg.g(id='layer_chaves'))
    
    # Garanta que todos os IDs de camadas existam para evitar KeyError
    layers_ativos = {
        'subestacao':   dwg.add(dwg.g(id='layer_subestacao')),
        'transformador':dwg.add(dwg.g(id='layer_transformador')),
        'gd':           dwg.add(dwg.g(id='layer_gd')),
        'capacitor':    dwg.add(dwg.g(id='layer_capacitor')),
        'carga':        dwg.add(dwg.g(id='layer_carga')), # A chave que faltava
        'default':      dwg.add(dwg.g(id='layer_default'))
    }

    # 4. Desenhar Arestas e Chaves
    for u, v, d in arvore.edges(data=True):
        p1, p2 = scale(pos[u]), scale(pos[v])
        
        # Identifica se é MT ou BT pelo nome do barramento
        is_mt = not (u.startswith('bt') or v.startswith('bt'))
        target_g = layer_mt_e if is_mt else layer_bt_e
        target_g.add(dwg.line(p1, p2, stroke_width=2))
        
        # Se for uma chave (detectado no script 12 ou por convenção de nome)
        if d.get('is_switch') or 'sw' in u or 'ch' in u:
            pm = ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2)
            g_sw = layer_chaves.add(dwg.g(class_='no-grupo'))
            g_sw.add(dwg.text('X', insert=(pm[0]-8, pm[1]+8), font_size=22, font_weight='bold', fill='yellow', class_='simbolo-chave'))
            
            nome_sw = f"Chave: {u}->{v}"
            g_sw.add(dwg.rect(insert=(pm[0]+12, pm[1]-15), size=(len(nome_sw)*9, 20), rx=5, class_='bg-texto'))
            g_sw.add(dwg.text(nome_sw, insert=(pm[0]+15, pm[1]), class_='nome-ativo'))

    # 5. Desenhar Nós (Ativos e de Passagem)
    estilos = {
        'subestacao':   {'color': 'red',       'size': 18, 'label': 'Subestação'},
        'transformador':{'color': 'orange',    'size': 10, 'label': 'Transformadores'},
        'gd':           {'color': 'limegreen', 'size': 12, 'label': 'Geração (PV)'},
        'capacitor':    {'color': 'hotpink',   'size': 12, 'label': 'Capacitores'},
        'carga':        {'color': 'royalblue', 'size': 6,  'label': 'Consumidores (BT)'},
        'default':      {'color': 'teal',      'size': 4,  'label': 'Nós de Passagem'}
    }

    for n, attr in arvore.nodes(data=True):
        tipo = attr.get('tipo', 'default')
        # Fallback de segurança: se o tipo não existir nas camadas, joga no default
        if tipo not in layers_ativos:
            tipo = 'default'
            
        p = scale(pos[n])
        cfg = estilos.get(tipo, estilos['default'])
        
        # Grupo para o nó (ícone + texto hover)
        g_no = layers_ativos[tipo].add(dwg.g(class_='no-grupo'))
        g_no.add(dwg.circle(center=p, r=cfg['size'], fill=cfg['color']))
        
        # Nomeação Interativa (Hover)
        if tipo != 'default':
            nome_node = str(n)
            largura_box = len(nome_node) * 10
            
            # Retângulo de fundo (Contraste)
            g_no.add(dwg.rect(insert=(p[0]+12, p[1]-15), 
                              size=(largura_box, 20), 
                              rx=5, ry=5, 
                              class_='bg-texto'))
            
            # Texto do Nome (Z-index superior dentro do grupo)
            g_no.add(dwg.text(nome_node, insert=(p[0]+15, p[1]), class_='nome-ativo'))

    # 6. Construir Legenda Interativa Manual
    # Centralizado horizontalmente: (2100 / 2) - (280 / 2) = 910
    leg_x, leg_y = 910, 50
    dwg.add(dwg.rect(insert=(leg_x-10, leg_y-10), size=(280, 320), fill='#222222', opacity=0.8, rx=10))
    dwg.add(dwg.text("CONTROLE DE CAMADAS", insert=(leg_x+20, leg_y+20), fill='white', font_size=18, font_weight='bold'))
    
    categorias = [
        ('mt', 'Rede: Média Tensão', '#555555'),
        ('bt', 'Rede: Baixa Tensão', '#88aadd'),
        ('chaves', 'Equip: Chaves (X)', 'black'),
        ('subestacao', estilos['subestacao']['label'], estilos['subestacao']['color']),
        ('transformador', estilos['transformador']['label'], estilos['transformador']['color']),
        ('gd', estilos['gd']['label'], estilos['gd']['color']),
        ('capacitor', estilos['capacitor']['label'], estilos['capacitor']['color']),
        ('carga', estilos['carga']['label'], estilos['carga']['color']),
        ('default', estilos['default']['label'], estilos['default']['color']),
    ]

    for i, (cat_id, label, cor) in enumerate(categorias):
        yy = leg_y + 60 + (i * 30)
        btn = dwg.add(dwg.g(id=f"btn_{cat_id}", class_='btn-toggle', onclick=f"toggleLayer('{cat_id}')"))
        btn.add(dwg.circle(center=(leg_x+20, yy-5), r=8, fill=cor))
        btn.add(dwg.text(label, insert=(leg_x+40, yy), fill='white', font_size=16))

    # 7. JavaScript e Finalização
    js = """
    function toggleLayer(tipo) {
        var id = (tipo === 'mt' || tipo === 'bt') ? 'layer_' + tipo + '_edges' : 'layer_' + tipo;
        var el = document.getElementById(id);
        if (el) {
            el.style.display = (el.style.display === 'none') ? 'inline' : 'none';
        }
        var btn = document.getElementById("btn_" + tipo);
        if (btn) btn.classList.toggle('layer-off');
    }
    """
    dwg.defs.add(dwg.script(content=js))
    dwg.save()
    print(f"\n>>> Mapa Final Gerado: {caminho_svg}")

if __name__ == "__main__":
    exportar_svg_high_performance()