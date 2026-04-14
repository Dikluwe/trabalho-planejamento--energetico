import sys
import networkx as nx
import matplotlib.pyplot as plt
from pathlib import Path
from networkx.drawing.nx_pydot import graphviz_layout

# Configuração de caminhos do projeto
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import configuracao

# --- CONFIGURAÇÃO DE VISIBILIDADE (TOGGLES) ---
EXIBIR_GD = True
EXIBIR_CARGAS = False      # Desligado por padrão para reduzir poluição
EXIBIR_CAPACITORES = True
# ----------------------------------------------

def gerar_arvore_com_ativos():
    from dss import dss
    dss.Text.Command = "Clear"
    dss.Text.Command = f"Compile [{configuracao.MASTER_DSS}]"

    G = nx.Graph() # Grafo não-direcionado para suportar definições de linhas em qualquer ordem
    tipos = {} # Mapeamento {nó: tipo}
    niveis = {} # Mapeamento {nó: 'mt' ou 'bt'}
    subestacao = "1_rede2_1"

    # 1. Extração de Conexões (Linhas e Transformadores)
    dss.ActiveCircuit.Lines.First
    while True:
        b1 = dss.ActiveCircuit.Lines.Bus1.split('.')[0].lower()
        b2 = dss.ActiveCircuit.Lines.Bus2.split('.')[0].lower()
        # No grafo não-direcionado, preservamos se é chave (is_switch)
        # Se uma linha aparecer duas vezes (raro), o is_switch prevalece se algum for True
        is_sw = dss.ActiveCircuit.Lines.IsSwitch
        nome_ln = dss.ActiveCircuit.Lines.Name.lower()
        if G.has_edge(b1, b2):
            is_sw = is_sw or G[b1][b2].get('is_switch', False)
        G.add_edge(b1, b2, is_switch=is_sw, name=nome_ln)
        if not dss.ActiveCircuit.Lines.Next > 0: break

    # Extrai transformadores (Conecta todos os enrolamentos ao primário)
    dss.ActiveCircuit.Transformers.First
    while True:
        nome_trf = dss.ActiveCircuit.Transformers.Name.lower()
        b = dss.ActiveCircuit.ActiveCktElement.BusNames
        if len(b) >= 2:
            bus0 = b[0].split('.')[0].lower()
            for i in range(1, len(b)):
                bus_i = b[i].split('.')[0].lower()
                G.add_edge(bus0, bus_i, is_switch=False, name=nome_trf)
                # O segundo barramento (enrolamento 2) marca o início do transformador nos ativos
                if i == 1: 
                    tipos[bus_i] = 'transformador'
                    G.nodes[bus_i]['equip_name'] = nome_trf
        if not dss.ActiveCircuit.Transformers.Next > 0: break

    # 2. Coleta de Metadados de Equipamentos e Níveis de Tensão
    for node in G.nodes:
        dss.ActiveCircuit.SetActiveBus(node)
        base_kv = dss.ActiveCircuit.ActiveBus.kVBase
        niveis[node] = 'mt' if base_kv > 1.0 else 'bt'

    # PVSystems
    dss.ActiveCircuit.PVSystems.First
    while dss.ActiveCircuit.PVSystems.Count > 0:
        bus = dss.ActiveCircuit.ActiveCktElement.BusNames[0].split('.')[0].lower()
        if bus not in tipos: tipos[bus] = 'gd'
        if not dss.ActiveCircuit.PVSystems.Next > 0: break

    # Capacitores
    dss.ActiveCircuit.Capacitors.First
    while dss.ActiveCircuit.Capacitors.Count > 0:
        bus = dss.ActiveCircuit.ActiveCktElement.BusNames[0].split('.')[0].lower()
        if bus not in tipos: tipos[bus] = 'capacitor'
        if not dss.ActiveCircuit.Capacitors.Next > 0: break

    # Cargas (Loads)
    dss.ActiveCircuit.Loads.First
    while dss.ActiveCircuit.Loads.Count > 0:
        bus = dss.ActiveCircuit.ActiveCktElement.BusNames[0].split('.')[0].lower()
        if bus not in tipos: tipos[bus] = 'carga'
        if not dss.ActiveCircuit.Loads.Next > 0: break

    tipos[subestacao] = 'subestacao'
    
    # Criar árvore direcionada real eliminando loops eventuais
    arvore = nx.bfs_tree(G, source=subestacao)
    
    # Re-atribuir atributos
    nx.set_node_attributes(arvore, tipos, "tipo")
    nx.set_node_attributes(arvore, niveis, "nivel")
    
    for u, v in arvore.edges():
        for attr_k, attr_v in G[u][v].items():
            arvore[u][v][attr_k] = attr_v
        # Nível da aresta (MT se o nó de origem for MT)
        arvore[u][v]['nivel'] = niveis.get(u, 'bt')
    
    return arvore

