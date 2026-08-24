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
