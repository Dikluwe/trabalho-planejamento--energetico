import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dss import dss

MASTER = str(HERE / "Master.dss")

def carregar(mult=1.0):
    dss.Text.Command = "Clear"
    dss.Text.Command = f'Redirect "{MASTER}"'
    dss.Text.Command = "Set mode=daily stepsize=1h number=1"
    dss.Text.Command = f"Set LoadMult={mult}"
    return dss.ActiveCircuit

# -------------------------------------------------------
# BUG 2: localiza cargas de uc632607
# -------------------------------------------------------
print("=== BUG 2 — CARGAS NO RAMAL uc632607 ===")
circuit = carregar(1.0)
loads = circuit.Loads
idx = loads.First
while idx > 0:
    circuit.SetActiveElement(f"Load.{loads.Name}")
    bus = circuit.ActiveCktElement.BusNames[0].split(".")[0]
    if "632607" in bus or "632607" in loads.Name or "4910" in loads.Name:
        print(f"  Load.{loads.Name}  bus={bus}  kW={loads.kW:.2f}")
    idx = loads.Next

# -------------------------------------------------------
# BUG 3: GD no ramal do trf_11_305a
# -------------------------------------------------------
print("\n=== BUG 3 — GD NO RAMAL trf_11_305a ===")
circuit = carregar(1.0)
circuit.SetActiveElement("Transformer.trf_11_305a")
buses = list(circuit.ActiveCktElement.BusNames)
bus_bt_305 = buses[1].split(".")[0]
print(f"  Barramento BT: {bus_bt_305}")

circuit.SetActiveClass("PVSystem")
idx = circuit.ActiveClass.First
gd_encontrada = False
while idx > 0:
    nome = circuit.ActiveCktElement.Name.split(".")[1]
    bus_pv = circuit.ActiveCktElement.BusNames[0].split(".")[0]
    if bus_bt_305 in bus_pv or bus_pv in bus_bt_305:
        print(f"  PVSystem.{nome}  bus={bus_pv}")
        gd_encontrada = True
    idx = circuit.ActiveClass.Next
if not gd_encontrada:
    print("  Nenhuma GD diretamente no barramento BT do trf_11_305a")
    print("  O efeito pode ser via GD em barramentos vizinhos na MT")

# Carregamento hora a hora do trf_11_305a para mult=1.0 e 1.2
print("\n  Carregamento hora a hora (LoadMult 1.0 e 1.2):")
print(f"  {'Hora':>4} {'mult=1.0':>10} {'mult=1.2':>10}")
print(f"  {'-'*28}")
for h in range(24):
    circuit_10 = carregar(1.0) if h == 0 else None
    circuit_12 = carregar(1.2) if h == 0 else None

    # Mais eficiente: roda os dois em paralelo
    if h == 0:
        c10 = carregar(1.0)
        c12 = carregar(1.2)

    c10.Solution.Solve()
    c10.SetActiveElement("Transformer.trf_11_305a")
    p10 = c10.ActiveCktElement.Powers
    n   = c10.ActiveCktElement.NumPhases
    s10 = (sum(p10[0:n*2:2])**2 + sum(p10[1:n*2+1:2])**2)**0.5
    pct10 = 100 * s10 / 75

    c12.Solution.Solve()
    c12.SetActiveElement("Transformer.trf_11_305a")
    p12 = c12.ActiveCktElement.Powers
    s12 = (sum(p12[0:n*2:2])**2 + sum(p12[1:n*2+1:2])**2)**0.5
    pct12 = 100 * s12 / 75

    print(f"  {h+1:>4} {pct10:>10.1f} {pct12:>10.1f}")
