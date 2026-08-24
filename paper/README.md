# Test forward en papel — Ciel sobre trigo y oro

## Para qué es

El backtest dice que el trigo tiene PF 1.77 y el oro PF 1.17, y que están
descorrelacionados (r = −0.004). Sobre esos números descansa el plan de la
cartera: dos mercados, 82% de probabilidad de pasar la evaluación en menos de
tres meses.

Pero los dos números salen de velas históricas que la estrategia **nunca operó**.
Esto corre la lógica idéntica hacia adelante sobre datos en vivo, registrando
cada decisión, para que el backtest se confirme o se caiga contra precio que no
ha visto.

No coloca órdenes ni toca ningún bróker. Papel puro.

## Uso

```bash
python ciel_paper.py --iniciar    # una vez: arranca el forward desde hoy
python ciel_paper.py              # un ciclo (correr cada hora)
python ciel_paper.py --stats      # reporte, sin tocar el estado
```

Correr repetido dentro de la misma hora es inofensivo: cada vela se procesa una
sola vez, indexada por su propio timestamp.

Para automatizarlo cada hora en horario de sesión (9:30–16:00 ET):

```bash
schtasks /create /tn "Ciel paper" /tr "python C:\Users\Usuario\orderflow-research\paper\ciel_paper.py" /sc hourly /st 09:30
```

## Verificación de fidelidad

Un forward que no reproduce el backtest no mide nada. Se comprobó corriendo el
motor del backtest sobre exactamente la misma ventana de 60 días:

| | paper | motor del backtest |
|---|---|---|
| Trigo | 34 trades, 61.8%, **+$197.97** | 34 trades, 61.8%, **+$198** |
| Oro | 25 trades, 52.0%, **−$423.64** | 25 trades, 52.0%, **−$424** |

Coincide al centavo.

Llegar ahí requirió cazar dos bugs propios, ambos del tipo que infla o desinfla
resultados sin avisar:

**1. Reentrada en la misma vela.** El motor original hace `continue` siempre
después de gestionar una posición, así que nunca abre en la vela donde cerró.
La primera versión caía y reabría de inmediato — reentrando justo después de un
stop, en plena contra. Fabricaba pérdidas que el backtest nunca toma:
trigo 40% de aciertos en vez de 62%.

**2. Mapa de tendencia con sesgo de anticipación.** El original clasifica cada
día usando el cierre del día **anterior** (`j = i-1`) y exige tres condiciones:
precio sobre MA20, MA20 sobre MA50, y MA20 subiendo contra 5 días atrás. La
primera versión usaba el cierre del propio día —información que a esa hora no
existe— y solo comparaba MA20 contra MA50. Esa versión laxa marca tendencia en
mercados que están picoteando y manda al motor a operar tendencia dentro del
ruido.

## Lo que ya se sabe, y es una advertencia

Al correr el motor verificado sobre los últimos 60 días, contra los promedios de
dos años:

| mercado | últimos 60 días | 2 años |
|---|---|---|
| Trigo | 34t, 61.8%, PF **1.06** | 511t, 65.4%, PF **1.77** |
| Oro | 25t, 52.0%, PF **0.84** | 375t, 58.4%, PF **1.17** |

**Los dos mercados están mucho peor que su promedio histórico, y el oro está en
negativo.** Es coherente con el deterioro año a año que ya se había marcado en
el trigo (+$16,479 → +$7,031 → +$4,521).

Esto importa para el plan: las probabilidades de 97.6% y 81.7% de
[docs/PORTFOLIO.md](../docs/PORTFOLIO.md) se calcularon sobre dos años de datos.
Si el régimen actual es el que muestran estos 60 días, las probabilidades reales
son bastante peores. **Ese es precisamente el motivo de correr este forward antes
de arriesgar la cuota de una evaluación.**

## Criterio de decisión, fijado ANTES de mirar

Objetivo: **~50 trades cerrados por mercado** (unas 6–8 semanas al ritmo
histórico).

- **Sigue en pie** si el trigo sostiene PF ≥ 1.3 con ≥ 50 trades. Ahí el plan de
  la cartera tiene la base que dice tener.
- **Se cae** si el trigo queda bajo PF 1.1, o si el oro sigue bajo 1.0. Con eso
  la cartera no justifica la cuota de la evaluación y hay que volver al
  laboratorio.
- **Zona gris** entre 1.1 y 1.3: no alcanza para arriesgar capital. Seguir
  midiendo.

Escribir el criterio antes es lo que impide racionalizar el resultado después.
Es la lección de OF-MGC, donde 13 trades al 69% se leyeron como permiso para
operar en vivo y terminaron en 38.7% con dinero real.

## Salidas

- `paper_trades.csv` — un registro por evento (ABRE / CIERRE) con precio, motivo,
  P&L, lado, stop y objetivo
- `paper_state.json` — posición abierta y acumulados; escritura atómica, un corte
  a media escritura no lo corrompe

## Supuestos declarados

- **Costo:** $5.00/trade fijo. El slippage del trigo no se midió como sí se midió
  el del oro. En el sistema real medido, el slippage fue el 82% de la fricción,
  así que este supuesto es el más frágil del test.
- **Datos:** velas horarias de Yahoo. Iguales a las del backtest, verificado:
  928 velas en el período común, cero diferencias entre el feed de 60 días y el
  de 730.
- **Ejecución:** entradas y salidas al cierre de la vela. El SL se comprueba
  antes que el TP, así que una vela que contiene ambos se resuelve como pérdida —
  no se sabe cuál llegó primero y suponer el peor caso es lo honesto.
- **Sesión:** el motor opera 9:30–16:00 ET. En trigo eso cae en las horas de
  6,700–11,900 contratos por hora y nunca toca la sesión electrónica delgada.
  La **gestión** de posiciones abiertas sí corre en velas nocturnas, igual que en
  el backtest: un stop puede tocarse de madrugada con poco volumen.
