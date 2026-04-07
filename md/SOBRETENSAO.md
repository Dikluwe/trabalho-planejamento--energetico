# Achado: Sobretensões por GD Fotovoltaica — Não Conformidade PRODIST

**Alimentador:** 1_REDE2_1 — CRELUZ  
**Script:** `08_sobretensao.py`  
**Referência normativa:** PRODIST Módulo 8, Seção 8.1, Tabela 5 (BT 380/220V)

---

## Resumo

A análise de qualidade de tensão identificou 4 barramentos de baixa tensão em não conformidade com o PRODIST no caso base (Ano 1, carga nominal). A causa é a geração fotovoltaica local com relação geração/carga de 23× em dois pontos de conexão. A cooperativa está sujeita a compensação financeira devida aos consumidores afetados.

---

## Barramentos com violação

| Barramento | Vmin (pu) | Vmax (pu) | DRP (%) | DRC (%) | Faixa | Horas em violação |
|---|---|---|---|---|---|---|
| `uc1607347` | 0,985 | 1,079 | 0,60 | 3,57 | crítica | 7h (11h–17h) |
| `bt56881` | 0,985 | 1,076 | 1,19 | 2,98 | crítica | 7h (11h–17h) |
| `uc606147` | 0,986 | 1,055 | 2,38 | 0,00 | precária | 6h (11h–16h) |
| `bt71761` | 0,987 | 1,050 | 0,60 | 0,00 | precária | 1h (15h) |

Faixas PRODIST Tabela 5 — BT 380/220V:
- **Adequada:** 0,921–1,050 pu
- **Precária:** 1,050–1,061 pu (DRP — compensação com k₁=3)
- **Crítica:** >1,061 pu (DRC — compensação com k₂=7)

---

## Causa identificada

### PVSystem no ponto de conexão com carga mínima

`PVSystem.gd.rs.001.675.269` (50 kW nominal) está conectado diretamente no barramento `uc1607347`, que alimenta dois medidores com carga total de 2,16 kW.

| Parâmetro | Valor |
|---|---|
| Potência nominal da GD | 50 kW |
| Carga local total | 2,16 kW (2 × 1,08 kW) |
| Relação GD/carga | **23,1×** |
| Potência excedente típica (hora 15) | ~47,8 kW |
| Fator de potência dos inversores | 0,92 capacitivo |

O mesmo padrão, em menor escala, ocorre em `uc606147` com `PVSystem.gd.rs.000.371.786`.

### Confirmação experimental

Desabilitando todos os PVSystems (`Disable PVSystem.*`), todos os barramentos retornam à faixa adequada em todas as horas (0,976–0,999 pu). A sobretensão é inteiramente causada pela GD fotovoltaica.

### Perfil temporal

A sobretensão ocorre exclusivamente durante as horas de geração solar intensa:

```
Hora  GD total   uc1607347   Status
  10   210 kW     1,032 pu   adequada
  11   335 kW     1,062 pu   CRÍTICA
  12   370 kW     1,069 pu   CRÍTICA
  13   395 kW     1,076 pu   CRÍTICA
  14   395 kW     1,075 pu   CRÍTICA
  15   400 kW     1,079 pu   CRÍTICA (pico)
  16   388 kW     1,077 pu   CRÍTICA
  17   304 kW     1,059 pu   CRÍTICA
  18   174 kW     1,026 pu   adequada
```

---

## Impacto financeiro estimado

### Compensação PRODIST devida

Usando a fórmula do Módulo 8, item 29, para o consumidor `uc1607347`:

```
DRC = 36 leituras críticas / 1.008 leituras totais = 3,57%
DRC_limite = 0,5%
k₂ = 7 (BT)

Comp = (DRC - DRC_lim) / 100 × k₂ × E_consumidor × TUSD
     = (3,57 - 0,5) / 100 × 7 × E_mensal × 90 USD/MWh
```

Com consumo mensal estimado de `uc1607347` de ~0,065 MWh (2,16 kW × 30 dias × fração de uso):

```
Comp ≈ 0,0307 × 7 × 0,065 × 90 ≈ USD 1,26/mês por consumidor
```

Valor unitário pequeno, mas representa **não conformidade regulatória documentada** que a ANEEL pode identificar em auditoria.

---

## Eficácia das mitigações testadas

| Estratégia | Vmax uc1607347 | Resolve? | Δ perdas |
|---|---|---|---|
| FP 0,90 (mais reativo) | 1,083 pu | NÃO — piora | +1,1 kWh/dia |
| FP 0,92 (atual) | 1,079 pu | NÃO | — |
| FP 0,95 | 1,072 pu | NÃO | −1,0 kWh/dia |
| FP 1,00 (sem reativo) | 1,047 pu | **SIM** | +3,2 kWh/dia |

FP 1,00 resolve a sobretensão mas o problema não é o reativo — é a potência ativa excedente de ~48 kW que não tem para onde ir. O ajuste de FP reduz a tensão porque elimina a componente reativa, mas a componente ativa continua elevando a tensão.

---

## Recomendações

### Imediata (sem custo de equipamento)

**Curtailment por tensão nos inversores:** configurar os inversores de `gd.rs.001.675.269` e `gd.rs.000.371.786` para limitar a potência ativa quando a tensão no ponto de conexão ultrapassar 1,045 pu. A maioria dos inversores modernos suporta essa função via parâmetro de configuração.

Impacto: perda de geração estimada de 5–10% (horas 11–17 com limitação), equivalente a ~15–20 kWh/dia de geração não aproveitada.

### Médio prazo (planejamento)

**Reconfiguração da carga:** avaliar a possibilidade de conectar cargas adicionais no barramento `uc1607347` ou ramais adjacentes para absorver o excedente local. Um consumidor de 10–15 kW nesse barramento eliminaria a sobretensão sem perda de geração.

**Redimensionamento da GD:** ao renovar os inversores ou módulos, recalibrar a potência instalada considerando a carga local. Uma GD de 10–15 kW seria adequada para a carga de 2,16 kW com margem de exportação segura.

### Longo prazo

**Armazenamento local:** bateria de 30–50 kWh em `uc1607347` absorveria o excedente solar e o restituiria à noite, eliminando a sobretensão e reduzindo a importação noturna da subestação.

---

## Relação com as alternativas avaliadas

Esta sobretensão é **independente do problema do `trf_6_4910a`** — está em ramais distintos da rede e não é resolvida pelo tap proposto. São dois problemas distintos que requerem intervenções distintas:

| Problema | Localização | Causa | Intervenção |
|---|---|---|---|
| Sobrecarga do trafo | trf_6_4910a / ramal uc632607 | Crescimento de carga | Tap wdg=1 tap=1,0333 |
| Sobretensão BT | uc1607347 / bt56881 | GD com carga mínima local | Curtailment por tensão |

O ajuste de FP de 0,92 para 0,95 recomendado para toda a rede reduz levemente a sobretensão (1,079 → 1,072 pu) mas não é suficiente para eliminar a violação PRODIST. O curtailment é necessário especificamente nesses dois pontos.

---

## Notas metodológicas

- Tensão calculada como `vpu = VMagAngle[0] / (kVBase × 1000)` — kVBase já é tensão de fase nesta rede (0,2194 kV ≈ 380V/√3)
- DRP e DRC extrapolados de 24 leituras horárias para 1.008 leituras mensais de 10 min (fator 42×)
- Causa confirmada por simulação com e sem GD — diferença de até 9,0% no ponto de pico
