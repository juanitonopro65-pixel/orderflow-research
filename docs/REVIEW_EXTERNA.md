# Review externa (24-ago-2026)

Una developer revisó el repositorio completo y devolvió una crítica técnica. Este
documento la registra, marca qué se midió a raíz de ella y qué queda abierto.
Varias observaciones son correcciones reales al análisis publicado.

## El diagnóstico central

> "Tenés un plan de negocio documentado y un simulador en papel, pero no tenés el
> auto para manejarlo en Lucid."

El marco que propuso, y que es el correcto:

```
CEREBRO  → qué hacer (comprar/vender, stop, target)
PAPEL    → practicar sin bróker (simula en CSV)
AUTO     → ejecutar de verdad en la cuenta
```

Ciel tiene cerebro y papel. **No tiene auto.** OF-MGC sí lo tiene
(`agus_ejecutor_of_mgc.py`) — y es justamente la estrategia que perdió.

| pieza | estado |
|---|---|
| Idea de estrategia (Ciel: tendencia + fade) | ✅ medida en backtest |
| Análisis de la evaluación $150k | ✅ `backtest_150k_ciel.py` |
| Portafolio oro + trigo | ✅ `docs/PORTFOLIO.md` |
| Paper forward | ✅ `paper/ciel_paper.py` |
| Bridge Quantower | ✅ `src/quantower_bridge.py` |
| **Ejecutor Ciel en vivo** | ❌ **no existe** |
| **Motor único compartido** | ❌ código duplicado entre paper y backtest |
| **Reglas de Lucid en código** | ❌ consistencia, flat 4:45, escalera |
| **Validación con fills reales** | ❌ Ciel nunca operó, ni en demo |

## ✅ Medido a raíz de su review: el flat de las 4:45 PM

Su observación más importante: Lucid exige posición plana ~16:45 ET, pero el
motor mantiene posiciones por el timeout de 8 velas horarias — cerrando de hecho
a las 20:00, 23:00 o 02:00. **El repo estaba reportando P&L que una cuenta Lucid
no habría podido obtener.**

Medido, forzando flat a las 16:40 ET y prohibiendo entradas después de las 15:00:

| mercado | sin flat | con flat | efecto |
|---|---|---|---|
| Oro | 375t, +$4,863, PF 1.17 | 355t, +$3,774, PF **1.16** | −22% del profit |
| Trigo | 511t, +$28,031, PF 1.77 | 512t, +$26,183, PF **1.77** | −7% del profit |

**El edge sobrevive.** El profit factor casi no se mueve, lo que indica que los
trades cortados eran aproximadamente neutros, no los ganadores. Pero la cifra
correcta para una cuenta Lucid es la de la derecha, no la de la izquierda.

## Lo que trajo y todavía NO está modelado

### La regla de consistencia — el hueco más grande

Lucid limita cuánto puede aportar un solo día al total del ciclo: **50% en la
evaluación Flex, 40% en la cuenta fondeada**. Ningún análisis de este repositorio
la modela. Su propuesta:

```python
if day_pnl + expected_win > 0.40 * cycle_profit:
    no_abrir_hoy()
```

Importa más de lo que parece: con trades de $200–400, un día bueno puede bloquear
el payout. Todas las probabilidades publicadas (97.6%, 81.7%) ignoran esta
restricción, así que son **cotas superiores**.

### Sesgo de selección en el trigo

ZW salió de "probar 8 mercados y elegir el mejor". El repositorio ya documenta
esa trampa en `METHOD.md` y aun así la cometió. Su propuesta, correcta:

1. Correr el mismo motor sobre **KE=F** (Kansas City, liquidez 46% de ZW)
2. Medir correlación diaria KE vs MGC
3. Reemplazar ZW solo si KE es positivo en 3 años **y** en rolling de 60 días

### ✅ Medido a raíz de su review: KE le gana a ZW, pero es el mismo trade

`analysis/ke_wheat.py` corre el motor sobre KE con oro y ZW como controles. Los
controles reproducen exacto lo publicado (oro 375t/+$4,863/PF 1.17; ZW
511t/+$28,031/PF 1.77), así que el port es fiel.

| mercado | trades | aciertos | neto | PF | maxDD | 2024/2025/2026 |
|---|---:|---:|---:|---:|---:|---|
| **KE** (Kansas City) | 531 | 66.5% | **+$36,575** | **1.94** | **$3,101** | +18,835 / +11,908 / +5,832 |
| ZW (Chicago) | 511 | 65.4% | +$28,031 | 1.77 | $3,752 | +16,479 / +7,031 / +4,521 |

KE gana en las tres dimensiones: profit factor, drawdown máximo y pendiente de
decaimiento. Y su maxDD de $3,101 deja más margen bajo el MLL de $4,500.

**Pero la correlación mata la idea de sumarlos:**

```
KE  vs ZW    r = +0.562     <- el MISMO trade con otro ticker
KE  vs Oro   r = +0.063     <- independientes
ZW  vs Oro   r = -0.019     <- independientes
```

Con r = 0.56 entre los dos trigos, correr ambos dobla el riesgo sin repartirlo.
**KE debería REEMPLAZAR a ZW, no acompañarlo.** El par sigue siendo dos mercados:
oro + un trigo.

