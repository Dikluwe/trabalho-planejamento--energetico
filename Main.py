from pathlib import Path

import numpy as np
import pandas as pd
from dss import DSSException, dss


def InitializeCircuit(
  dssFilePath: str,
  considerPVSystem: bool
):
  text = dss.Text

  text.Command = "Clear"
  text.Command = f'Redirect "{dssFilePath}"'

  if not considerPVSystem:
    text.Command = "Disable PVSystem.*"

  return dss.ActiveCircuit.Solution


def BuildBusData(lowVoltageLimitKv: float):
  circuit = dss.ActiveCircuit
  busData = {}

  for busName in circuit.AllBusNames:
    circuit.SetActiveBus(busName)
    baseKv = circuit.ActiveBus.kVBase

    if baseKv <= 0:
      voltageLevel = "Unknown"
    elif baseKv <= lowVoltageLimitKv:
      voltageLevel = "LV"
    else:
      voltageLevel = "MV"

    busData[busName.lower()] = {
      "baseKv": baseKv,
      "voltageLevel": voltageLevel
    }

  return busData


def BuildLoadBusSet(circuit):
  circuit.SetActiveClass("Load")
  loads = circuit.Loads
  loadBusSet = set()

  currentIndex = loads.First
  while currentIndex > 0:
    busName = circuit.ActiveCktElement.BusNames[0].split(".")[0].lower()
    loadBusSet.add(busName)
    currentIndex = loads.Next

  return loadBusSet


def IsValidNetworkLine(
  lineName: str,
  isSwitch: bool
):
  if isSwitch:
    return False

  if lineName.lower().startswith("resist"):
    return False

  return True


def SolveDailyStep(
  solution,
  hour: int
):
  solution.Solve()

  if not solution.Converged:
    raise DSSException(f"Solução não convergiu na hora {hour}.")


def CollectVoltageRowsForHour(
  hour: int,
  busData: dict,
  loadBusSet: set,
  lowerVoltageLimitPu: float,
  upperVoltageLimitPu: float
):
  rows = []
  circuit = dss.ActiveCircuit

  for busName in loadBusSet:
    circuit.SetActiveBus(busName)
    bus = circuit.ActiveBus
    
    # puVmagAngle retorna uma lista com [magnitude1, angulo1, magnitude2, angulo2...]
    # [0::2] pega apenas as magnitudes das tensões
    voltagesPu = bus.puVmagAngle[0::2] 
    nodes = bus.Nodes
    
    if len(voltagesPu) == 0 or len(nodes) == 0:
      continue

    currentBusData = busData.get(busName, {
      "baseKv": 0.0,
      "voltageLevel": "Unknown"
    })

    for i, voltagePu in enumerate(voltagesPu):
      phase = nodes[i]
      nodeName = f"{busName}.{phase}"

      violationPu = 0.0
      if voltagePu < lowerVoltageLimitPu:
        violationPu = lowerVoltageLimitPu - voltagePu
      elif voltagePu > upperVoltageLimitPu:
        violationPu = voltagePu - upperVoltageLimitPu

      rows.append({
        "hour": hour,
        "node": nodeName,
        "bus": busName,
        "phase": phase,
        "voltagePu": voltagePu,
        "baseKvLN": currentBusData["baseKv"],
        "voltageLevel": currentBusData["voltageLevel"],
        "violationPu": violationPu,
        "hasViolation": int(violationPu > 0)
      })

  return rows


