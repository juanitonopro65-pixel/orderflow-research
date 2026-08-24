# orderflow-research

Sistema de trading algorítmico sobre futuros: puentes de datos en vivo contra la
plataforma del bróker, motor de señales de order flow, simulador en papel,
ejecutor con guardas, y los backtests que decidieron qué se desplegaba.

Construido solo. Operó **dinero real** sobre futuros de oro micro (MGC) a través
de Quantower.

**Perdió plata. Este repositorio documenta exactamente por qué, con el registro
crudo incluido para que cada cifra se pueda recalcular desde la fuente.**

---

## Dos estrategias, resultados opuestos

Acá viven dos sistemas distintos. Confundirlos es el error más fácil de cometer:

- **OF-MGC** — scalp de order flow. Operó dinero real. **Perdió $430.20.**
- **Ciel** — seguimiento de tendencia + fade en rango. **Nunca operó dinero real.**
  Expectativa positiva en backtest (+$12.97/trade, rentable en cada uno de tres
  años por separado). Es la estrategia pensada para una cuenta grande.

| | OF-MGC | Ciel |
|---|---|---|
| trades por día | ~9 | ~1.2 |
| duración | 25 minutos | hasta 8 horas |
| por trade | **−$5.74** (real) | **+$12.97** (backtest) |
| aciertos | 38.7% | 58.4% |
| profit factor | < 1 | 1.17 |

---

## Lo que pasó con dinero real

| | trades | aciertos | neto |
|---|---|---|---|
| Dry-run — *la muestra con la que se decidió operar* | 13 | 69.2% | **+$288.00** |
| **En vivo** (20–30 jul 2026) | **75** | **38.7%** | **−$430.20** |

```bash
python analysis/live_results.py     # recalcula cada cifra de docs/RESULTS.md
```

Dos cosas antes de seguir, porque las dos son errores que sobreviven si nadie
los escribe:

**1. El registro estaba contaminado.** Cuatro filas de prueba unitaria (precio
de fixture `entry 4000.0`; una con el timestamp literalmente en `t`) estaban
dentro del ledger en vivo e inflaban el resultado en $157. Una primera lectura
reportó −$273.20. La cifra real es −$430.20.

**2. El log simulado y la realidad se contradicen brutalmente.** Del 27 al 30 de
julio el log de señales suma **+$12,062**; esos mismos cuatro días la cuenta real
perdió **$370**. El simulador contaba el mismo movimiento hasta diez veces, y
registraba ganadores de +$600 que llegaban al objetivo en cinco minutos —sesenta
puntos de oro en cinco minutos, que no ocurre—.

---

## Por qué perdió — el mecanismo real

Se diseñó como scalp: stop de 6 puntos (−$60), objetivo de 9 (+$90), salida
forzada a los 25 minutos. Eso es un payoff 1:1.5 que necesita 40% de aciertos.

Lo que corrió no era ese sistema:

```
motivo de salida   TIEMPO(26m)=35   SL=26   TIEMPO(25m)=5   TP=9
llegó al objetivo    9 / 75  (12%)
cerró por reloj     40 / 75  (53%)
```

**Solo el 12% de los trades llegó al objetivo.** El reloj cerró más de la mitad
donde el precio estuviera. Así el payoff real no fue 1:1.5 sino **1.23:1**, que
necesita **44.9%** de aciertos. El sistema entregó 38.7%.

La brecha son 6.2 puntos, y es un problema de **geometría**, no de fuerza de la
señal. Un objetivo que el reloj nunca deja alcanzar no es un objetivo.

### Lo que *no* lo explica

Medido, no supuesto:

- **Comisión.** $0.60 ida y vuelta, no los $2.60 que cobraba el simulador. Es el
  18% de la fricción. El costo real es $3.39/trade y el 82% es slippage.
- **El slippage de entrada es estructural.** El ejecutor ancla el bracket al
  ask/bid de referencia y después llena a mercado, así que cualquier diferencia
  desplaza la distancia real al objetivo 1:1. Un tick, cada trade.
- **Entrar con órdenes límite sería peor.** Medido: la selección adversa elimina
  los trades que nunca vuelven, que son los buenos.
