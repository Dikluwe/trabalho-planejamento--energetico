import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dss import dss

MASTER = str(HERE / "Master.dss")

dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=1"
dss.Text.Command = "Set LoadMult=1.0"

circuit = dss.ActiveCircuit

# Descobre kV e barramento MT do trf_6_4910a
circuit.Transformers.Name = "trf_6_4910a"
kv_wdg1 = circuit.Transformers.kV  # winding 1 ativo por padrão
circuit.Transformers.Wdg = 2
kv_wdg2 = circuit.Transformers.kV

circuit.SetActiveElement("Transformer.trf_6_4910a")
buses = list(circuit.ActiveCktElement.BusNames)
bus_mt = buses[0].split(".")[0]
bus_bt = buses[1].split(".")[0]

print(f"trf_6_4910a:")
print(f"  bus MT : {bus_mt}")
print(f"  bus BT : {bus_bt}")
print(f"  kV wdg1: {kv_wdg1:.4f}")
print(f"  kV wdg2: {kv_wdg2:.4f}")

# Novo barramento BT
novo_bus = "et6_4910b"

# Tenta instalar trafo monofásico (igual ao existente)
# Primeiro verifica se o trafo existente é monofásico ou trifásico
circuit.Transformers.Name = "trf_6_4910a"
n_phases = circuit.Transformers.NumWindings
print(f"  NumWindings: {n_phases}")

circuit.SetActiveElement("Transformer.trf_6_4910a")
print(f"  NumPhases: {circuit.ActiveCktElement.NumPhases}")
print(f"  BusNames: {list(circuit.ActiveCktElement.BusNames)}")

# Instala o novo trafo
kv_mt_fase = kv_wdg1  # já é tensão de fase se monofásico
cmd_novo = (
    f"New Transformer.TRF_6_4910b phases=1 windings=2 "
    f"buses=[{bus_mt}.1 {novo_bus}.1] "
    f"conns=[wye wye] kvs=[{kv_mt_fase:.4f} {kv_wdg2:.4f}] "
    f"kvas=[30 30] xhl=2 %Rs=[0.5 0.5]"
)
print(f"\nComando DSS:")
print(f"  {cmd_novo}")
dss.Text.Command = cmd_novo

# Move carga bt_632607_m2 para o novo barramento
dss.Text.Command = f"Edit Load.bt_632607_m2 bus1={novo_bus}.1"

# Verifica se o trafo foi criado
circuit.SetActiveElement("Transformer.trf_6_4910b")
nome_ativo = circuit.ActiveCktElement.Name
print(f"\nTrafo novo criado: {nome_ativo}")
print(f"  BusNames: {list(circuit.ActiveCktElement.BusNames)}")
print(f"  NumPhases: {circuit.ActiveCktElement.NumPhases}")

# Roda hora 7 (pico) e lê os dois trafos
dss.Text.Command = "Set mode=daily stepsize=1h number=7"
circuit.Solution.Solve()

for nome_t, kva in [("trf_6_4910a", 30), ("trf_6_4910b", 30)]:
    circuit.SetActiveElement(f"Transformer.{nome_t}")
    powers = circuit.ActiveCktElement.Powers
    n = circuit.ActiveCktElement.NumPhases
    print(f"\n{nome_t}:")
    print(f"  Powers: {powers[:n*4]}")
    if len(powers) >= n * 2:
        p = sum(powers[0:n*2:2])
        q = sum(powers[1:n*2+1:2])
        s = (p**2 + q**2)**0.5
        print(f"  P={p:.2f} kW  Q={q:.2f} kvar  S={s:.2f} kVA  = {100*s/kva:.1f}%")

# Verifica carga bt_632607_m2
circuit.SetActiveElement("Load.bt_632607_m2")
print(f"\nLoad.bt_632607_m2 bus: {list(circuit.ActiveCktElement.BusNames)}")
