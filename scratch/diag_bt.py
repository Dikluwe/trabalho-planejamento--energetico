import importlib
import sys
from pathlib import Path
HERE = Path('.').resolve()
sys.path.insert(0, str(HERE))

from core import configuracao
from dss import dss

def diagnose():
    dss.Text.Command = f"Compile [{configuracao.MASTER_DSS}]"
    
    # Mapear kVBase de todos os barramentos
    buses = dss.ActiveCircuit.AllBusNames
    niveis = {}
    for b in buses:
        dss.ActiveCircuit.SetActiveBus(b)
        niveis[b.lower()] = 'mt' if dss.ActiveCircuit.ActiveBus.kVBase > 1.0 else 'bt'
    
    # Contar linhas BT
    dss.ActiveCircuit.Lines.First
    bt_lines = []
    while True:
        b1 = dss.ActiveCircuit.Lines.Bus1.split('.')[0].lower()
        b2 = dss.ActiveCircuit.Lines.Bus2.split('.')[0].lower()
        if niveis.get(b1) == 'bt' and niveis.get(b2) == 'bt':
            bt_lines.append((b1, b2))
        
        if not dss.ActiveCircuit.Lines.Next > 0: break
    
    print(f"Total Lines: {dss.ActiveCircuit.Lines.Count}")
    print(f"BT-BT Lines: {len(bt_lines)}")
    if bt_lines:
        print(f"Sample BT Lines: {bt_lines[:5]}")
    
    # Verificar Transformers
    dss.ActiveCircuit.Transformers.First
    trans_missing_bt = 0
    while True:
        names = dss.ActiveCircuit.ActiveCktElement.BusNames
        b_sec = names[1].split('.')[0].lower() if len(names) > 1 else None
        if b_sec and niveis.get(b_sec) == 'mt':
            # This would be strange: a transformer secondary that is MT? 
            # (Maybe a step-up or voltage regulator)
            pass
        if not dss.ActiveCircuit.Transformers.Next > 0: break

if __name__ == "__main__":
    diagnose()
