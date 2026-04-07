# Scripts Python — Trabalho 1a Planejamento Energético (CRELUZ)

Alimentador 1_REDE2_1, 23,1 kV, 301 consumidores, 521 kW de GD fotovoltaica.
Todos os scripts usam `dss-python` e devem ser executados com `uv run python <script>` a partir da pasta `Finais/`.

---

## Módulos base

### `00_financeiro.py`
Módulo L1 (lógica pura, sem I/O). Contém as funções de cálculo financeiro usadas pelos demais scripts: `calcular_resultado_mensal` (faturamento, custo de perdas e compensação PRODIST a partir das métricas de simulação), `calcular_vpl` (VPL com fluxos de caixa, taxa de desconto e valor residual), faixas de tensão PRODIST (Tabelas 3 e 5) para MT e BT, e fórmulas de DRP/DRC do Módulo 8 item 29.

### `00_expansao.py`
Módulo L1 de avaliação de alternativas. Define a estrutura `Alternativa` e a função `avaliar_alternativa`, que recebe comandos DSS, roda a simulação para cada ano e retorna os benefícios anuais. Importado pelo `01_main_trabalho.py`.

---

## Análise principal

### `01_main_trabalho.py`
Ponto de entrada central do trabalho. Roda o caso base para os 3 anos de crescimento de carga (×1,0 / ×1,1 / ×1,2), calcula o diagnóstico financeiro com as fórmulas do PRODIST Módulo 8, e avalia as 4 alternativas de intervenção (tap nos dois trafos, tap isolado, capacitor fixo, capacitor automático) calculando o VPL de cada uma. Produz a tabela comparativa final com a melhor alternativa identificada.

**Saída principal:** tabela de VPL — alternativa recomendada: tap nos dois trafos, VPL = +USD 1.283.

---

## Diagnóstico do trafo crítico

### `02_analisar_trafo.py`
Extrai a topologia completa do ramal do `trf_6_4910a`: barramento MT (9051), barramento BT (et6_4910), linhas downstream, cargas conectadas (consumidor `uc632607`, medidores `bt_632607_m1` e `bt_632607_m2`) e carregamento estático (90,3% nominal). Ponto de partida para entender por que esse trafo é o único com problema.

### `02_analisar_linha.py`
Analisa a linha `rbt_632607` (32,9 m, 125 A normAmps) que conecta o trafo ao consumidor. Verifica carregamento máximo (32,7% — não é gargalo), perfil de corrente em 24h e descarta a linha como problema independente do trafo.

### `02_horizonte_tap.py`
Determina em qual ano o `trf_6_4910a` ultrapassa 100% de carregamento com e sem ajuste de tap, para cada derivação disponível (wdg=1, tap 1,0 a 1,13). Mostra que tap=1,0333 (+1 derivação) adia a sobrecarga do Ano 3 para o Ano 4 mas reduz a tensão no secundário de 208,3V para 201,5V.

### `02_remanejamento_trafo.py`
Inventário de todos os transformadores da rede com carregamento abaixo de 30%, identificando candidatos para remanejamento como substituto do `trf_6_4910a`. Identifica `trf_11_6482a` e `trf_12_6578a` (45 kVA, ~0,4% de carregamento) como candidatos viáveis.

### `02_impacto_tap_bt.py`
Quantifica o impacto do tap (wdg=1, tap=1,0333 nos dois trafos) no perfil de tensão BT, comparando as faixas PRODIST Tabela 5 antes e após a intervenção nos 3 anos. Identifica quais barramentos mudam de faixa e a variação de tensão no secundário do `trf_6_4910a`.

---

## Análise de capacitores

### `03_diagnosticar_capcontrol.py`
Investigação inicial do CapControl e do tap no OpenDSS. Compara `wdg=1 tap=1.0333` vs `wdg=2 tap=0.9667` medindo carregamento e tensão na hora de pico. Identifica que o elemento de referência correto para o CapControl é `Line.smt_14449` e não `Transformer.TRF_6_4910A`.

### `03_testar_capcontrol.py`
Testa o capacitor automático de 1.200 kvar no barramento 9051 isoladamente. Mostra que o Q máximo na linha `smt_14449` é de 0,2 kvar — muito abaixo do onsetting de 200 kvar — confirmando que o capacitor nunca liga nesse ponto.

### `03_mapear_reativo.py`
Varre todas as linhas MT da rede medindo Q médio e Q máximo em 24h. Identifica FP global de 0,982 (acima do limite regulatório de 0,92) e confirma que a GD fotovoltaica já compensa a demanda reativa. Produz ranking de linhas por demanda reativa para identificar candidatos a capacitor.

### `03_melhor_ponto_capacitor.py`
Separa o perfil de Q em horário noturno (0–6h e 19–23h) e diurno, encontra o barramento com maior déficit noturno real (barramento 181, via `smt_6350`, Q noturno máximo 63 kvar) e testa capacitor automático de 50 kvar com onsetting=37 kvar. Mostra que o capacitor liga mas não desliga corretamente por causa do Q residual de 10,8 kvar.

