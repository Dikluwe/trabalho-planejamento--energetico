from dss import DSSException, dss

class DSSSimulation:
    def __init__(self, dss_file: str, pv_system: bool):
        self.engine = dss
        self.text = self.engine.Text
        self.circuit = self.engine.ActiveCircuit
        self._initialize_circuit(dss_file, pv_system)

    def _initialize_circuit(self, path: str, pv_system: bool):
        self.text.Command = "Clear"
        self.text.Command = f'Redirect "{path}"'
        
        # Chamada de atenção 1: Erro de compilação no arquivo original
        if self.engine.Error.Number != 0:
            raise DSSException(f"ERRO CRÍTICO no arquivo DSS: {self.engine.Error.Description}")
        
        if not pv_system:
            self.text.Command = "Disable PVSystem.*"
        
        self.text.Command = "Reset Meters"
        self.text.Command = "Set mode=daily stepsize=1h number=1"

    def solve_step(self, hour: int):
        self.circuit.Solution.Solve()
        
        # Chamada de atenção 2: Erro de convergência matemática
        if not self.circuit.Solution.Converged:
            raise DSSException(f"ERRO CRÍTICO: Solução não convergiu na hora {hour}.")