def CollectLineRowsForHour(hour: int):
  circuit = dss.ActiveCircuit
  rows = []

  circuit.SetActiveClass("Line")
  lines = circuit.Lines
  currentIndex = lines.First

  while currentIndex > 0:
    elementName = circuit.ActiveElement.Name
    lineName = lines.Name
    isSwitch = lines.IsSwitch


    if IsValidNetworkLine(lineName, isSwitch):
      element = circuit.ActiveCktElement

      currentsMagAng = element.CurrentsMagAng

      losses = element.Losses
      if currentsMagAng is not None and len(currentsMagAng) > 0:  # type: ignore[arg-type]
        activeLossesKw = losses[0] / 1000.0      # type: ignore[index]
        reactiveLossesKvar = losses[1] / 1000.0  # type: ignore[index]
      normAmps = lines.NormAmps

      maxCurrentA = 0.0
      loadingRatio = np.nan
      loadingPct = np.nan
      isOverloaded = 0
      activeLossesKw = np.nan
      reactiveLossesKvar = np.nan

      if currentsMagAng is not None and len(currentsMagAng) > 0:
        currentMagnitudes = currentsMagAng[0::2]
        if len(currentMagnitudes) > 0:
          maxCurrentA = max(currentMagnitudes)

      if normAmps is not None and normAmps > 0:
        loadingRatio = maxCurrentA / normAmps
        loadingPct = loadingRatio * 100.0
        isOverloaded = int(loadingRatio > 0.8)

      if isOverloaded:
        print(
          f"Alerta: Linha {lineName} está sobrecarregada no horário "
          f"{hour}: {loadingPct:.2f}% da capacidade nominal"
        )

      if losses is not None and len(losses) >= 2:  # type: ignore[arg-type]
        activeLossesKw = losses[0] / 1000.0      # type: ignore[index]
        reactiveLossesKvar = losses[1] / 1000.0  # type: ignore[index]

      rows.append({
        "hour": hour,
        "element": elementName,
        "line": lineName,
        "bus1": lines.Bus1.split(".")[0],
        "bus2": lines.Bus2.split(".")[0],
        "normAmps": normAmps,
        "maxCurrentA": maxCurrentA,
        "loadingRatio": loadingRatio,
        "loadingPct": loadingPct,
        "isOverloaded": isOverloaded,
        "activeLossesKw": activeLossesKw,
        "reactiveLossesKvar": reactiveLossesKvar
      })

    currentIndex = lines.Next

  return rows


def CollectTransformerRowsForHour(hour: int):
  circuit = dss.ActiveCircuit
  rows = []

  transformerNames = list(circuit.Transformers.AllNames)

  for transformerName in transformerNames:
    circuit.Transformers.Name = transformerName
    ratedKva = circuit.Transformers.kVA

    circuit.SetActiveElement(f"Transformer.{transformerName}")
    activeElement = circuit.ActiveCktElement
    powers = activeElement.Powers

    if powers is None or len(powers) == 0:
      continue

    terminalCount = activeElement.NumTerminals
    if terminalCount <= 0:
      continue

    activePowers = []
    reactivePowers = []

    for powerIndex in range(0, len(powers), 2):
      activePowers.append(powers[powerIndex])
      reactivePowers.append(powers[powerIndex + 1])

    phaseCountFirstTerminal = len(activePowers) // terminalCount
    activePowerKw = sum(activePowers[:phaseCountFirstTerminal])
    reactivePowerKvar = sum(reactivePowers[:phaseCountFirstTerminal])

    apparentPowerKva = np.sqrt(activePowerKw ** 2 + reactivePowerKvar ** 2)

    loadingPct = np.nan
    isOverloaded = 0

    if ratedKva is not None and ratedKva > 0:
      loadingPct = 100.0 * apparentPowerKva / ratedKva
      isOverloaded = int(loadingPct > 100.0)

    rows.append({
      "hour": hour,
      "transformer": transformerName,
      "apparentPowerKva": apparentPowerKva,
      "ratedKva": ratedKva,
      "loadingPct": loadingPct,
      "isOverloaded": isOverloaded
    })

  return rows


def CollectMeterState():
  meters = dss.ActiveCircuit.Meters
  rows = []

  currentIndex = meters.First
  while currentIndex > 0:
    meterName = meters.Name
    registerValues = list(meters.RegisterValues)

    activeEnergyKWh = np.nan
    reactiveEnergyKvarh = np.nan
    activeLossesKWh = np.nan
    reactiveLossesKvarh = np.nan

    if len(registerValues) > 0:
      activeEnergyKWh = registerValues[0]

    if len(registerValues) > 1:
      reactiveEnergyKvarh = registerValues[1]

    if len(registerValues) > 12:
      activeLossesKWh = registerValues[12]

    if len(registerValues) > 13:
      reactiveLossesKvarh = registerValues[13]

    rows.append({
      "meterName": meterName,
      "activeEnergyKWh": activeEnergyKWh,
      "reactiveEnergyKvarh": reactiveEnergyKvarh,
      "activeLossesKWh": activeLossesKWh,
      "reactiveLossesKvarh": reactiveLossesKvarh
    })

    currentIndex = meters.Next

  return pd.DataFrame(rows)