### `03_comparar_capcontrol.py`
Compara duas estratégias de controle do capacitor no barramento 181: Opção 2 (Loadshape fixo, liga 6h–21h) e Opção 3 (controle manual por hora, só fora do horário de GD com histerese de Q). Resultado: payback de 356 anos (Opção 2) e 12.082 anos (Opção 3) — capacitores inviáveis nesta rede.

---

## Análises complementares

### `04_perfil_tensao_trafos_gd.py`
Três análises em sequência:

1. **Perfil de tensão** — tensão mínima diária em todos os barramentos MT (2320, tensão mínima 0,981 pu) e BT (844, tensão mínima 0,941 pu). Nenhum barramento em faixa precária no caso base.
2. **Carregamento dos trafos** — todos os 177 transformadores nos 3 anos. Apenas 2 com alerta: `trf_6_4910a` (sobrecarga Ano 3) e `trf_11_305a` (80,7%, estável por perfil de ordenha bovina).
3. **Impacto da GD** — comparação hora a hora com e sem os 23 PVSystems (521 kW). A GD reduz perdas em 42,16 kW/dia (15,39 MWh/ano, USD 538,59/ano para a rede).

### `04_pior_caso_duracao_degradacao.py`
Três análises adicionais:

1. **Pior caso diário** — carregamento dos trafos críticos na hora de pico simultâneo (hora 9, 829 kW) para os 3 anos com degradação da GD.
2. **Curva de duração de carga** — horas por ano acima de 70%, 80%, 90% e 100% para `trf_6_4910a` e `trf_11_305a`. O `trf_6_4910a` fica 730 h/ano em sobrecarga no Ano 3 (2 horas por dia todos os dias).
3. **Degradação da GD** — horizonte com 0,7%/ano de perda de potência dos painéis. Tensão mínima BT cai de 0,941 para 0,927 pu no Ano 3, ainda dentro da faixa adequada PRODIST.

---

## Análises avançadas e longo prazo

### `05_remanejamento_15anos.py`
Simula 15 anos (10% carga/ano + 0,7% degradação GD/ano) e identifica 5 trafos com problema: `trf_6_4910a` (Ano 3), `trf_6_3509a` (Ano 10), mais 3 com alerta no Ano 14–15. Calcula VPL do remanejamento em 4 horizontes com e sem risco de falha. Inviável em 3 anos mas atrativo a partir do Ano 5 com risco contabilizado.

### `05_regulador_crescimento_assimetrico.py`
Duas análises fora do escopo direto do enunciado:

1. **Regulador de tensão** — avaliação de regulador ±10% no barramento 9051. Aumenta perdas (609 → 632 kWh/dia) e tem VPL de −USD 6.207. Descartado.
2. **Crescimento assimétrico** — sensibilidade para crescimento concentrado no `uc632607` (×1,4 local, ×1,15 resto). `trf_6_4910a` atinge 123,2% no Ano 3 — remanejamento torna-se prioritário antes do Ano 3 nesse cenário.

### `05_montecarlo_despacho_gd.py`
Duas análises probabilísticas e operacionais:

1. **Monte Carlo** — 100 simulações com crescimento uniforme entre 5% e 15%/ano. Resultado: P10=Ano 2, P50=Ano 3, P90=Ano 4. 100% de probabilidade de sobrecarga até o Ano 15. A recomendação do tap é robusta para qualquer taxa de crescimento realista.
2. **Despacho ótimo da GD** — compara FP 0,92 (atual), 1,00, 0,95 e 0,90 nos 23 PVSystems. FP 0,95 é ótimo (−1,0 kWh/dia de perdas). FP unitário piora as perdas porque elimina compensação reativa local que a GD já faz bem.

---

## Alternativas adicionais

### `06_recondutoramento.py`
Identifica as linhas MT com maiores perdas absolutas (candidatas ao recondutoramento), avalia o recondutoramento da linha `smt_29422` (147 m, R1=1,35 ohm/km) reduzindo R1 e X1 em 50%, e avalia a combinação tap + recondutoramento. Resultados: recondutoramento isolado VPL −USD 914, combinação VPL −USD 2.753. Ambos inviáveis — a rede não tem linhas sobrecarregadas (máximo 74,5%).

### `06_novo_trafo_paralelo.py`
Modela a instalação de um segundo trafo trifásico (30 ou 45 kVA) em paralelo com o `trf_6_4910a`, conectado ao mesmo barramento MT com barramento BT separado (`et6_4910b`). Move o medidor `bt_632607_m2` para o novo trafo. Resultado: trafos ficam em 51% e 54% (30 kVA) ou 36% (45 kVA) no Ano 3. VPL −USD 2.674 (30 kVA) e −USD 3.359 (45 kVA). Inviável em 3 anos.

---

## Análises finais

### `07_expansao_gd_fluxo_n1.py`
Três análises:

