import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dss import dss

MASTER = str(HERE / "Master.dss")
dss.Text.Command = "Clear"
dss.Text.Command = f'Redirect "{MASTER}"'
dss.Text.Command = "Set mode=daily stepsize=1h number=12"
circuit = dss.ActiveCircuit
circuit.Solution.Solve()

# Inspeciona barramentos BT específicos
print("Barramentos BT — amostra de 10:")
print(f"  {'Nome':<25} {'kVBase':>8} {'NumNodes':>9} {'VMag[0]':>10} {'vpu calc':>10}")
print(f"  {'-'*66}")

all_bus = list(circuit.AllBusNames)
count = 0
for nome in all_bus:
    circuit.SetActiveBus(nome)
    kv = circuit.ActiveBus.kVBase
    if 0.05 < kv <= 1.0:
        vmag = circuit.ActiveBus.VMagAngle
        nn   = circuit.ActiveBus.NumNodes
        if len(vmag) >= 1 and vmag[0] > 0:
            vbase = kv*1000 if nn < 3 else kv*1000/3**0.5
            vpu   = vmag[0] / vbase
            print(f"  {nome:<25} {kv:>8.3f} {nn:>9} {vmag[0]:>10.1f} {vpu:>10.4f}")
            count += 1
            if count >= 15:
                break

# Foca no barramento et6_4910 e uc632607
print(f"\nBarramentos do ramal trf_6_4910a:")
for nome in ["et6_4910", "uc632607"]:
    circuit.SetActiveBus(nome)
    kv   = circuit.ActiveBus.kVBase
    vmag = circuit.ActiveBus.VMagAngle
    nn   = circuit.ActiveBus.NumNodes
    print(f"  {nome}: kVBase={kv:.4f}  NumNodes={nn}  VMagAngle={list(vmag[:4])}")

# Verifica o trafo trf_6_4910a — tensão nominal do secundário
circuit.Transformers.Name = "trf_6_4910a"
circuit.Transformers.Wdg = 2
print(f"\ntrf_6_4910a wdg=2: kV={circuit.Transformers.kV:.4f}  kVA={circuit.Transformers.kVA}")

# Verifica medidor de tensão do main_trabalho
# O main_trabalho usa lvViolationPct — como ele calcula?
# Busca um barramento adequado para ter a tensão pu correta
print(f"\nBusca barramentos BT com vpu razoável (0.85-1.10):")
count2 = 0
for nome in all_bus:
    circuit.SetActiveBus(nome)
    kv = circuit.ActiveBus.kVBase
    if 0.05 < kv <= 1.0:
        vmag = circuit.ActiveBus.VMagAngle
        nn   = circuit.ActiveBus.NumNodes
        if len(vmag) >= 1 and vmag[0] > 0:
            # Testa as duas formas de calcular vpu
            vpu_1 = vmag[0] / (kv * 1000)              # fase/kVBase
            vpu_2 = vmag[0] / (kv * 1000 / 3**0.5)    # fase/Vfase
            if 0.85 < vpu_1 < 1.10:
                print(f"  {nome:<25} kV={kv:.3f} nn={nn} V={vmag[0]:.1f} "
                      f"vpu_direto={vpu_1:.4f} vpu_div3={vpu_2:.4f}")
                count2 += 1
                if count2 >= 10:
                    break
