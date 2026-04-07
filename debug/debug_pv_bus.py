import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dss import dss

MASTER = str(HERE.parent / "dss" / "Master.dss")
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=12"
circuit = dss.ActiveCircuit
circuit.Solution.Solve()

# PVSystems com Vmax=0 no ranking
suspeitos = [
    "gd.rs.001.590.899",
    "gd.rs.000.622.799",
    "gd.rs.000.197.382",
    "gd.rs.001.255.347",
    "gd.rs.001.864.524",
    "gd.rs.001.922.364",
]

print("Diagnóstico dos PVSystems com Vmax=0 no ranking:\n")
idx = circuit.PVSystems.First
while idx > 0:
    nome = circuit.PVSystems.Name
    if nome in suspeitos:
        bus_pv = circuit.ActiveCktElement.BusNames[0].split(".")[0]
        circuit.SetActiveBus(bus_pv)
        kv  = circuit.ActiveBus.kVBase
        nn  = circuit.ActiveBus.NumNodes
        vmag = circuit.ActiveBus.VMagAngle
        vpu_direto = vmag[0] / (kv * 1000) if kv > 0 and len(vmag) > 0 else 0
        vpu_div3   = vmag[0] / (kv * 1000 / 3**0.5) if kv > 0 and len(vmag) > 0 else 0
        print(f"  {nome}")
        print(f"    bus={bus_pv}  kVBase={kv:.4f}  NumNodes={nn}")
        print(f"    VMag[0]={vmag[0]:.2f}V  vpu_direto={vpu_direto:.4f}  vpu_div3={vpu_div3:.4f}")
        print(f"    Categoria: {'MT' if kv > 1.0 else 'BT'}")
        print()
    idx = circuit.PVSystems.Next
