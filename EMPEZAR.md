# Empezar

## Requisitos

**Python 3.9 o superior. Nada más.** Cero dependencias externas — todo el código
usa solo la librería estándar. No hay `pip install`, no hay entorno virtual, no
hay `requirements.txt` que se rompa.

```bash
python --version    # tiene que decir 3.9 o mas
```

## Clonar

El repositorio es **privado**, así que hace falta estar invitado como colaborador
y autenticado. Con GitHub CLI (`gh`) es lo más simple:

```bash
gh auth login
gh repo clone juanitonopro65-pixel/orderflow-research
```

Con git a secas, pide usuario y un *personal access token* (no la contraseña):

```bash
git clone https://github.com/juanitonopro65-pixel/orderflow-research.git
```

## Comprobar que todo corre

Tres comandos, cada uno independiente:

```bash
cd orderflow-research

# 1. Recalcula los resultados con dinero real desde el ledger crudo.
#    No necesita internet: lee data/of_exec_log.csv.
python analysis/live_results.py

# 2. Estado del test forward en papel (al principio dira que no hay trades).
python paper/ciel_paper.py --stats

# 3. Backtest de viabilidad de la evaluacion de $150k.
#    Este SI baja datos de Yahoo, tarda ~30 segundos.
python src/backtest_150k_ciel.py
```

Si el primero imprime `-$430.20` sobre 75 trades, está todo bien.

## Por dónde empezar a leer

1. **[README.md](README.md)** — qué es, qué pasó, y los números que importan.
2. **[docs/METHOD.md](docs/METHOD.md)** — las trampas de medición. Es lo más útil
   si el interés es técnico: seis formas concretas en que un backtest miente,
   cada una con el número real al lado del número falso.
3. **[docs/PORTFOLIO.md](docs/PORTFOLIO.md)** — la decisión abierta hoy: qué
   cuenta comprar y cuándo.
4. **[paper/README.md](paper/README.md)** — el test que está corriendo ahora y el
   criterio de decisión, escrito antes de mirar los resultados.

## Qué se puede correr y qué no

| | corre solo | necesita |
|---|---|---|
| `analysis/live_results.py` | ✅ | nada, lee el CSV incluido |
| `paper/ciel_paper.py` | ✅ | internet (datos de Yahoo) |
| `src/backtest_*.py` | ✅ | internet |
| `src/agus_ejecutor_of_mgc.py` | ❌ | Quantower corriendo + cuenta de bróker |
| `src/agus_orderflow_reader.py` | ❌ | el bridge en localhost:8766 |

Los dos últimos están para leerlos, no para correrlos: se conectan al bróker.
`src/quantower_bridge.py` es el cliente HTTP que usan.

## Los datos incluidos

- `data/master_of_mgc_bars.csv` — 34,276 velas de 1 minuto de oro con order flow
  (delta, delta acumulado, volumen comprador y vendedor). Recolectadas con la
  infraestructura propia, no descargadas.
- `data/of_exec_log.csv` — el ledger completo de los trades con dinero real.
- `data/orderflow_signals_log.csv` — 7,657 señales registradas en vivo.

Todo lo que se afirma en los documentos sale de estos tres archivos.