def BuildPreviousMeterState(dfMeterState: pd.DataFrame):
  previousMeterState = {}

  if dfMeterState.empty:
    return previousMeterState

  for _, currentRow in dfMeterState.iterrows():
    previousMeterState[currentRow["meterName"]] = {
      "activeEnergyKWh": currentRow["activeEnergyKWh"],
      "reactiveEnergyKvarh": currentRow["reactiveEnergyKvarh"],
      "activeLossesKWh": currentRow["activeLossesKWh"],
      "reactiveLossesKvarh": currentRow["reactiveLossesKvarh"]
    }

  return previousMeterState


def CollectMeterRowsForHour(
  hour: int,
  previousMeterState: dict
):
  currentMeterState = CollectMeterState()
  rows = []

  if currentMeterState.empty:
    return rows, previousMeterState

  for _, currentRow in currentMeterState.iterrows():
    meterName = currentRow["meterName"]

    previousRow = previousMeterState.get(meterName, {
      "activeEnergyKWh": 0.0,
      "reactiveEnergyKvarh": 0.0,
      "activeLossesKWh": 0.0,
      "reactiveLossesKvarh": 0.0
    })

    activeEnergyKWh = currentRow["activeEnergyKWh"]
    reactiveEnergyKvarh = currentRow["reactiveEnergyKvarh"]
    activeLossesKWh = currentRow["activeLossesKWh"]
    reactiveLossesKvarh = currentRow["reactiveLossesKvarh"]

    deltaActiveEnergyKWh = activeEnergyKWh - previousRow["activeEnergyKWh"]
    deltaReactiveEnergyKvarh = (
      reactiveEnergyKvarh - previousRow["reactiveEnergyKvarh"]
    )
    deltaActiveLossesKWh = activeLossesKWh - previousRow["activeLossesKWh"]
    deltaReactiveLossesKvarh = (
      reactiveLossesKvarh - previousRow["reactiveLossesKvarh"]
    )

    rows.append({
      "hour": hour,
      "meterName": meterName,
      "activeEnergyKWh": activeEnergyKWh,
      "reactiveEnergyKvarh": reactiveEnergyKvarh,
      "activeLossesKWh": activeLossesKWh,
      "reactiveLossesKvarh": reactiveLossesKvarh,
      "deltaActiveEnergyKWh": deltaActiveEnergyKWh,
      "deltaReactiveEnergyKvarh": deltaReactiveEnergyKvarh,
      "deltaActiveLossesKWh": deltaActiveLossesKWh,
      "deltaReactiveLossesKvarh": deltaReactiveLossesKvarh
    })

  updatedPreviousMeterState = BuildPreviousMeterState(currentMeterState)

  return rows, updatedPreviousMeterState


def CollectEnergySummary(dfMeterByHour: pd.DataFrame):
  if dfMeterByHour.empty:
    return pd.DataFrame()

  summaryRows = []

  for meterName, currentGroup in dfMeterByHour.groupby("meterName"):
    currentGroup = currentGroup.sort_values("hour").copy()

    totalEnergyKWh = currentGroup["activeEnergyKWh"].iloc[-1]
    totalReactiveEnergyKvarh = currentGroup["reactiveEnergyKvarh"].iloc[-1]
    totalLossesKWh = currentGroup["activeLossesKWh"].iloc[-1]
    totalReactiveLossesKvarh = currentGroup["reactiveLossesKvarh"].iloc[-1]

    lossesPct = np.nan
    if pd.notna(totalEnergyKWh) and totalEnergyKWh > 0:
      lossesPct = 100.0 * totalLossesKWh / totalEnergyKWh

    summaryRows.append({
      "meterName": meterName,
      "totalEnergyKWh": totalEnergyKWh,
      "totalReactiveEnergyKvarh": totalReactiveEnergyKvarh,
      "totalLossesKWh": totalLossesKWh,
      "totalReactiveLossesKvarh": totalReactiveLossesKvarh,
      "lossesPct": lossesPct
    })

  return pd.DataFrame(summaryRows)


def BuildVoltageSummary(dfVoltages: pd.DataFrame):
  rows = []

  for voltageLevel in ["MV", "LV"]:
    dfLevel = dfVoltages[dfVoltages["voltageLevel"] == voltageLevel].copy()
    if dfLevel.empty:
      continue

    rows.append({
      "voltageLevel": voltageLevel,
      "minVoltagePu": dfLevel["voltagePu"].min(),
      "meanVoltagePu": dfLevel["voltagePu"].mean(),
      "maxVoltagePu": dfLevel["voltagePu"].max(),
      "maxViolationPu": dfLevel["violationPu"].max(),
      "violationCount": int(dfLevel["hasViolation"].sum()),
      "violationPct": 100.0 * dfLevel["hasViolation"].mean()
    })

  return pd.DataFrame(rows)


