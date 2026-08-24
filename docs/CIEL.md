# Ciel — la otra estrategia

**Esta no es la que perdió plata.** En este repositorio viven dos estrategias
separadas y tienen perfiles opuestos:

| | OF-MGC | Ciel |
|---|---|---|
| qué es | scalp de divergencia de order flow | tendencia + fade en rango |
| duración | 25 minutos | hasta 8 horas |
| trades por día | ~9 | ~1.2 |
| operó dinero real | sí | **nunca** |
| por trade | **−$5.74** (en vivo) | **+$12.97** (backtest) |
| aciertos | 38.7% | 58.4% |
| profit factor | < 1 | 1.17 |

OF-MGC se desplegó y perdió $430. Ciel se guardó *antes* de desplegarse, con el
argumento de que el micro de oro es un instrumento demasiado grueso para una
cuenta de $25k — sus stops son de 15 a 40 puntos ($150–400), que sobre $25k son
tres balas. Ese razonamiento es la razón por la que se reconsidera para $150k.

## El edge medido

`src/backtest_combo_eval.py` sobre GC=F, dos años, un trade a la vez, con $5.00
de costo descontado por operación:

```
TREND   161 trades   55.9% aciertos   +$3,364   PF 1.20   +$20.90/trade
FADE    214 trades   60.3% aciertos   +$1,498   PF 1.13    +$7.00/trade
COMBO   375 trades   58.4% aciertos   +$4,863   PF 1.17   +$12.97/trade
```

Positivo en cada año por separado — el test que OF-MGC reprobó:

| año | trades | aciertos | neto |
|---|---:|---:|---:|
| 2024 | 133 | 56.4% | +$803 |
| 2025 | 143 | 62.2% | +$2,508 |
| 2026 | 99 | 55.6% | +$1,552 |

Las dos mitades son excluyentes por régimen: trend solo dispara en días
direccionales, fade solo en días laterales, así que nunca compiten por el mismo
capital y la cifra combinada no está contando doble. El motor comprueba el stop
antes que el objetivo dentro de la misma vela, que es la resolución conservadora.

## ¿Puede pasar una evaluación de $150k?

Objetivo +$9,000, pérdida máxima $4,500 con trailing al cierre. El backtest de un
solo camino dice "pasa con 2 contratos en 11.5 meses" — pero eso es **una sola
tirada**. Haciendo bootstrap de la distribución diaria real sobre 6,000
simulaciones:

| plan | P(pasar) | meses (mediana) |
|---|---:|---:|
| 1 contrato fijo | 18.6% | 18.9 |
| escalera 1 → 2 con colchón de $1,500 | 38.6% | 13.1 |

Solo con oro, es una propuesta pobre. La ruta que sí funciona pasa por agregar un
segundo mercado descorrelacionado — está en [PORTFOLIO.md](PORTFOLIO.md).

### Lo que no funciona acá

Un freno de pérdida diaria — la guarda que sí ayudó medible a OF-MGC (PF 1.15 →
1.21) — no hace casi nada por Ciel. A $450 y $600 se activa en **cero de 317
días**. La razón es estructural: Ciel toma 1.2 trades por día, así que un freno
diario no tiene trades posteriores que impedir. No puede parar el trade que lo
rompe, solo los que vienen después — y normalmente no hay ninguno.

Un freno de $300 sí ayuda algo (+$4,863 → +$5,744 crudo, cortando 12 días malos),
pero es un efecto chico, no una solución.

## Qué es y qué no es

**Es:** una estrategia con expectativa positiva, consistente en tres años, cuyos
dos componentes funcionan por separado.

**No es:** algo probado. Ciel nunca llenó una orden real. En concreto:

- El backtest corre sobre velas horarias de GC=F desde Yahoo, un proxy del MGC.
  El recorrido dentro de la vela es desconocido; la resolución es conservadora
  pero sigue siendo un supuesto.
- El forward de su configuración con gate (A+) devolvió **−$231 en 7 trades**.
  Es una muestra demasiado chica para concluir nada, y además es una
  configuración más restrictiva que la que se backtestea acá. Se registra porque
  omitirlo sería deshonesto, no porque sea decisivo.
- **En los últimos 60 días el oro cae a PF 0.84, negativo.** El promedio de dos
  años no es la expectativa de hoy. Ver la advertencia en
  [PORTFOLIO.md](PORTFOLIO.md).
- El costo es plano de $5.00/trade. El slippage medido en otra parte de este
  proyecto tenía cola gorda (peor caso $29 sobre un stop de 6 puntos). Los stops
  de Ciel son más anchos, así que el impacto proporcional es menor, pero la cola
  no se modeló.

**La frase honesta:** el edge parece real y sobrevive los tests que mataron a la
otra estrategia, pero nunca se encontró con un fill real, y el régimen de los
últimos dos meses está por debajo de su promedio histórico.
