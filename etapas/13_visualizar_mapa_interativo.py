import sys
import json
import importlib
from pathlib import Path
from pyvis.network import Network

# Configuração de caminhos para encontrar o 'core' e 'etapas'
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import configuracao
# Carregamento dinâmico para contornar nomes de arquivos que iniciam com números
visualizar_grafo = importlib.import_module("etapas.12_visualizar_grafo_hierarquico")
gerar_arvore_com_ativos = visualizar_grafo.gerar_arvore_com_ativos

def gerar_mapa_html():
    print(">>> Extraindo ativos e gerando estrutura para o Pyvis...")
    # Reaproveita a lógica de extração técnica do Script 12
    arvore = gerar_arvore_com_ativos()
    
    # Inicializa a rede Pyvis
    net = Network(height="1000px", width="100%", bgcolor="#222222", font_color="white", directed=True)
    
    # Mapeamento de Cores para o Pyvis (padrão Hexadecimal)
    cores = {
        'subestacao':   '#ff0000', # Vermelho
        'transformador':'#ffa500', # Laranja
        'gd':           '#32cd32', # Verde (LimeGreen)
        'capacitor':    '#ff69b4', # Rosa (HotPink)
        'carga':        '#4169e1', # Azul (RoyalBlue)
        'default':      '#008080'  # Teal
    }

    # Adicionando nós com metadados
    for n, attr in arvore.nodes(data=True):
        tipo = attr.get('tipo', 'default')
        # Garante que temos uma cor definida para o tipo, senão usa default
        cor = cores.get(tipo, cores['default'])
        
        net.add_node(n, 
                     label=n if tipo != 'default' else "", # Mostra nome apenas em equipamentos
                     title=f"Barramento: {n}\nTipo: {tipo.upper()}", # Tooltip ao passar o mouse
                     color=cor,
                     size=30 if tipo != 'default' else 10,
                     shape="star" if tipo == 'subestacao' else ("square" if tipo == 'transformador' else "dot"))

    # Adicionando arestas
    for u, v in arvore.edges():
        net.add_edge(u, v, color="gray", alpha=0.5)

    # Configuração de Layout Hierárquico e Física
    # Incluímos o menu de configuração diretamente nas opções
    options = {
        "configure": {
            "enabled": True,
            "filter": ["nodes", "selection"]
        },
        "layout": {
            "hierarchical": {
                "enabled": True,
                "levelSeparation": 150,
                "nodeSpacing": 100,
                "treeSpacing": 200,
                "blockShifting": True,
                "edgeMinimization": True,
                "parentCentralization": True,
                "direction": "UD",
                "sortMethod": "directed"
            }
        },
        "interaction": {
            "navigationButtons": True,
            "hover": True,
            "tooltipDelay": 200
        },
        "physics": {
            "enabled": True,
            "hierarchicalRepulsion": {
                "centralGravity": 0,
                "springLength": 100,
                "springConstant": 0.01,
                "nodeDistance": 120,
                "damping": 0.09
            },
            "solver": "hierarchicalRepulsion",
            "stabilization": {
                "enabled": True,
                "iterations": 500,
                "updateInterval": 50
            }
        }
    }
    
    net.set_options(json.dumps(options))
    
    caminho_saida = configuracao.RESULTADOS_DIR / "mapa_interativo_ativos.html"
    net.save_graph(str(caminho_saida))
    print(f"\n>>> Mapa interativo gerado com sucesso: {caminho_saida}")
    print(">>> Dica: Use o menu 'selection' no rodapé do HTML para buscar barramentos específicos.")

if __name__ == "__main__":
    gerar_mapa_html()