def BuildLineSummary(dfLines: pd.DataFrame):
  if dfLines.empty:
    return pd.DataFrame()

  return (
    dfLines
    .groupby("line", as_index=False)
    .agg(
      maxCurrentA=("maxCurrentA", "max"),
      normAmps=("normAmps", "max"),
      maxLoadingPct=("loadingPct", "max"),
      meanLoadingPct=("loadingPct", "mean"),
      overloadHours=("isOverloaded", "sum")
    )
    .sort_values("maxLoadingPct", ascending=False)
  )


def BuildTransformerSummary(dfTransformers: pd.DataFrame):
  if dfTransformers.empty:
    return pd.DataFrame()

  return (
    dfTransformers
    .groupby("transformer", as_index=False)
    .agg(
      ratedKva=("ratedKva", "max"),
      maxApparentPowerKva=("apparentPowerKva", "max"),
      maxLoadingPct=("loadingPct", "max"),
      meanLoadingPct=("loadingPct", "mean"),
      overloadHours=("isOverloaded", "sum")
    )
    .sort_values("maxLoadingPct", ascending=False)
  )


def BuildMeterHourSummary(dfMeterByHour: pd.DataFrame):
  if dfMeterByHour.empty:
    return pd.DataFrame()

  return (
    dfMeterByHour
    .groupby("hour", as_index=False)
    .agg(
      totalDeltaActiveEnergyKWh=("deltaActiveEnergyKWh", "sum"),
      totalDeltaReactiveEnergyKvarh=("deltaReactiveEnergyKvarh", "sum"),
      totalDeltaActiveLossesKWh=("deltaActiveLossesKWh", "sum"),
      totalDeltaReactiveLossesKvarh=("deltaReactiveLossesKvarh", "sum")
    )
    .sort_values("hour")
  )


def BuildDailyNetworkSummary(
  dfVoltageSummary: pd.DataFrame,
  dfLineSummary: pd.DataFrame,
  dfTransformerSummary: pd.DataFrame,
  dfEnergySummary: pd.DataFrame
):
  mvViolationPct = 0.0
  lvViolationPct = 0.0

  if not dfVoltageSummary.empty:
    mvData = dfVoltageSummary[dfVoltageSummary["voltageLevel"] == "MV"]
    lvData = dfVoltageSummary[dfVoltageSummary["voltageLevel"] == "LV"]

    if not mvData.empty:
      mvViolationPct = mvData.iloc[0]["violationPct"]

    if not lvData.empty:
      lvViolationPct = lvData.iloc[0]["violationPct"]

  overloadedLines = 0
  overloadedTransformers = 0
  maxLineLoadingPct = 0.0
  maxTransformerLoadingPct = 0.0

  if not dfLineSummary.empty:
    overloadedLines = int((dfLineSummary["maxLoadingPct"] > 100.0).sum())
    maxLineLoadingPct = dfLineSummary["maxLoadingPct"].max()

  if not dfTransformerSummary.empty:
    overloadedTransformers = int((dfTransformerSummary["maxLoadingPct"] > 100.0).sum())
    maxTransformerLoadingPct = dfTransformerSummary["maxLoadingPct"].max()

  totalEnergyKWh = 0.0
  totalReactiveEnergyKvarh = 0.0
  totalLossesKWh = 0.0
  totalReactiveLossesKvarh = 0.0
  lossesPct = np.nan

  if not dfEnergySummary.empty:
    totalEnergyKWh = dfEnergySummary["totalEnergyKWh"].sum()
    totalReactiveEnergyKvarh = dfEnergySummary["totalReactiveEnergyKvarh"].sum()
    totalLossesKWh = dfEnergySummary["totalLossesKWh"].sum()
    totalReactiveLossesKvarh = dfEnergySummary["totalReactiveLossesKvarh"].sum()

    if totalEnergyKWh > 0:
      lossesPct = 100.0 * totalLossesKWh / totalEnergyKWh

  return pd.DataFrame([{
    "mvViolationPct": mvViolationPct,
    "lvViolationPct": lvViolationPct,
    "overloadedLines": overloadedLines,
    "overloadedTransformers": overloadedTransformers,
    "maxLineLoadingPct": maxLineLoadingPct,
    "maxTransformerLoadingPct": maxTransformerLoadingPct,
    "totalEnergyKWh": totalEnergyKWh,
    "totalReactiveEnergyKvarh": totalReactiveEnergyKvarh,
    "totalLossesKWh": totalLossesKWh,
    "totalReactiveLossesKvarh": totalReactiveLossesKvarh,
    "lossesPct": lossesPct
  }])


