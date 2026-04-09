# CLAUDE.md

Este arquivo fornece instruções para ferramentas de inteligência artificial quando trabalharem com o código deste repositório.

## Visão Geral do Projeto

O projeto realiza o planejamento da rede de distribuição de energia e a análise econômica para a CRELUZ (cooperativa de eletrificação rural no Brasil). O sistema simula um alimentador de 23,1 kV com 301 consumidores e 23 sistemas de geração distribuída fotovoltaica. O código avalia 8 alternativas de expansão considerando um crescimento de carga de 10% ao ano.

## Executando o Código

**Pipeline completo (todas as fases sequencialmente):**
```bash
python executar_tudo.py
O log de saída é salvo em: resultados/relatorio_tecnico_completo.txtScripts individuais:Os scripts separados estão localizados no diretório etapas/. Eles devem ser executados a partir da raiz do repositório e sempre seguir a ordem numérica do nome do arquivo (o script 01 gera arquivos base necessários para o script 02 e assim por diante).Bashpython etapas/01_simulacao_base.py
Ambiente Python:Bashpython -m venv .venv && source .venv/bin/activate
pip install dss-python pandas numpy
Não há framework de testes, não há configuração de linter e não há sistema de build.ArquiteturaFases do Pipeline (definidas em executar_tudo.py)Simulação base: Executa o OpenDSS para um horizonte de 3 anos, avalia todas as alternativas e salva os dados horários em arquivos CSV dentro da pasta resultados/.Estudos de diagnóstico: Lê os arquivos CSV gerados na fase 1 para identificar gargalos nas linhas e sobrecarga nos transformadores.Análise avançada: Realiza estudos específicos como dimensionamento de capacitores, despacho de GD via Monte Carlo, avaliação de reguladores de tensão, conformidade com o PRODIST e envelhecimento térmico de transformadores.Exportação e visualização: Gera a topologia da rede em formato GeoJSON, diagramas em formato SVG e gráficos de resumo.Módulos Principais (core/)MóduloFunçãoconfiguracao.pyCarrega o arquivo parametros.json uma única vez. Expõe os caminhos de pastas, limites técnicos, constantes financeiras e funções de inicialização do DSS. É a única fonte de verdade para todos os parâmetros do projeto.financeiro.pyExecuta os cálculos financeiros puros: faturamento, custo com perdas de energia, cálculo de penalidades do PRODIST (DRP/DRC) e cálculo de VPL e TIR. Não realiza chamadas ao simulador.dss_engine.pyInterface direta com o OpenDSS. Inicializa o Master.dss, executa o solver em modo diário e avança 24 intervalos de uma hora.data_processor.pyExtrai os dados após a simulação. Monta os DataFrames do Pandas com as tensões, fluxo das linhas, cargas dos transformadores e medidores. Salva os arquivos CSV.dss_extractors.pyContém as chamadas de API de baixo nível do OpenDSS para buscar dados brutos (tensão nas barras, corrente nos transformadores, etc).Fluxo de DadosPlaintextparametros.json → configuracao.py
                           ↓
                dss_engine.py (Solver OpenDSS)
                           ↓ (24 passos horários)
                dss_extractors.py → data_processor.py
                           ↓
                Arquivos CSV: tensões, linhas, transformadores, medidores
                           ↓
                financeiro.py (VPL, DRP/DRC, faturamento)
                           ↓
                Scripts da pasta etapas/ (risco, conformidade, recomendações)
                           ↓
                GeoJSON, arquivos SVG, relatorio_tecnico_completo.txt
DataFrames PrincipaisdfVoltages: Registra as tensões horárias por barra (média e baixa tensão). É usado para verificar as faixas do PRODIST (adequada, precária, crítica).dfTransformers: Registra a porcentagem de carregamento horário dos transformadores.dfLines: Registra o carregamento horário das linhas e a potência reativa.dfMeterByHour / dfEnergySummary: Registra a energia total e as perdas contabilizadas pelos medidores.Arquivos de Rede (dss/)O arquivo Master.dss é o ponto de entrada do OpenDSS. Ele inclui 14 sub-arquivos (condutores, transformadores, segmentos de linha, cargas e curvas). Não edite os sub-arquivos sem entender as dependências entre eles. O arquivo buscoords.csv fornece as coordenadas geográficas usadas para exportar os mapas.Configuração (parametros.json)Todos os parâmetros de simulação e os valores financeiros ficam neste arquivo. Isso inclui: tarifas de energia, limites de tensão, taxa de crescimento anual da carga, taxa de degradação dos painéis solares, taxa de desconto, as definições físicas das 8 alternativas (CAPEX e comandos DSS) e as barras alvo para análise.Contexto RegulatórioPRODIST Módulo 8: Padrão regulatório da ANEEL (Brasil) para a qualidade do nível de tensão. Os limites base são: adequado entre 0,93 e 1,05 pu. Tensões fora desta faixa geram indicadores de duração precária (DRP) e crítica (DRC).IEEE C57.91: Norma internacional que define o modelo de envelhecimento térmico de transformadores (fator de aceleração de envelhecimento de Arrhenius), usado para estimar a probabilidade de falha dos equipamentos sobrecarregados.
