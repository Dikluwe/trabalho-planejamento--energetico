# Crystalline Lineage
# @layer L1
# @updated 2026-04-05

"""
Centralização de parâmetros e caminhos conforme sugestão técnica.
Evita repetição de código (boilerplate) em todos os scripts de análise.
"""

import sys
import json
from pathlib import Path

# Garante que a raiz do projeto está no path para que o pacote fase_00 seja importável
HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Carregamento centralizado do JSON
CONFIG_FILE = HERE / "parametros.json"
if not CONFIG_FILE.exists():
    # Se não achar na raiz (fallback para execução direta dentro da pasta)
    CONFIG_FILE = HERE / "fase_00" / "parametros.json"

try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
except Exception as e:
    print(f"ERRO CRÍTICO: Falha ao carregar {CONFIG_FILE}: {e}")
    sys.exit(1)

# Constantes globais de caminhos
MASTER_DSS = str(HERE / config["caminhos"]["dss_file"])
RESULTADOS_DIR = HERE / "Resultados"
RESULTADOS_DIR.mkdir(exist_ok=True)

# Parâmetros técnicos frequentes
TRAFO_CRITICO = config["graficos"]["trafo_critico"]
CRESCIMENTO = config["simulacao"]["crescimento_carga"]
LIMITE_MIN_PU = config["tecnico"]["limite_min_pu"]
LIMITE_MAX_PU = config["tecnico"]["limite_max_pu"]

# Parâmetros econômicos
ECONOMICO = config["economico"]
TAXA_DESCONTO = ECONOMICO["taxa_desconto"]
TARIFA_VENDA = ECONOMICO["tarifa_venda_usd_mwh"]
PRECO_COMPRA = ECONOMICO["preco_compra_usd_mwh"]

# Utilitário para garantir que o OpenDSS está pronto
def inicializar_dss(dss, master=MASTER_DSS):
    """Inicializa o circuito OpenDSS com os parâmetros padrão."""
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{master}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    return dss.ActiveCircuit

def calcular_potencia_aparente(circuit, nome_elemento, tipo_elemento="Transformer"):
    """Calcula a potência aparente (S) em kVA e o carregamento."""
    circuit.SetActiveElement(f"{tipo_elemento}.{nome_elemento}")
    pw = circuit.ActiveCktElement.Powers
    n = circuit.ActiveCktElement.NumPhases
    
    if len(pw) < n * 2:
        return 0.0
        
    p = sum(pw[0:n*2:2])
    q = sum(pw[1:n*2+1:2])
    return (p**2 + q**2)**0.5

