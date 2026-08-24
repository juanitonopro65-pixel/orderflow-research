# -*- coding: utf-8 -*-
"""backtest_150k_ciel.py — FEASIBILITY del 150K PRO EVAL para Ciel (24-jul, antes de gastar $222).
Reglas del eval: target $9,000 · max loss $4,500 tipo EOD (intradia NO cuenta) · sin DLL ·
max 10 mini = 100 micros. Pregunta: ¿a que tamaño Ciel pasa el target ANTES de tocar el limite,
y en cuanto tiempo? La proporcion ganancia/drawdown NO cambia con el tamaño — escalar acelera
la ganancia PERO tambien el drawdown. Eso decide si el eval es viable o es tirar $222.
Motor: combo v3.4 (trend zona 50/50 + fade en laterales) sobre GC=F 2 años, costo incluido.
Uso: python backtest_150k_ciel.py
"""
import sys, os
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_combo_eval as ce

TARGET   = 9000.0
MAXLOSS  = 4500.0     # EOD trailing
MAX_MICROS = 100

def simular(dias_pnl, n_micros):
    """Simula el eval con N micros. DD medido EOD (sobre el cierre de cada dia).
    Devuelve (resultado, dias_hasta, peor_dd)."""
    eq = 0.0; peak = 0.0; peor = 0.0
    for i, (d, p) in enumerate(dias_pnl, 1):
        eq += p * n_micros
        peak = max(peak, eq)
        dd = peak - eq
        peor = max(peor, dd)
        if dd >= MAXLOSS:
            return ("MUERE", i, peor)
        if eq >= TARGET:
            return ("PASA", i, peor)
    return ("NO LLEGA", len(dias_pnl), peor)

def main():
    print("FEASIBILITY 150K PRO EVAL para Ciel — target $9,000 | max loss $4,500 EOD | hasta 100 micros\n")
    daily = ce.yh("1d", "2y"); h1 = ce.yh("1h", "730d")
    tmap = ce.daily_trend_map(daily)
    tt = ce.run_trend(h1, tmap, zona=50)      # v3.4 = zona 50/50
    ff = ce.run_fade(h1, tmap)
    combo = tt + ff
    dias = defaultdict(float)
    for d, p, _ in combo: dias[d] += p
    serie = sorted(dias.items())
    tot1 = sum(p for _, p in serie)
    print(f"  Ciel combo (v3.4) a 1 micro sobre {len(serie)} dias operados (2 años): {tot1:+.0f}$")
    print(f"  -> ritmo: {tot1/24:+.0f}$/mes a 1 micro\n")
    print(f"  {'micros':>7} {'resultado':>10} {'dias':>6} {'~meses':>7} {'peor DD EOD':>12} {'target/DD':>10}")
    algun_pasa = False
    for n in (1, 2, 3, 5, 8, 12, 20, 40, 100):
        if n > MAX_MICROS: continue
        res, d, peor = simular(serie, n)
        meses = d / 21.0
        ratio = f"{TARGET/peor:.2f}" if peor > 0 else "-"
        flag = ""
        if res == "PASA": algun_pasa = True; flag = "  <== VIABLE"
        print(f"  {n:>7} {res:>10} {d:>6} {meses:>7.1f} {peor:>12.0f} {ratio:>10}{flag}")
    print()
    if not algun_pasa:
        print("  VEREDICTO: con NINGUN tamaño Ciel pasa el eval antes de tocar el limite.")
        print("  Motivo: la proporcion ganancia/drawdown de la estrategia es la que es; escalar")
        print("  multiplica las DOS cosas. Si el DD llega a $4,500 antes que la ganancia a $9,000,")
        print("  ningun sizing lo arregla. Gastar $222 seria comprar una loteria, no un plan.")
    else:
        print("  VEREDICTO: hay tamaño(s) donde pasa. Mirar cuantos meses tarda y con cuanto")
        print("  margen (peor DD vs $4,500) — si el margen es fino, es apuesta, no plan.")
    print("\n  OJO: proxy deterministico del combo (sin DeepSeek), GC=F 2 años. Valida el patron")
    print("  ganancia/DD, no la version exacta en vivo.")

if __name__ == "__main__":
    main()