def ExportResults(
  outputFolderPath: str,
  dfVoltages: pd.DataFrame,
  dfLines: pd.DataFrame,
  dfTransformers: pd.DataFrame,
  dfMeterByHour: pd.DataFrame,
  dfVoltageSummary: pd.DataFrame,
  dfLineSummary: pd.DataFrame,
  dfTransformerSummary: pd.DataFrame,
  dfMeterHourSummary: pd.DataFrame,
  dfEnergySummary: pd.DataFrame,
  dfNetworkSummary: pd.DataFrame
):
  outputFolder = Path(outputFolderPath)
  outputFolder.mkdir(parents=True, exist_ok=True)

  dfVoltages.to_csv(outputFolder / "VoltagesByHour.csv", index=False)
  dfLines.to_csv(outputFolder / "LinesLoadingByHour.csv", index=False)
  dfTransformers.to_csv(outputFolder / "TransformersLoadingByHour.csv", index=False)
  dfMeterByHour.to_csv(outputFolder / "EnergyMetersByHour.csv", index=False)
  dfVoltageSummary.to_csv(outputFolder / "VoltageSummary.csv", index=False)
  dfLineSummary.to_csv(outputFolder / "LineSummary.csv", index=False)
  dfTransformerSummary.to_csv(outputFolder / "TransformerSummary.csv", index=False)
  dfMeterHourSummary.to_csv(outputFolder / "EnergyMeterHourSummary.csv", index=False)
  dfEnergySummary.to_csv(outputFolder / "EnergySummary.csv", index=False)
  dfNetworkSummary.to_csv(outputFolder / "DailyNetworkSummary.csv", index=False)


def SplitVoltagesByPhase(dfVoltages: pd.DataFrame):
  dfPhaseA = dfVoltages[dfVoltages["phase"] == 1].copy()
  dfPhaseB = dfVoltages[dfVoltages["phase"] == 2].copy()
  dfPhaseC = dfVoltages[dfVoltages["phase"] == 3].copy()

  return dfPhaseA, dfPhaseB, dfPhaseC


def RunDailySimulationAndCollect(
  solution,
  totalHours: int,
  lowVoltageLimitKv: float,
  lowerVoltageLimitPu: float,
  upperVoltageLimitPu: float
):
  circuit = dss.ActiveCircuit
  busData = BuildBusData(lowVoltageLimitKv)
  loadBusSet = BuildLoadBusSet(circuit)

  voltageRows = []
  lineRows = []
  transformerRows = []
  meterRows = []

  dss.Text.Command = "Reset Meters"
  previousMeterState = BuildPreviousMeterState(CollectMeterState())

  dss.Text.Command = "Set mode=daily stepsize=1h number=1"
  for hour in range(totalHours):
    SolveDailyStep(
      solution=solution,
      hour=hour
    )

    voltageRows.extend(
      CollectVoltageRowsForHour(
        hour=hour,
        busData=busData,
        loadBusSet=loadBusSet,
        lowerVoltageLimitPu=lowerVoltageLimitPu,
        upperVoltageLimitPu=upperVoltageLimitPu
      )
    )

    lineRows.extend(
      CollectLineRowsForHour(hour=hour)
    )

    transformerRows.extend(
      CollectTransformerRowsForHour(hour=hour)
    )

    currentMeterRows, previousMeterState = CollectMeterRowsForHour(
      hour=hour,
      previousMeterState=previousMeterState
    )
    meterRows.extend(currentMeterRows)

  dfVoltages = pd.DataFrame(voltageRows)
  dfLines = pd.DataFrame(lineRows)
  dfTransformers = pd.DataFrame(transformerRows)
  dfMeterByHour = pd.DataFrame(meterRows)

  return dfVoltages, dfLines, dfTransformers, dfMeterByHour


