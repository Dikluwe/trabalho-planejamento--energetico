import numpy as np
import logging


class DSSExtractor:
    def __init__(self, circuit):
        self.circuit = circuit

    def get_bus_data(self, low_voltage_limit_kv: float) -> dict:
        bus_data = {}
        for bus_name in self.circuit.AllBusNames:
            self.circuit.SetActiveBus(bus_name)
            base_kv = self.circuit.ActiveBus.kVBase

            # Chamada de atenção 3: Tensão base zerada
            if base_kv <= 0:
                logging.warning(
                    f"A barra '{bus_name}' está com tensão base igual a zero. Execute o comando CalcVoltageBases no OpenDSS."
                )
                voltage_level = "Unknown"
            elif base_kv <= low_voltage_limit_kv:
                voltage_level = "LV"
            else:
                voltage_level = "MV"

            bus_data[bus_name.lower()] = {
                "baseKv": base_kv,
                "voltageLevel": voltage_level,
            }
        return bus_data

    def get_load_bus_set(self) -> set:
        self.circuit.SetActiveClass("Load")
        loads = self.circuit.Loads
        load_bus_set = set()

        current_index = loads.First
        while current_index > 0:
            bus_name = self.circuit.ActiveCktElement.BusNames[0].split(".")[0].lower()
            load_bus_set.add(bus_name)
            current_index = loads.Next

        return load_bus_set

    def get_voltages(
        self,
        hour: int,
        bus_data: dict,
        load_bus_set: set,
        lower_limit_pu: float,
        upper_limit_pu: float,
    ) -> list:
        rows = []
        for bus_name in load_bus_set:
            self.circuit.SetActiveBus(bus_name)
            bus = self.circuit.ActiveBus

            voltages_pu = bus.puVmagAngle[0::2]
            nodes = bus.Nodes

            if len(voltages_pu) == 0 or len(nodes) == 0:
                continue

            current_bus_data = bus_data.get(
                bus_name, {"baseKv": 0.0, "voltageLevel": "Unknown"}
            )

            for i, voltage_pu in enumerate(voltages_pu):
                phase = nodes[i]
                node_name = f"{bus_name}.{phase}"

                violation_pu = 0.0
                if voltage_pu > 0:  # Evita erro matemático se a tensão for 0 absoluto
                    if voltage_pu < lower_limit_pu:
                        violation_pu = lower_limit_pu - voltage_pu
                    elif voltage_pu > upper_limit_pu:
                        violation_pu = voltage_pu - upper_limit_pu

                rows.append(
                    {
                        "hour": hour,
                        "node": node_name,
                        "bus": bus_name,
                        "phase": phase,
                        "voltagePu": voltage_pu,
                        "baseKvLN": current_bus_data["baseKv"],
                        "voltageLevel": current_bus_data["voltageLevel"],
                        "violationPu": violation_pu,
                        "hasViolation": int(violation_pu > 0),
                    }
                )

        return rows

    def get_lines(self, hour: int) -> list:
        rows = []
        self.circuit.SetActiveClass("Line")
        lines = self.circuit.Lines
        current_index = lines.First

        while current_index > 0:
            element_name = self.circuit.ActiveElement.Name
            line_name = lines.Name
            is_switch = lines.IsSwitch

            if not is_switch and not line_name.lower().startswith("resist"):
                element = self.circuit.ActiveCktElement
                currents_mag_ang = element.CurrentsMagAng
                losses = element.Losses
                norm_amps = lines.NormAmps

                max_current_a = 0.0
                loading_ratio = np.nan
                loading_pct = np.nan
                is_overloaded = 0
                active_losses_kw = np.nan
                reactive_losses_kvar = np.nan

                if currents_mag_ang is not None and len(currents_mag_ang) > 0:
                    current_magnitudes = currents_mag_ang[0::2]
                    if len(current_magnitudes) > 0:
                        max_current_a = max(current_magnitudes)

                if norm_amps is not None and norm_amps > 0:
                    loading_ratio = max_current_a / norm_amps
                    loading_pct = loading_ratio * 100.0
                    is_overloaded = int(loading_pct > 100.0)

                if losses is not None and len(losses) >= 2:
                    active_losses_kw = losses[0] / 1000.0
                    reactive_losses_kvar = losses[1] / 1000.0

                rows.append(
                    {
                        "hour": hour,
                        "element": element_name,
                        "line": line_name,
                        "bus1": lines.Bus1.split(".")[0],
                        "bus2": lines.Bus2.split(".")[0],
                        "normAmps": norm_amps,
                        "maxCurrentA": max_current_a,
                        "loadingRatio": loading_ratio,
                        "loadingPct": loading_pct,
                        "isOverloaded": is_overloaded,
                        "activeLossesKw": active_losses_kw,
                        "reactiveLossesKvar": reactive_losses_kvar,
                    }
                )

            current_index = lines.Next

        return rows

    def get_transformers(self, hour: int) -> list:
        rows = []
        transformer_names = list(self.circuit.Transformers.AllNames)

        for transformer_name in transformer_names:
            self.circuit.Transformers.Name = transformer_name
            self.circuit.SetActiveElement(f"Transformer.{transformer_name}")
            active_element = self.circuit.ActiveCktElement
            powers = active_element.Powers

            if powers is None or len(powers) == 0:
                continue

            terminal_count = active_element.NumTerminals

            # O Aviso 4 (transformadores complexos) foi removido,
            # pois o cálculo agora varre todos os terminais fisicamente.

            max_loading_pct = 0.0
            max_apparent_power_kva = 0.0
            max_rated_kva = 0.0

            # A lista 'powers' traz [P1, Q1, P2, Q2...] de TODOS os terminais sequencialmente.
            # Descobrimos a quantidade exata de valores pertencentes a cada terminal.
            values_per_terminal = len(powers) // terminal_count

            for wdg in range(1, terminal_count + 1):
                # Selecionamos o enrolamento atual (1, 2, 3...) para ler seu limite nominal específico
                self.circuit.Transformers.Wdg = wdg
                rated_kva = self.circuit.Transformers.kVA

                # Recorta da lista 'powers' apenas os dados que entram neste terminal
                start_idx = (wdg - 1) * values_per_terminal
                end_idx = start_idx + values_per_terminal
                terminal_powers = powers[start_idx:end_idx]

                # Separa P e Q e soma os dados de todas as fases do terminal
                active_power_kw = sum(terminal_powers[0::2])
                reactive_power_kvar = sum(terminal_powers[1::2])

                # Potência aparente total fluindo por este lado do equipamento (S)
                apparent_power_kva = np.sqrt(
                    active_power_kw**2 + reactive_power_kvar**2
                )

                # Avalia o carregamento apenas para este enrolamento
                loading_pct = 0.0
                if rated_kva is not None and rated_kva > 0:
                    loading_pct = 100.0 * apparent_power_kva / rated_kva

                # Armazena o "pior caso" — o enrolamento que estiver mais próximo de derreter
                if loading_pct > max_loading_pct:
                    max_loading_pct = loading_pct
                    max_apparent_power_kva = apparent_power_kva
                    max_rated_kva = rated_kva

            is_overloaded = int(max_loading_pct > 100.0)

            rows.append(
                {
                    "hour": hour,
                    "transformer": transformer_name,
                    "apparentPowerKva": max_apparent_power_kva,
                    "ratedKva": max_rated_kva,
                    "loadingPct": max_loading_pct,
                    "isOverloaded": is_overloaded,
                }
            )

        return rows

    def get_meter_state(self) -> list:
        meters = self.circuit.Meters
        rows = []
        current_index = meters.First

        while current_index > 0:
            meter_name = meters.Name
            register_values = list(meters.RegisterValues)

            # Chamada de atenção 5: Medidores sem registros suficientes
            if len(register_values) < 14:
                logging.warning(
                    f"O medidor '{meter_name}' tem menos de 14 registros. As perdas não serão calculadas."
                )

            rows.append(
                {
                    "meterName": meter_name,
                    "activeEnergyKWh": register_values[0]
                    if len(register_values) > 0
                    else np.nan,
                    "reactiveEnergyKvarh": register_values[1]
                    if len(register_values) > 1
                    else np.nan,
                    "activeLossesKWh": register_values[12]
                    if len(register_values) > 12
                    else np.nan,
                    "reactiveLossesKvarh": register_values[13]
                    if len(register_values) > 13
                    else np.nan,
                }
            )

            current_index = meters.Next

        return rows