Advertencia que su propio punto sobre sesgo de selección obliga a hacer: ya van
**nueve** mercados probados. Que KE le gane a ZW puede ser ruido. Antes de
cambiar hay que verlo aguantar en rolling de 60 días, no solo en el total.

### Gate de régimen automático

Hoy `paper/` es un reporte manual. Su propuesta lo convierte en interruptor:

```python
# rolling sobre los ultimos 50 trades cerrados, por mercado
if pf_rolling_50 < 1.1:
    no_operar_ese_mercado_hasta_que_mejore()
```

Con trigo en 1.06 y oro en 0.84 en los últimos 60 días, esto apagaría los dos hoy.

### Otras piezas

- **ADX(14) > 22–25 en el diario** como filtro extra de tendencia. Nota justa:
  el efficiency ratio ya se probó y falló; ADX es el candidato que **no** se probó.
- **Escalera en código, no en la cabeza**: 1 MGC + 1 ZW → 2+2 con colchón ≥ $1,500
  sobre el piso trailing; bajar si el DD intradía supera el umbral.
- **Freno diario −$400** (≈1.5–2 stops) como guarda dura, coherente con el MLL de
  $4,500. El repositorio ya midió que un freno de $300 sube el neto de +$4,863 a
  +$5,744 cortando 12 días malos.
- **No re-optimizar la zona 50/50.** v3.4 es la versión; volver a barrer 20/30/40
  es la trampa de grid search que el propio repositorio documentó.

## El paso que falta en la secuencia

```
paper 50+ trades  →  DEMO Lucid con ejecutor  →  eval $150k
```

Su argumento, que es el correcto: **saltarse la demo es repetir el 69% dry → 38.7%
live de OF-MGC.** El paper responde "¿la estrategia seguiría ganando hoy?"; solo
el ejecutor en demo responde "¿la cuenta ejecutó bien lo que el cerebro dijo?".
En julio falló exactamente esa segunda pregunta.

Esto contradice la recomendación actual del README de ir directo a la $150k, y
tiene razón: ese análisis de sensibilidad medía cuánto slippage aguanta el plan,
no si el ejecutor traduce correctamente las señales a órdenes. Son dos riesgos
distintos y yo había colapsado uno sobre el otro.

## Criterios de validación que propuso añadir

Los actuales están en `paper/README.md` (trigo PF ≥ 1.3 con ≥ 50 trades). Suma:

| regla | motivo |
|---|---|
| Demo 20 trades, WR y PF dentro de ±15% del paper | fills reales |
| Bootstrap de la eval con los últimos **120 días**, no 2 años | régimen actual |
| Peor DD simulado < $3,500 (margen bajo los $4,500) | no pasar "de milagro" |
| Consistencia simulada: ningún día > 45% del profit acumulado | payout de Lucid |

## Lo que dijo NO tocar

- **OF-MGC** — muerta; no mezclar con Ciel en la misma cuenta
- **Más filtros de order flow** — no predice dirección (ya medido acá)
- **Grid search de parámetros** — solo si hay meseta fuera de muestra, no un pico
- **Micro trigo (MZW)** — liquidez ~1% de ZW; el repositorio ya lo descartó
- **Prometer "dinero constante"** — el edge decae (+$16k → +$7k → +$4.5k/año).
  Lo constante es el **proceso**, no el P&L mensual.

## Arquitectura que propuso

```
          ciel_engine.py (único)
                  |
   ┌──────────────┼──────────────┐
   ▼              ▼              ▼
backtest_eval  ciel_paper   ejecutor_lucid
(simula eval)  (forward)    (órdenes reales)
   └──────────────┼──────────────┘
                  ▼
           risk_lucid.py
           · escalera 1→2
           · consistencia 40%
           · flat 16:40 ET
           · freno −$400/día
           · gate de régimen (50t)
```

Hoy el paper duplica la lógica del backtest. Ya costó caro: los dos bugs que hubo
que cazar para que el paper reprodujera el backtest (reentrada en la misma vela,
mapa de tendencia con anticipación) no habrían existido con un motor único.

## Plan por fases

```
FASE 1 — MEDIR (0 costo, 6-8 semanas)     paper/ corriendo, decisión con regla fija
FASE 2 — UNIFICAR (1-2 semanas)           ciel_engine.py + flat 4:45 en el motor
FASE 3 — SIMULAR LUCID (pocos días)       sim_eval_lucid.py: meta/MLL/consistencia/escalera
FASE 4 — EJECUTOR (1-2 semanas)           agus_ejecutor_ciel.py + demo Lucid 20+ trades
FASE 5 — EVAL (solo si 1 y 4 pasan)       comprar $150k, 1+1, subir a 2+2 con colchón
```

## Balance

Su crítica es correcta en lo central: el repositorio documenta investigación
honesta y no tiene con qué operarla. Y su hallazgo del flat 4:45 obligó a corregir
cifras publicadas.

Dos cosas donde el repositorio ya tenía razón y ella lo confirmó: no re-optimizar
parámetros, y no prometer ingreso constante cuando el edge decae año a año.

Lo que queda pendiente y es lo más urgente de su lista: **modelar la regla de
consistencia**, porque todas las probabilidades publicadas la ignoran.
