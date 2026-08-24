# Ir más rápido: el segundo mercado

Nueve meses para pasar una evaluación es mucho tiempo para pedirle a alguien que
espere. Esto documenta la búsqueda de una ruta más rápida y lo que cuesta.

## Primero, una corrección

Una versión anterior reportó Ciel con "~59% de probabilidad en 9.5 meses". Ese
número muestreaba solo los **días en que la estrategia operó**, lo que asume en
silencio que todos los días calendario producen trade. Ciel opera 317 de 511
días. Modelado bien, con los días sin operar contados como cero:

```
Ciel solo en oro, 1 contrato:   18.6% de probabilidad, 18.9 meses
Ciel solo en oro, escalera 1->2: 38.6% de probabilidad, 13.1 meses
```

Bastante peor. La corrección importa más que la cifra original.

## Por qué más contratos no puede arreglarlo

La velocidad es `objetivo / edge diario`. La probabilidad la manda
`edge diario / volatilidad diaria`. Sumar contratos multiplica **las dos cosas**,
así que compra velocidad y la paga en probabilidad — la proporción no se toca.

La única forma de mejorar ambas es subir el edge *sin* subir la volatilidad en la
misma medida. Agregar un mercado **descorrelacionado** hace exactamente eso: el
edge suma lineal, la volatilidad suma en cuadratura.

## Buscando un segundo mercado

Se corrió el motor de Ciel sin cambios sobre ocho instrumentos. El recorte del
stop —el original limita la distancia a 15–40 puntos en oro a $10/punto— se
expresó como su equivalente en dólares, $150–400 de riesgo, y se convirtió de
vuelta a puntos para cada instrumento. Eso preserva el dimensionamiento
consciente de volatilidad en vez de eliminarlo.

Verificación de que el port es fiel: el oro reproduce el original exacto
(375 trades, 58.4% de aciertos, +$4,863, PF 1.17, mismo desglose anual).

| mercado | trades | aciertos | neto | PF | 2024 / 2025 / 2026 |
|---|---:|---:|---:|---:|---|
| **Trigo (ZW)** | 511 | 65.4% | **+$28,031** | **1.77** | +16,479 / +7,031 / +4,521 |
| **Oro (MGC)** | 375 | 58.4% | +$4,863 | 1.17 | +803 / +2,508 / +1,552 |
| Plata | 383 | 60.8% | +$3,533 | 1.10 | negativo en 2024 |
| Cobre | 373 | 54.4% | +$1,048 | 1.03 | negativo en 2025 |
| Petróleo, Nasdaq, S&P, Gas | — | — | todos negativos | 0.74–0.86 | — |

Solo oro y trigo son positivos en los tres años por separado.

**Su correlación de P&L diario es r = −0.004.** Independientes, que es lo que
hace que la combinación funcione en vez de ser solo el doble de exposición.

## La cartera

| plan | P(pasar) | meses (mediana) |
|---|---:|---:|
| solo oro, 1 contrato | 18.6% | 18.9 |
| solo oro, escalera 1→2 | 38.6% | 13.1 |
| **oro + trigo, 1 contrato c/u** | **97.6%** | **6.5** |
| oro + trigo, escalera 1→2 | 88.5% | 3.8 |
| **oro + trigo, 2 contratos c/u** | **81.7%** | **2.8** |
| oro + trigo, 3 contratos c/u | 67.6% | 1.5 |

El dimensionamiento es práctico con 1 contrato de cada uno — verificado, no
supuesto:

```
Trigo ZW    ATR mediano 3.00 pts -> stop 5.25 pts -> riesgo $262 por contrato entero
Oro MGC     ATR mediano 11.6 pts -> stop 20.3 pts -> riesgo $203 por micro
```

Los dos caen dentro de la banda $150–400 naturalmente con el contrato entero.

**Corrección (24-ago):** sí existe micro de trigo — **MZW** (500 bushels, $5/punto,
riesgo ~$26 con este stop) y **XW** mini (1.000 bushels, $10/punto). Una versión
anterior decía lo contrario. Con micros el dimensionamiento deja de ser un salto de
$262 y pasa a ser ajustable de a $26, lo que cambia el análisis de las cuentas
chicas: la fragilidad de "1 trade = 31% del aire" en la $25k es un artefacto de
usar el contrato grande, no una restricción real.

Queda por medir la **liquidez de MZW** — la cifra de 6.700–11.900 contratos/hora es
de ZW. También aparecen **KE** (trigo Kansas City) y **HRS** (Hard Red Spring) como
mercados vecinos sin analizar.

## ⚠️ Advertencia: el régimen reciente contradice estas cifras

Las probabilidades de arriba se calcularon sobre dos años de datos. Al correr el
motor verificado sobre los **últimos 60 días**:

| mercado | últimos 60 días | promedio 2 años |
|---|---|---|
| Trigo | 34t, 61.8%, PF **1.06** | 511t, 65.4%, PF **1.77** |
| Oro | 25t, 52.0%, PF **0.84** | 375t, 58.4%, PF **1.17** |

**Los dos están muy por debajo de su promedio, y el oro está en negativo.**

Si el régimen actual es el que muestran estos 60 días, las probabilidades reales
son bastante peores que 81.7%. Esto no invalida el resultado de diversificación
—que es aritmética— pero sí invalida usar los números de dos años como si fueran
la expectativa de hoy.

Es exactamente por esto que existe [`paper/`](../paper/): medir el régimen
vigente antes de arriesgar la cuota de una evaluación.

## Lo que no está establecido

El trigo nunca se operó. En concreto:

- **El edge decae año a año**: +$16,479 → +$7,031 → +$4,521, y los últimos 60
  días dan PF 1.06. 2024 es el 59% del total. Esa caída es la razón principal
  para no cargarle tamaño.
- **Se probaron ocho instrumentos y se eligió el mejor.** Es la trampa de
  comparaciones múltiples que este proyecto ya documentó. Ser positivo en los
  tres años por separado lo distingue de un golpe de suerte, pero no equivale a
  confirmación fuera de muestra.
- El costo se asume plano en $5.00/trade. La liquidez del trigo en la ventana
  operada es adecuada (6,700–11,900 contratos/hora, y el motor nunca toca la
  sesión nocturna delgada), pero su distribución de slippage no se midió como sí
  se midió la del oro. En el sistema real, el slippage fue el **82%** de la
  fricción — así que este es el supuesto más frágil.
- Velas horarias de Yahoo, como en todo el resto del análisis.

## La recomendación honesta

El resultado de diversificación es la parte robusta: dos mercados
descorrelacionados mejoran velocidad y probabilidad a la vez, y eso es
aritmética, no artefacto de backtest. La elección específica del trigo es un
candidato, no una conclusión — y los últimos 60 días le bajan el pulgar.

**Antes de poner tamaño:** correr `paper/ciel_paper.py` hacia adelante ~50 trades
por mercado, con el criterio de decisión escrito de antemano (está en
[`paper/README.md`](../paper/README.md)). Si el trigo sostiene PF ≥ 1.3, el plan
de 2+2 contratos tiene la base que dice tener. Si no, oro solo es una propuesta
del 18.6% a diecinueve meses, y eso no justifica el capital de nadie.
