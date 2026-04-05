# horizonte_tap.py
# Determina em qual ano o trf_6_4910a ultrapassa 100% de carregamento
# com e sem ajuste de tap, crescimento de 10% ao ano

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import Main as professor
from dss import dss

import json
with open(HERE / "parametros.json", "r") as f:
    config = json.load(f)

MASTER     = str(HERE / config["caminhos"]["dss_file"])
TRAFO_ALVO = config["graficos"]["trafo_critico"]
CRESCIMENTO = config["simulacao"]["crescimento_carga"]
LIMITE_PCT  = 100.0
ANOS_MAX    = 20

def rodar_ano(fator: float, comandos: list[str]) -> float:
    """Retorna o carregamento máximo do trafo alvo para um dado fator de carga."""
    # Redireciona e limpa, mais rapido que a função do professor
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{MASTER}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    
    # Restaura variaveis de ambiente equivalentes
    dss.Text.Command = f"Set LoadMult={fator}"
    for cmd in comandos:
        dss.Text.Command = cmd
        
    circuit = dss.ActiveCircuit
    
    # Para ser coerente com InitializeCircuit do professor
    circuit.SetActiveClass("PVSystem")
    idx = circuit.ActiveClass.First
    while idx > 0:
        nome = circuit.ActiveCktElement.Name.split(".")[1]
        dss.Text.Command = f"Edit PVSystem.{nome} irradiance=1.0"
        idx = circuit.ActiveClass.Next

    circuit.SetActiveElement(f"Transformer.{TRAFO_ALVO}")
    kva = circuit.ActiveCktElement.Properties("kVA").Val
    try:
        kva = float(kva)
    except:
        kva = 30.0

    pmax = 0.0
    for h in range(24):
        circuit.Solution.Solve()
        circuit.SetActiveElement(f"Transformer.{TRAFO_ALVO}")
        powers = circuit.ActiveCktElement.Powers
        n = circuit.ActiveCktElement.NumPhases
        if len(powers) >= n * 2 and kva > 0:
            p = sum(powers[0:n*2:2])
            q = sum(powers[1:n*2+1:2])
            s = (p**2 + q**2)**0.5
            pmax = max(pmax, 100 * s / kva)
            
    return pmax


# Derivações possíveis: até 5 de 600V em 23,1kV
# tap_sec = 1.0 - (n_deriv * 600/23100)
# Tap no primário (wdg=1): aumenta a relação → reduz corrente no primário
# Cada derivação de 600V em 23,1kV = 600/23100 = 0,02597
# Cada derivação = 600V / 23100V = 0,02597 pu (PRODIST/enunciado)
derivacoes = {
    0: 1.0000,   # nominal
    1: 1.0260,   # +1 derivação (600V/23100V)
    2: 1.0519,   # +2 derivações
    3: 1.0779,   # +3 derivações
    4: 1.1039,   # +4 derivações
    5: 1.1299,   # +5 derivações (máximo)
}

# Calcula carregamentos para cada configuração por ano
resultados = {}  # {deriv: {ano: carg}}
for deriv, tap in derivacoes.items():
    resultados[deriv] = {}
    for ano in range(1, ANOS_MAX + 1):
        fator = 1.0 + CRESCIMENTO * (ano - 1)
        if deriv == 0:
            cmds = []
        else:
            cmds = [f"Edit Transformer.{TRAFO_ALVO} wdg=1 tap={tap}"]
        resultados[deriv][ano] = rodar_ano(fator, cmds)

# Cabeçalho
print(f"\n{'='*80}")
print(f"[02.03] ANÁLISE DE HORIZONTE — {TRAFO_ALVO.upper()}")
print(f"Crescimento: {CRESCIMENTO*100:.0f}% ao ano | Limite: {LIMITE_PCT}%")
print(f"{'='*80}")
header = f"  {'Ano':>3}  {'Fator':>5}"
for d in derivacoes:
    header += f"  {'Der'+str(d):>10}"
print(header)
print(f"  {'-'*75}")

anos_limite = {}  # {deriv: primeiro ano de sobrecarga}
for ano in range(1, ANOS_MAX + 1):
    fator = 1.0 + CRESCIMENTO * (ano - 1)
    linha = f"  {ano:>3}  {fator:>5.2f}"
    tem_sobrecarga = False
    for d in derivacoes:
        c = resultados[d][ano]
        flag = "*" if c > LIMITE_PCT else " "
        linha += f"  {c:>8.2f}%{flag}"
        if c > LIMITE_PCT and d not in anos_limite:
            anos_limite[d] = ano
        if c > LIMITE_PCT:
            tem_sobrecarga = True
    print(linha)
    # Para 3 anos após todos atingirem sobrecarga
    if len(anos_limite) == len(derivacoes) and ano > max(anos_limite.values()) + 2:
        break

print(f"\n{'='*80}")
print("CONCLUSÃO POR DERIVAÇÃO:")
for d, tap in derivacoes.items():
    if d in anos_limite:
        ano_s = anos_limite[d]
        fator_s = 1.0 + CRESCIMENTO * (ano_s - 1)
        ganho = ano_s - anos_limite.get(0, ano_s)
        print(f"  Derivação {d} (tap={tap:.4f}): sobrecarga no Ano {ano_s} (fator {fator_s:.2f}) | ganho: {ganho:+d} ano(s)")
    else:
        print(f"  Derivação {d} (tap={tap:.4f}): não atinge sobrecarga em {ANOS_MAX} anos")
print(f"{'='*80}\n")
