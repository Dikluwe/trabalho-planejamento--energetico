from dss import dss
from core import configuracao

circuit = configuracao.inicializar_dss(dss)
circuit.SetActiveElement('Line.smt_29422')
print(f"Nome: {circuit.ActiveCktElement.Name}")
print(f"Fases: {circuit.ActiveCktElement.NumPhases}")
print(f"Comprimento: {circuit.ActiveCktElement.Properties('length').Val}")
print(f"Unidades: {circuit.ActiveCktElement.Properties('units').Val}")
