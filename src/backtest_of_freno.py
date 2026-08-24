# -*- coding: utf-8 -*-
"""backtest_of_freno.py — ¿El freno diario del ejecutor OF paga, cuesta o da igual? (16-jul)
Pregunta de Juan: el +$1,749/maxDD $646 del veredicto es del sistema QUIETO — el freno -$300
es una regla sin backtest (la misma falta del Q78). Este script la testea sobre los mismos
30 dias del veredicto: reconstruye los trades div-only con backtest_of_pro y aplica encima
variantes de freno como las aplicaria el ejecutor (bloquea ABRIR tras cruzar el limite;
el trade que cruza completa).
Variantes: SIN freno / -300 / -450 / racha 3 SL plenos -> cierra el dia.
Uso: python backtest_of_freno.py [MGC|MES]
"""
import sys, os
from collections import defaultdict

if len(sys.argv) < 2: sys.argv.append("MGC")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_of_pro as bop

def aplicar_freno(trades, stop=None, racha_sl=None):
    """Replica la logica del ejecutor: al cruzar el limite se bloquea ABRIR el resto del dia."""
    out = []; cur = None; cum = 0.0; blocked = False; streak = 0
    for tag, pnl, d in trades:
        if d != cur: cur = d; cum = 0.0; blocked = False; streak = 0
        if blocked: continue
        out.append((tag, pnl, d))
        cum += pnl
        if pnl < -60: streak += 1        # SL pleno (-63.5 con costo); time-exits chicos no cuentan
        elif pnl > 0: streak = 0
        if stop is not None and cum <= -stop: blocked = True
        if racha_sl is not None and streak >= racha_sl: blocked = True
    return out

def met(trades):
    pl = [p for _, p, _ in trades]
    dias = defaultdict(float)
    for _, p, d in trades: dias[d] += p
    bal = peak = mdd = 0.0
    for d in sorted(dias):
        bal += dias[d]; peak = max(peak, bal); mdd = max(mdd, peak - bal)
    w = [x for x in pl if x > 0]; l = [x for x in pl if x <= 0]
    return dict(n=len(pl), tot=sum(pl), pf=(sum(w)/abs(sum(l)) if l else 99),
                mdd=mdd, peor=min(dias.values()) if dias else 0,
                verdes=sum(1 for v in dias.values() if v > 0), dias=len(dias), pordia=dict(dias))

def main():
    bars, lvls = bop.cargar()
    base = bop.backtest(bars, lvls, usar_abs=False)   # SOLO DIVERGENCIA = config del veredicto
    variantes = [("SIN freno (sistema quieto)", None, None),
                 ("freno -300", 300, None), ("freno -450", 450, None),
                 ("racha 3 SL -> cierra dia", None, 3)]
    print(f"{bop.MERCADO} div-only | {len(bars)} velas | freno aplicado como en el ejecutor\n")
    print(f"  {'variante':30} {'n':>4} {'PF':>5} {'total':>8} {'maxDD':>6} {'peorDia':>8} {'verdes':>7}")
    res = {}
    for label, stop, racha in variantes:
        t = aplicar_freno(base, stop, racha)
        m = met(t); res[label] = m
        print(f"  {label:30} {m['n']:>4} {m['pf']:>5.2f} {m['tot']:>+8.0f} {m['mdd']:>6.0f} {m['peor']:>+8.0f} {m['verdes']:>4}/{m['dias']}")
    print()
    sin = res["SIN freno (sistema quieto)"]["pordia"]
    for label in ("freno -300", "freno -450", "racha 3 SL -> cierra dia"):
        con = res[label]["pordia"]
        difs = [(d, sin[d], con.get(d, 0.0)) for d in sorted(sin) if abs(sin[d] - con.get(d, 0.0)) > 0.5]
        if not difs:
            print(f"  {label}: NUNCA actuo en los 30 dias."); continue
        costo = sum(s - c for _, s, c in difs)
        print(f"  {label}: actuo {len(difs)} dia(s), costo total {-costo:+.0f}$ vs quieto")
        for d, s, c in difs:
            tipo = "SALVO" if c > s else ("corto remontada" if s > c else "=")
            print(f"      {d}  sin freno {s:+7.0f}  con freno {c:+7.0f}  -> {tipo} {abs(s-c):.0f}$")

if __name__ == "__main__":
    main()