1. **Expansão da GD +20%** — impacto no carregamento e perdas no Ano 3. A GD adicional não altera o `trf_6_4910a` (está em ramal isolado da GD). Sem fluxo reverso mesmo com +20%.
2. **Fluxo reverso** — monitora a linha `smt_24122` (entrada do alimentador) hora a hora. Resultado: zero horas com fluxo reverso — subestação importadora líquida durante todo o dia com margem de ~35%.
3. **Análise N-1** — abertura da `smt_31408` (74,5% de carregamento) interrompe 83 barramentos MT e 6 transformadores. Rede radial sem redundância — recomendação de chave seccionadora de emergência.

### `07_perfil_tensao_balanco_sensibilidade.py`
Três análises:

1. **Perfil de tensão por percentil** — distribuição estatística (P0–P100) de tensão mínima diária em todos os barramentos MT (664 válidos) e BT (343 válidos). Nenhum barramento MT abaixo de 0,95 pu; tensão mínima BT de 0,941 pu (faixa adequada).
2. **Balanço energético hora a hora** — subestação, GD, perdas e consumo em 24h. GD fornece 22,2% do consumo total (3.264 kWh/dia de 14.687 kWh/dia). Participação máxima de 44,7% na hora 16.
3. **Sensibilidade do VPL à taxa de desconto** — tap nos dois trafos é atrativo para taxas de 6% a 25%. TIR = 54%. Payback = 2 anos em todos os cenários.

### `07_analise_fp095.py`
Análise financeira completa do ajuste de FP dos PVSystems de 0,92 para 0,95. Benefício de USD 13,42/ano no Ano 1 (decrescente), VPL de +USD 20 em 3 anos e +USD 34 em 15 anos. CAPEX zero — medida operacional de reconfiguração dos inversores. Incluído na tabela final como alternativa complementar ao tap sem custo adicional.

### `07_arrhenius_breakeven_prodist.py`
Quatro análises finais:

1. **Arrhenius** — modelo IEEE C57.91 para envelhecimento do `trf_6_4910a`. Com 730h/ano em sobrecarga (FAA=7,32), probabilidade de falha de 26,5% no Ano 3. Risco financeiro VP = USD 1.807 — maior que o CAPEX do tap. VPL do tap incluindo risco = USD 3.090.
2. **Break-even do remanejamento** — interpolação fluxo a fluxo. Break-even no Ano 6 considerando risco de falha. Planejamento deve iniciar agora para execução antes do Ano 5.
3. **Custo do atraso** — cada mês de atraso na implementação do tap custa USD 56. Atrasar 2 anos resulta em VPL negativo (−USD 63) por exposição ao risco de falha no Ano 3.
4. **PRODIST DRP/DRC** — tabela completa de violações por barramento BT. 4 barramentos com violação: 2 em faixa crítica por sobretensão (Vmax até 1,079 pu, provavelmente causada pela GD fotovoltaica) e 2 em faixa precária. Exporta `prodist_drp_drc.csv`.

---

## Scripts de depuração

Os scripts `debug_*.py` foram usados durante o desenvolvimento para investigar comportamentos da API `dss-python` e podem ser deletados:

- `debug_bt.py` — diagnóstico do cálculo de tensão BT (identificou o bug de divisão por √3)
- `debug_bugs.py` — localização das cargas de `uc632607` e perfil do `trf_11_305a`
- `debug_pvapi.py` — atributos disponíveis em `IPVSystems`
- `debug_pvname.py`, `debug_pvname2.py` — problema de pontos no nome dos PVSystems
- `debug_raiz.py`, `debug_raiz2.py`, `debug_raiz3.py` — barramento raiz do alimentador
- `debug_trafo_novo.py` — diagnóstico do trafo novo em paralelo (identificou bug monofásico vs trifásico)

---

## Ordem de execução recomendada

```bash
uv run python 01_main_trabalho.py          # resultado principal
uv run python 04_perfil_tensao_trafos_gd.py
uv run python 04_pior_caso_duracao_degradacao.py
uv run python 05_remanejamento_15anos.py
uv run python 06_recondutoramento.py
uv run python 06_novo_trafo_paralelo.py
uv run python 05_regulador_crescimento_assimetrico.py
uv run python 07_expansao_gd_fluxo_n1.py
uv run python 07_perfil_tensao_balanco_sensibilidade.py
uv run python 07_analise_fp095.py
uv run python 07_arrhenius_breakeven_prodist.py
uv run python 05_montecarlo_despacho_gd.py
uv run python 02_impacto_tap_bt.py
```

Scripts de diagnóstico (executar individualmente se necessário):
```bash
uv run python 02_analisar_trafo.py
uv run python 02_analisar_linha.py
uv run python 02_horizonte_tap.py
uv run python 02_remanejamento_trafo.py
uv run python 03_diagnosticar_capcontrol.py
uv run python 03_testar_capcontrol.py
uv run python 03_mapear_reativo.py
uv run python 03_melhor_ponto_capacitor.py
uv run python 03_comparar_capcontrol.py
```

---

## Arquivos de saída gerados

- `resultados_consolidados.csv` — 45 métricas organizadas por categoria (Caso Base, Alternativas, GD, Monte Carlo, Longo Prazo)
- `prodist_drp_drc.csv` — tabela PRODIST com DRP e DRC por barramento BT (844 barramentos)