- **El P&L bruto antes de costos ya era negativo.** Los costos hicieron que un
  sistema perdedor perdiera más rápido. No causaron la pérdida.

---

## El trigo: el segundo mercado

La velocidad para pasar una evaluación es `objetivo / edge diario`. La
probabilidad la manda `edge / volatilidad`. Sumar contratos multiplica **las
dos**, así que compra velocidad y la paga en probabilidad. Lo único que mejora
ambas es agregar un mercado **descorrelacionado**: el edge suma lineal, la
volatilidad suma en cuadratura.

Se corrió el motor de Ciel **sin cambios** sobre ocho instrumentos, traduciendo
el recorte del stop (15–40 puntos en oro a $10/punto) a su equivalente en riesgo,
$150–400, para cada mercado. El oro reproduce el original exacto, que es la
prueba de que el port es fiel.

| mercado | trades | aciertos | neto | PF | 2024 / 2025 / 2026 |
|---|---:|---:|---:|---:|---|
| **Trigo (ZW)** | 511 | 65.4% | **+$28,031** | **1.77** | +16,479 / +7,031 / +4,521 |
| **Oro (MGC)** | 375 | 58.4% | +$4,863 | 1.17 | +803 / +2,508 / +1,552 |
| Plata | 383 | 60.8% | +$3,533 | 1.10 | negativo en 2024 |
| Cobre | 373 | 54.4% | +$1,048 | 1.03 | negativo en 2025 |
| Petróleo, Nasdaq, S&P, Gas | — | — | todos negativos | 0.74–0.86 | — |

Solo oro y trigo son positivos en los tres años por separado. Su correlación de
P&L diario es **r = −0.004**: independientes.

Y el dimensionamiento sale natural, verificado y no supuesto:

```
Trigo ZW   ATR mediano 3.00 pts -> stop 5.25 pts -> riesgo $262 por contrato entero
Oro MGC    ATR mediano 11.6 pts -> stop 20.3 pts -> riesgo $203 por micro
```

Los dos caen dentro de la banda $150–400. No hace falta micro de trigo.

### ⚠️ Pero el régimen reciente contradice esas cifras

Corriendo el mismo motor sobre los **últimos 60 días**:

| mercado | últimos 60 días | promedio 2 años |
|---|---|---|
| Trigo | 34t, 61.8%, PF **1.06** | 511t, 65.4%, PF **1.77** |
| Oro | 25t, 52.0%, PF **0.84** | 375t, 58.4%, PF **1.17** |

Los dos muy por debajo de su promedio, y el oro en negativo. Coherente con el
deterioro año a año del trigo. **Las probabilidades de abajo se calcularon sobre
dos años y no son la expectativa de hoy.** Por eso existe [`paper/`](paper/):
medir el régimen vigente antes de pagar nada.

## Qué cuenta comprar, y en qué orden

| cuenta | plan | P(pasar) | meses | fragilidad |
|---|---|---:|---:|---|
| $25k (aire $1,500) | oro+trigo 1x c/u | **80.8%** | **0.8** | 1 trade = 31% del aire |
| $25k (aire $822) | oro+trigo 1x c/u | 55.1% | 0.6 | 1 trade = **57%** del aire |
| $150k (aire $4,500) | oro+trigo 1x c/u | **97.8%** | 6.5 | 1 trade = 10% del aire |
| $150k (aire $4,500) | oro+trigo 2x c/u | 81.6% | 2.8 | 1 trade = 21% del aire |

Dos conclusiones prácticas:

1. **El aire de la evaluación importa más que su tamaño.** La misma estrategia
   pasa de 80.8% a 55.1% solo por bajar el colchón de $1,500 a $822. Al comprar,
   comparar el *drawdown* permitido y si es estático o con trailing — no el
   número grande del título.
2. **Una evaluación pagada no es un entorno de pruebas.** No se "prueba" en ella:
   se pasa o se pierde la cuota. Probar es lo que hace `paper/`, gratis. Lo que
   sí compra una cuenta chica, y el papel no puede dar, son **fills reales y
   slippage real** — que fue exactamente donde murió OF-MGC (dry-run 69% →
   en vivo 38.7%).

