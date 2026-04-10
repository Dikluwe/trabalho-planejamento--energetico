import importlib
import sys
import networkx as nx
from pathlib import Path
HERE = Path('.').resolve()
sys.path.insert(0, str(HERE))

from core import configuracao
from dss import dss

def diagnose_connectivity():
    dss.Text.Command = f"Compile [{configuracao.MASTER_DSS}]"
    
    G = nx.DiGraph()
    tipos = {}
    niveis = {}
    
    # 1. Extração de Conexões (Linhas)
    dss.ActiveCircuit.Lines.First
    while True:
        b1 = dss.ActiveCircuit.Lines.Bus1.split('.')[0].lower()
        b2 = dss.ActiveCircuit.Lines.Bus2.split('.')[0].lower()
        G.add_edge(b1, b2)
        if not dss.ActiveCircuit.Lines.Next > 0: break

    # 2. Extração de Transformadores (Connect MT -> BT)
    dss.ActiveCircuit.Transformers.First
    while True:
        b = dss.ActiveCircuit.ActiveCktElement.BusNames
        # Connect primary to all other windings
        b0 = b[0].split('.')[0].lower()
        for i in range(1, len(b)):
            bi = b[i].split('.')[0].lower()
            G.add_edge(b0, bi)
        if not dss.ActiveCircuit.Transformers.Next > 0: break

    # 3. Identificar Níveis
    for n in G.nodes:
        dss.ActiveCircuit.SetActiveBus(n)
        niveis[n] = 'mt' if dss.ActiveCircuit.ActiveBus.kVBase > 1.0 else 'bt'

    subestacao = "1_rede2_1"
    arvore = nx.bfs_tree(G, source=subestacao)
    
    print(f"Nodes in G: {len(G.nodes)}")
    print(f"Nodes in Arvore: {len(arvore.nodes)}")
    
    bt_nodes_g = [n for n in G.nodes if niveis.get(n) == 'bt']
    bt_nodes_tree = [n for n in arvore.nodes if niveis.get(n) == 'bt']
    
    print(f"BT Nodes in G: {len(bt_nodes_g)}")
    print(f"BT Nodes in Arvore: {len(bt_nodes_tree)}")
    
    if len(bt_nodes_g) > len(bt_nodes_tree):
        missing = set(bt_nodes_g) - set(bt_nodes_tree)
        print(f"Sample Missing BT Nodes: {list(missing)[:5]}")
        # Check if missing nodes have predecessors in G
        m0 = list(missing)[0]
        preds = list(G.predecessors(m0))
        print(f"Predecessors of {m0} in G: {preds}")

if __name__ == "__main__":
    diagnose_connectivity()