def RunDailyNetworkAnalysis(
  dssFilePath: str,
  outputFolderPath: str,
  considerPVSystem: bool,
  totalHours: int,
  lowVoltageLimitKv: float,
  lowerVoltageLimitPu: float,
  upperVoltageLimitPu: float
):
  (
    solution
  ) = InitializeCircuit(
    dssFilePath=dssFilePath,
    considerPVSystem=considerPVSystem
  )

  (
    dfVoltages,
    dfLines,
    dfTransformers,
    dfMeterByHour
  ) = RunDailySimulationAndCollect(
    solution=solution,
    totalHours=totalHours,
    lowVoltageLimitKv=lowVoltageLimitKv,
    lowerVoltageLimitPu=lowerVoltageLimitPu,
    upperVoltageLimitPu=upperVoltageLimitPu
  )

  dfPhaseA, dfPhaseB, dfPhaseC = SplitVoltagesByPhase(dfVoltages)

  dfVoltageSummary = BuildVoltageSummary(dfVoltages)
  dfLineSummary = BuildLineSummary(dfLines)
  dfTransformerSummary = BuildTransformerSummary(dfTransformers)
  dfMeterHourSummary = BuildMeterHourSummary(dfMeterByHour)
  dfEnergySummary = CollectEnergySummary(dfMeterByHour)

  dfNetworkSummary = BuildDailyNetworkSummary(
    dfVoltageSummary=dfVoltageSummary,
    dfLineSummary=dfLineSummary,
    dfTransformerSummary=dfTransformerSummary,
    dfEnergySummary=dfEnergySummary
  )

  ExportResults(
    outputFolderPath=outputFolderPath,
    dfVoltages=dfVoltages,
    dfLines=dfLines,
    dfTransformers=dfTransformers,
    dfMeterByHour=dfMeterByHour,
    dfVoltageSummary=dfVoltageSummary,
    dfLineSummary=dfLineSummary,
    dfTransformerSummary=dfTransformerSummary,
    dfMeterHourSummary=dfMeterHourSummary,
    dfEnergySummary=dfEnergySummary,
    dfNetworkSummary=dfNetworkSummary
  )

  print("\nResumo diário da rede:\n")
  print(dfNetworkSummary.to_string(index=False))

  print("\nResumo por medidor:\n")
  print(dfEnergySummary.to_string(index=False))

  print("\nEnergia horária agregada dos medidores:\n")
  print(dfMeterHourSummary.to_string(index=False))

  print("\nTop 10 cabos mais carregados:\n")
  print(dfLineSummary.head(10).to_string(index=False))

  print("\nTop 10 transformadores mais carregados:\n")
  print(dfTransformerSummary.head(10).to_string(index=False))

  return {
    "dfVoltages": dfVoltages,
    "dfPhaseA": dfPhaseA,
    "dfPhaseB": dfPhaseB,
    "dfPhaseC": dfPhaseC,
    "dfLines": dfLines,
    "dfTransformers": dfTransformers,
    "dfMeterByHour": dfMeterByHour,
    "dfVoltageSummary": dfVoltageSummary,
    "dfLineSummary": dfLineSummary,
    "dfTransformerSummary": dfTransformerSummary,
    "dfMeterHourSummary": dfMeterHourSummary,
    "dfEnergySummary": dfEnergySummary,
    "dfNetworkSummary": dfNetworkSummary
  }


def BuildDefaultPaths():
  currentFolder = Path(__file__).resolve().parent
  dssFilePath = currentFolder / "Master.dss"
  outputFolderPath = currentFolder / "Resultados"
  csvFolderPath = outputFolderPath / "buscoords.csv"
  return dssFilePath, outputFolderPath, csvFolderPath


if __name__ == "__main__":
  dssFilePath, outputFolderPath, csvFolderPath = BuildDefaultPaths()

  considerpvsystem = True
  totalhours = 24
  lowvoltagelimitkv = 1.0
  lowervoltagelimitpu = 0.95
  uppervoltagelimitpu = 1.05

  RunDailyNetworkAnalysis(
    dssFilePath=str(dssFilePath),
    outputFolderPath=str(outputFolderPath),
    considerPVSystem=considerpvsystem,
    totalHours=totalhours,
    lowVoltageLimitKv=lowvoltagelimitkv,
    lowerVoltageLimitPu=lowervoltagelimitpu,
    upperVoltageLimitPu=uppervoltagelimitpu
  )