def plotar_arvore_estilizada(G, nome_arquivo, titulo, height=40):
    plt.figure(figsize=(20, height))
    
    # O segredo da visualização em árvore: layout 'dot'
    try:
        pos = graphviz_layout(G, prog='dot')
    except Exception as e:
        print(f"Aviso: Graphviz falhou ({e}). Usando layout planar.")
        pos = nx.planar_layout(G)

    # Definição de Estilos e Símbolos
    # 's' square, 'd' diamond, 'h' hexagon, '*' star, '^' triangle, '.' point
    estilos = {
        'subestacao':   {'node_color': 'red',       'node_shape': '*', 'node_size': 500, 'label': 'Subestação',   'active': True},
        'transformador':{'node_color': 'orange',    'node_shape': 's', 'node_size': 120, 'label': 'Transformador', 'active': True},
        'gd':           {'node_color': 'limegreen', 'node_shape': 'd', 'node_size': 180, 'label': 'Geração (PV)',  'active': EXIBIR_GD},
        'capacitor':    {'node_color': 'hotpink',   'node_shape': 'h', 'node_size': 180, 'label': 'Capacitor',     'active': EXIBIR_CAPACITORES},
        'carga':        {'node_color': 'royalblue', 'node_shape': '^', 'node_size': 100, 'label': 'Carga (UC)',    'active': EXIBIR_CARGAS},
        'default':      {'node_color': 'teal',      'node_shape': '.', 'node_size': 10,  'label': 'Nó de Passagem', 'active': True}
    }

    # Desenhar Arestas (o esqueleto da rede)
    nx.draw_networkx_edges(G, pos, alpha=0.3, edge_color='gray', arrows=False)

    # Coleta de nós por categoria para desenho otimizado
    for tipo, config in estilos.items():
        if not config['active']:
            # Se o equipamento está desligado, os nós voltam ao estilo default (nó de passagem)
            continue
            
        nos_categoria = [n for n, attr in G.nodes(data=True) if attr.get('tipo', 'default') == tipo]
        
        # Caso especial para o estilo 'default': inclui nós sem categoria e nós de equipamentos desativados
        if tipo == 'default':
            mais_nos = [n for n, attr in G.nodes(data=True) if attr.get('tipo', 'default') not in estilos or not estilos.get(attr.get('tipo', 'default'))['active']]
            nos_categoria.extend(mais_nos)

        if nos_categoria:
            nx.draw_networkx_nodes(G, pos, nodelist=nos_categoria, 
                                   node_color=config['node_color'], 
                                   node_shape=config['node_shape'], 
                                   node_size=config['node_size'], 
                                   label=config['label'],
                                   alpha=0.8)

    plt.title(titulo, fontsize=16)
    plt.legend(scatterpoints=1, loc='upper right', fontsize=12)
    plt.axis('off')
    
    caminho = configuracao.RESULTADOS_DIR / nome_arquivo
    plt.savefig(caminho, dpi=300, bbox_inches='tight')
    print(f">>> Árvore salva em: {caminho}")
    plt.close()

if __name__ == "__main__":
    print(">>> Extraindo árvore hierárquica e ativos da rede...")
    rede = gerar_arvore_com_ativos()
    
    # Gerar visualização completa (MT + BT)
    plotar_arvore_estilizada(rede, "arvore_estilizada_completa.png", 
                             "Mapa de Ativos - Topologia Hierárquica Rural", height=80)
    
    # Gerar visualização Média Tensão (MT)
    nos_mt = [n for n in rede.nodes if not n.startswith('bt') and not n.startswith('uc')]
    sub_mt = rede.subgraph(nos_mt)
    plotar_arvore_estilizada(sub_mt, "arvore_estilizada_mt.png", 
                             "Mapa de Ativos - Tronco de Média Tensão", height=40)
