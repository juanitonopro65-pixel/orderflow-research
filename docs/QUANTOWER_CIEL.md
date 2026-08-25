# Ciel en Quantower (demo / eval)

Tutorial completo paso a paso: **[TUTORIAL_CIEL.md](TUTORIAL_CIEL.md)**.

## Puertos

| Puerto | Uso |
|---|---|
| **8765** | AgustinaBridge en gráfico **MGC** (Ciel oro) |
| 8766 | OF-MGC (no mezclar con Ciel LIVE) |
| 8767 | OF-MES |
| **8768** | AgustinaBridge en gráfico **ZW** (Ciel trigo) |

## Setup en Quantower

1. Abrí Strategy Runner → **AgustinaBridge** en el gráfico **MGC** continuo.
2. Puerto HTTP = **8765**, cuenta Lucid demo/eval, activá la estrategia.
3. (Opcional trigo) Otra instancia AgustinaBridge en gráfico **ZW**, puerto **8768**.
4. En Windows, desde la carpeta del repo:

```bat
set CIEL_LUCID_PROFILE=25k
set CIEL_MARKETS=MGC
python src\agus_ejecutor_ciel.py --check
python src\agus_ejecutor_ciel.py
```

5. Programá `src\run_ciel_exec.bat` cada 1–5 min en sesión (Task Scheduler).
6. **LIVE:** ejecutá `src\activar_ciel_live.bat` y escribí `SI`. Sin ese archivo = DRY-RUN.
7. Abort LIVE: borrá `src\LIVE_MGC.txt`.

## Eval $150k

```bat
set CIEL_LUCID_PROFILE=150k
set CIEL_MARKETS=MGC,ZW
python src\agus_ejecutor_ciel.py --check
python src\agus_ejecutor_ciel.py
```

Escalera: 1 contrato c/u hasta +$1,500 de profit eval, luego 2. Flat ~16:40 ET.

## Comparar paper vs demo

```bat
python analysis\compare_demo.py
```

Criterio: PF demo ≥ 1.0 y WR dentro de ±15% del paper → comprar eval.