### ¿Justifica el desvío por la cuenta chica?

El único argumento para comprar una $25k antes es medir slippage barato. Así que
la pregunta correcta es cuánto slippage aguanta el plan antes de romperse
(evaluación $150k, 2 contratos de cada uno):

| costo/trade | PF trigo | PF oro | P(pasar) | |
|---:|---:|---:|---:|---|
| $5.00 | 1.77 | 1.17 | **81.7%** | supuesto del backtest |
| $10.00 | 1.68 | 1.10 | 75.5% | |
| $15.00 | 1.60 | 1.04 | 67.4% | ≈ lo medido en oro, escalado |
| $20.00 | 1.52 | 0.97 | 58.4% | pesimista |
| $30.00 | 1.37 | 0.86 | **38.3%** | acá se rompe |

Referencia: en OF-MGC el costo real medido fue **$3.39 sobre un stop de $60**, o
sea 5.6% del riesgo. Aplicado a los $262 de riesgo del trigo, eso son ~$15/trade
— donde el plan todavía da 67%. Para romperlo, el slippage tendría que ser el 11%
del riesgo, el doble de la tasa proporcional ya medida.

**Conclusión: el riesgo de slippage no justifica pagar una segunda cuota.** El
plan se degrada de forma gradual, no cae por un precipicio. Ir directo a la $150k
es más rápido (2.8 meses contra 0.8 + 2.8 = 3.6), cuesta una cuota en vez de dos,
y da la misma probabilidad.

### Cuánto tamaño en la $150k

| plan | P(pasar) | meses |
|---|---:|---:|
| 1 contrato de cada uno | **97.6%** | 6.5 |
| **escalera 1 → 2 con colchón de $1,500** | **88.5%** | **3.8** |
| 2 contratos de cada uno | 81.7% | 2.8 |

La escalera es el mejor canje: arranca chico para que la varianza temprana no
mate la cuenta, y sube cuando ya hay ganancia que la absorba.

Con eso, la secuencia que el dato respalda:

```
1. AHORA        paper/ corre gratis, ~6 semanas, ~50 trades por mercado
2. CRITERIO     trigo PF >= 1.3 y oro >= 1.0   (escrito antes de mirar)
3. SI PASA      la de $150k DIRECTO, escalera 1->2 con colchon de $1.500
                (88.5%, ~3.8 meses, una sola cuota)
4. SI NO PASA   no se compro nada. Costo total: $0
```

Sin escalón intermedio: la cuenta de $25k costaría una segunda cuota y ~10 meses
más de calendario para comprar información —el slippage— que el análisis de
sensibilidad muestra que no es el riesgo dominante.

Lo que **no** cambia: no se compra nada hasta que el papel valide el régimen
actual. Los últimos 60 días dan trigo 1.06 y oro 0.84. Seis semanas de espera
cuestan $0; comprar hoy y equivocarse cuesta la cuota.

## Estructura

```
src/         el sistema: ejecutor, simulador, backtests
data/        evidencia cruda: 34,276 velas de 1 minuto con order flow,
             7,657 señales registradas, el ledger completo de trades reales
analysis/    scripts que regeneran cada cifra publicada
paper/       test forward en papel de Ciel sobre trigo y oro
docs/        arquitectura, resultados y el registro de investigación
```

- [docs/RESULTS.md](docs/RESULTS.md) — cada número y cómo se obtuvo
- [docs/CIEL.md](docs/CIEL.md) — la estrategia que nunca se desplegó
- [docs/PORTFOLIO.md](docs/PORTFOLIO.md) — cómo acelerar: el segundo mercado
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — cómo está construido
- [docs/METHOD.md](docs/METHOD.md) — hipótesis probadas y descartadas, y las
  trampas de medición que produjeron falsos positivos

## Estado

Detenido desde el 30 de julio de 2026. Nada acá es una recomendación de operar,
y los resultados argumentan en contra de desplegar OF-MGC como está.

La ingeniería es reutilizable; la estrategia todavía no es rentable.
