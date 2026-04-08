import pandas as pd
import numpy as np
from pathlib import Path
from .dss_extractors import DSSExtractor


class DailyNetworkAnalyzer:
    def __init__(
        self,
        simulador,
        total_hours: int,
        low_voltage_kv: float,
        lower_v_pu: float,
        upper_v_pu: float,
        output_folder: str,
    ):
        self.simulador = simulador
        # Instancia o extrator passando o circuito ativo do simulador
        self.extrator = DSSExtractor(self.simulador.circuit)
        self.total_hours = total_hours
        self.low_voltage_kv = low_voltage_kv
        self.lower_v_pu = lower_v_pu
        self.upper_v_pu = upper_v_pu
        self.output_folder = Path(output_folder)

    def run_analysis_and_export(self) -> dict:
        # Usa o extrator para mapear a rede
        bus_data = self.extrator.get_bus_data(self.low_voltage_kv)
        load_bus_set = self.extrator.get_load_bus_set()

        all_voltages = []
        all_lines = []
        all_transformers = []
        all_meters = []

        previous_meter_state = self._build_initial_meter_state()

        for hour in range(self.total_hours):
            # O simulador apenas avança o tempo
            self.simulador.solve_step(hour)

            # O extrator coleta os dados físicos
            all_voltages.extend(
                self.extrator.get_voltages(
                    hour, bus_data, load_bus_set, self.lower_v_pu, self.upper_v_pu
                )
            )
            all_lines.extend(self.extrator.get_lines(hour))
            all_transformers.extend(self.extrator.get_transformers(hour))

            current_meters, previous_meter_state = self._process_meter_step(
                hour, previous_meter_state
            )
            all_meters.extend(current_meters)

        # Conversão das listas para DataFrames
        df_voltages = pd.DataFrame(all_voltages)
        df_lines = pd.DataFrame(all_lines)
        df_transformers = pd.DataFrame(all_transformers)
        df_meter_by_hour = pd.DataFrame(all_meters)

        # Geração dos resumos
        df_voltage_summary = self._build_voltage_summary(df_voltages)
        df_line_summary = self._build_line_summary(df_lines)
        df_transformer_summary = self._build_transformer_summary(df_transformers)
        df_energy_summary = self._build_energy_summary(df_meter_by_hour)
        df_meter_hour_summary = self._build_meter_hour_summary(df_meter_by_hour)

        df_network_summary = self._build_network_summary(
            df_voltage_summary,
            df_line_summary,
            df_transformer_summary,
            df_energy_summary,
        )

        # Exportação para CSV
        self._export_to_csv(
            df_voltages,
            df_lines,
            df_transformers,
            df_meter_by_hour,
            df_voltage_summary,
            df_line_summary,
            df_transformer_summary,
            df_meter_hour_summary,
            df_energy_summary,
            df_network_summary,
        )

        return {
            "dfVoltages": df_voltages,
            "dfLines": df_lines,
            "dfTransformers": df_transformers,
            "dfMeterByHour": df_meter_by_hour,
            "dfVoltageSummary": df_voltage_summary,
            "dfLineSummary": df_line_summary,
            "dfTransformerSummary": df_transformer_summary,
            "dfMeterHourSummary": df_meter_hour_summary,
            "dfEnergySummary": df_energy_summary,
            "dfNetworkSummary": df_network_summary,
        }

    def _build_initial_meter_state(self) -> dict:
        initial_state_list = self.extrator.get_meter_state()
        state_dict = {}
        for row in initial_state_list:
            state_dict[row["meterName"]] = row
        return state_dict

    def _process_meter_step(self, hour: int, previous_state: dict):
        current_state_list = self.extrator.get_meter_state()
        rows = []
        new_state = {}

        for row in current_state_list:
            meter_name = row["meterName"]
            new_state[meter_name] = row

            prev_row = previous_state.get(
                meter_name,
                {
                    "activeEnergyKWh": 0.0,
                    "reactiveEnergyKvarh": 0.0,
                    "activeLossesKWh": 0.0,
                    "reactiveLossesKvarh": 0.0,
                },
            )

            rows.append(
                {
                    "hour": hour,
                    "meterName": meter_name,
                    "activeEnergyKWh": row["activeEnergyKWh"],
                    "reactiveEnergyKvarh": row["reactiveEnergyKvarh"],
                    "activeLossesKWh": row["activeLossesKWh"],
                    "reactiveLossesKvarh": row["reactiveLossesKvarh"],
                    "deltaActiveEnergyKWh": row["activeEnergyKWh"]
                    - prev_row["activeEnergyKWh"],
                    "deltaReactiveEnergyKvarh": row["reactiveEnergyKvarh"]
                    - prev_row["reactiveEnergyKvarh"],
                    "deltaActiveLossesKWh": row["activeLossesKWh"]
                    - prev_row["activeLossesKWh"],
                    "deltaReactiveLossesKvarh": row["reactiveLossesKvarh"]
                    - prev_row["reactiveLossesKvarh"],
                }
            )

        return rows, new_state

    def _build_voltage_summary(self, df_voltages: pd.DataFrame) -> pd.DataFrame:
        if df_voltages.empty:
            return pd.DataFrame()

        rows = []
        for voltage_level in ["MV", "LV"]:
            df_level = df_voltages[df_voltages["voltageLevel"] == voltage_level]
            if df_level.empty:
                continue

            rows.append(
                {
                    "voltageLevel": voltage_level,
                    "minVoltagePu": df_level["voltagePu"].min(),
                    "meanVoltagePu": df_level["voltagePu"].mean(),
                    "maxVoltagePu": df_level["voltagePu"].max(),
                    "maxViolationPu": df_level["violationPu"].max(),
                    "violationCount": int(df_level["hasViolation"].sum()),
                    "violationPct": 100.0 * df_level["hasViolation"].mean(),
                }
            )
        return pd.DataFrame(rows)

    def _build_line_summary(self, df_lines: pd.DataFrame) -> pd.DataFrame:
        if df_lines.empty:
            return pd.DataFrame()

        return (
            df_lines.groupby("line", as_index=False)
            .agg(
                maxCurrentA=("maxCurrentA", "max"),
                normAmps=("normAmps", "max"),
                maxLoadingPct=("loadingPct", "max"),
                meanLoadingPct=("loadingPct", "mean"),
                overloadHours=("isOverloaded", "sum"),
            )
            .sort_values("maxLoadingPct", ascending=False)
        )

    def _build_transformer_summary(self, df_transformers: pd.DataFrame) -> pd.DataFrame:
        if df_transformers.empty:
            return pd.DataFrame()

        return (
            df_transformers.groupby("transformer", as_index=False)
            .agg(
                ratedKva=("ratedKva", "max"),
                maxApparentPowerKva=("apparentPowerKva", "max"),
                maxLoadingPct=("loadingPct", "max"),
                meanLoadingPct=("loadingPct", "mean"),
                overloadHours=("isOverloaded", "sum"),
            )
            .sort_values("maxLoadingPct", ascending=False)
        )

    def _build_energy_summary(self, df_meter_by_hour: pd.DataFrame) -> pd.DataFrame:
        if df_meter_by_hour.empty:
            return pd.DataFrame()

        summary_rows = []
        for meter_name, group in df_meter_by_hour.groupby("meterName"):
            group = group.sort_values("hour")

            total_energy = group["activeEnergyKWh"].iloc[-1]
            total_losses = group["activeLossesKWh"].iloc[-1]

            losses_pct = np.nan
            if pd.notna(total_energy) and total_energy > 0:
                losses_pct = 100.0 * total_losses / total_energy

            summary_rows.append(
                {
                    "meterName": meter_name,
                    "totalEnergyKWh": total_energy,
                    "totalReactiveEnergyKvarh": group["reactiveEnergyKvarh"].iloc[-1],
                    "totalLossesKWh": total_losses,
                    "totalReactiveLossesKvarh": group["reactiveLossesKvarh"].iloc[-1],
                    "lossesPct": losses_pct,
                }
            )
        return pd.DataFrame(summary_rows)

    def _build_meter_hour_summary(self, df_meter_by_hour: pd.DataFrame) -> pd.DataFrame:
        if df_meter_by_hour.empty:
            return pd.DataFrame()

        return (
            df_meter_by_hour.groupby("hour", as_index=False)
            .agg(
                totalDeltaActiveEnergyKWh=("deltaActiveEnergyKWh", "sum"),
                totalDeltaReactiveEnergyKvarh=("deltaReactiveEnergyKvarh", "sum"),
                totalDeltaActiveLossesKWh=("deltaActiveLossesKWh", "sum"),
                totalDeltaReactiveLossesKvarh=("deltaReactiveLossesKvarh", "sum"),
            )
            .sort_values("hour")
        )

    def _build_network_summary(
        self, df_voltage, df_line, df_transformer, df_energy
    ) -> pd.DataFrame:
        mv_pct = 0.0
        lv_pct = 0.0

        if not df_voltage.empty:
            mv_data = df_voltage[df_voltage["voltageLevel"] == "MV"]
            lv_data = df_voltage[df_voltage["voltageLevel"] == "LV"]
            if not mv_data.empty:
                mv_pct = mv_data.iloc[0]["violationPct"]
            if not lv_data.empty:
                lv_pct = lv_data.iloc[0]["violationPct"]

        ovl_lines = (
            int((df_line["maxLoadingPct"] > 100.0).sum()) if not df_line.empty else 0
        )
        ovl_trafo = (
            int((df_transformer["maxLoadingPct"] > 100.0).sum())
            if not df_transformer.empty
            else 0
        )

        max_line_pct = df_line["maxLoadingPct"].max() if not df_line.empty else 0.0
        max_trafo_pct = (
            df_transformer["maxLoadingPct"].max() if not df_transformer.empty else 0.0
        )

        tot_ener = df_energy["totalEnergyKWh"].sum() if not df_energy.empty else 0.0
        tot_loss = df_energy["totalLossesKWh"].sum() if not df_energy.empty else 0.0
        pct_loss = (100.0 * tot_loss / tot_ener) if tot_ener > 0 else np.nan

        return pd.DataFrame(
            [
                {
                    "mvViolationPct": mv_pct,
                    "lvViolationPct": lv_pct,
                    "overloadedLines": ovl_lines,
                    "overloadedTransformers": ovl_trafo,
                    "maxLineLoadingPct": max_line_pct,
                    "maxTransformerLoadingPct": max_trafo_pct,
                    "totalEnergyKWh": tot_ener,
                    "totalLossesKWh": tot_loss,
                    "lossesPct": pct_loss,
                }
            ]
        )

    def _export_to_csv(self, *dfs):
        self.output_folder.mkdir(parents=True, exist_ok=True)
        filenames = [
            "VoltagesByHour.csv",
            "LinesLoadingByHour.csv",
            "TransformersLoadingByHour.csv",
            "EnergyMetersByHour.csv",
            "VoltageSummary.csv",
            "LineSummary.csv",
            "TransformerSummary.csv",
            "EnergyMeterHourSummary.csv",
            "EnergySummary.csv",
            "DailyNetworkSummary.csv",
        ]

        for df, name in zip(dfs, filenames):
            if not df.empty:
                df.to_csv(self.output_folder / name, index=False)
