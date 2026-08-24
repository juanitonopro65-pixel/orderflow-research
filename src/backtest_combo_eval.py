# -*- coding: utf-8 -*-
"""COMBO TREND+FADE vs el eval Lucid — ¿el fade ayuda a los Ciel a pasar y escalar?
Corre los dos sistemas sobre la misma data (GC=F 2y 1h):
  TREND = nucleo mecanico con zona 20/80 (v3.3)   — opera dias ALCISTA/BAJISTA del diario
  FADE  = rango ext85 TP 0.5R (backtest_fade_gc)  — opera SOLO dias LATERAL
Jamas operan el mismo dia -> el combo es union limpia. Metricas que importan al eval:
  maxDD de la curva | muertes con trailing $1,000 EOD (aprox Lucid MLL, sin lock,
  conservador) | dias ganadores >=$100 (payout Lucid pide 5) | P&L por regimen.
Uso: python backtest_combo_eval.py"""
import json, urllib.request, statistics as st
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
DPP, COST = 10.0, 5.0

def yh(itv, rng):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval={itv}&range={rng}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AgusBot/1.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=40).read().decode())
    res = d["chart"]["result"][0]; ts = res["timestamp"]; q = res["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(ts):
        o,h,l,c = q["open"][i],q["high"][i],q["low"][i],q["close"][i]
        if None in (o,h,l,c): continue
        out.append((t,o,h,l,c))
    return out

def sma(v,i,p): return sum(v[i-p+1:i+1])/p if i>=p-1 else None

def daily_trend_map(daily):
    C=[c for *_,c in daily]; out={}
    for i in range(len(daily)):
        d=datetime.fromtimestamp(daily[i][0],ET).date()
        j=i-1
        if j<50: out[d]="LATERAL"; continue
        ma20,ma50=sma(C,j,20),sma(C,j,50); ma20p=sma(C,j-5,20)
        p=C[j]
        if p>ma20>ma50 and ma20>ma20p: out[d]="ALCISTA"
        elif p<ma20<ma50 and ma20<ma20p: out[d]="BAJISTA"
        else: out[d]="LATERAL"
    return out

def atr(H,L,C,i,p=14):
    if i<p: return None
    trs=[max(H[k]-L[k],abs(H[k]-C[k-1]),abs(L[k]-C[k-1])) for k in range(i-p+1,i+1)]
    return sum(trs)/p

def run_trend(h1, tmap, zona=20):
    T=[x[0] for x in h1]; H=[x[2] for x in h1]; L=[x[3] for x in h1]; C=[x[4] for x in h1]
    n=len(h1); trades=[]; pos=None
    for i in range(60,n):
        dt=datetime.fromtimestamp(T[i],ET)
        if pos:
            dirn,e,slv,tpv,i0=pos
            hit_sl=(L[i]<=slv) if dirn==1 else (H[i]>=slv)
            hit_tp=(H[i]>=tpv) if dirn==1 else (L[i]<=tpv)
            if hit_sl: trades.append((dt.date(),-abs(e-slv)*DPP-COST,"TREND")); pos=None
            elif hit_tp: trades.append((dt.date(), abs(tpv-e)*DPP-COST,"TREND")); pos=None
            elif i-i0>=8: trades.append((dt.date(),((C[i]-e) if dirn==1 else (e-C[i]))*DPP-COST,"TREND")); pos=None
            continue
        mins=dt.hour*60+dt.minute
        if not (9*60+30<=mins<16*60): continue
        tr=tmap.get(dt.date(),"LATERAL")
        if tr=="LATERAL": continue
        a=atr(H,L,C,i)
        if not a or a<=0: continue
        lo=min(L[max(0,i-47):i+1]); hi=max(H[max(0,i-47):i+1])
        if hi<=lo: continue
        p100=(C[i]-lo)/(hi-lo)*100
        if tr=="ALCISTA" and p100>zona: continue
        if tr=="BAJISTA" and p100<100-zona: continue
        dirn=1 if tr=="ALCISTA" else -1; e=C[i]
        sd=min(max(1.75*a,15),40); tpd=1.5*sd
        pos=(dirn,e,e-dirn*sd,e+dirn*tpd,i)
    return trades

def run_fade(h1, tmap, ext=85, tp_r=0.5):
    T=[x[0] for x in h1]; H=[x[2] for x in h1]; L=[x[3] for x in h1]; C=[x[4] for x in h1]
    n=len(h1); trades=[]; pos=None
    for i in range(60,n):
        dt=datetime.fromtimestamp(T[i],ET)
        if pos:
            dirn,e,slv,tpv,i0=pos
            hit_sl=(L[i]<=slv) if dirn==1 else (H[i]>=slv)
            hit_tp=(H[i]>=tpv) if dirn==1 else (L[i]<=tpv)
            if hit_sl: trades.append((dt.date(),-abs(e-slv)*DPP-COST,"FADE")); pos=None
            elif hit_tp: trades.append((dt.date(), abs(tpv-e)*DPP-COST,"FADE")); pos=None
            elif i-i0>=8: trades.append((dt.date(),((C[i]-e) if dirn==1 else (e-C[i]))*DPP-COST,"FADE")); pos=None
            continue
        mins=dt.hour*60+dt.minute
        if not (9*60+30<=mins<16*60): continue
        if tmap.get(dt.date(),"LATERAL")!="LATERAL": continue
        a=atr(H,L,C,i)
        if not a or a<=0: continue
        lo=min(L[max(0,i-47):i+1]); hi=max(H[max(0,i-47):i+1])
        if hi<=lo: continue
        p100=(C[i]-lo)/(hi-lo)*100
        if p100>=ext: dirn=-1
        elif p100<=100-ext: dirn=1
        else: continue
        e=C[i]
        sd=min(max(1.75*a,15),40); tpd=tp_r*sd
        pos=(dirn,e,e-dirn*sd,e+dirn*tpd,i)
    return trades

def eval_metrics(trades,label):
    """trades: [(date,pnl,tag)] -> curva diaria + metricas de eval"""
    if not trades: print(f"  {label}: sin trades"); return
    trades=sorted(trades,key=lambda x:x[0])
    daily={}
    for d,p,_ in trades: daily[d]=daily.get(d,0.0)+p
    days=sorted(daily)
    # curva y maxDD
    bal=peak=mdd=0.0
    muertes=0; bal_t=0.0; peak_t=0.0   # trailing $1000 con reset (cada muerte = cuenta nueva)
    for d in days:
        bal+=daily[d]; peak=max(peak,bal); mdd=max(mdd,peak-bal)
        bal_t+=daily[d]; peak_t=max(peak_t,bal_t)
        if peak_t-bal_t>=1000.0: muertes+=1; bal_t=0.0; peak_t=0.0
    pl=[p for _,p,_ in trades]; w=[x for x in pl if x>0]; l=[x for x in pl if x<=0]
    pf=sum(w)/abs(sum(l)) if l else 99
    dias_verdes=sum(1 for d in days if daily[d]>0)
    dias_100=sum(1 for d in days if daily[d]>=100.0)
    dias_rojos_400=sum(1 for d in days if daily[d]<=-400.0)
    total=sum(pl)
    print(f"  {label:14} trades={len(pl):>3} PF={pf:.2f} tot=${total:+8.0f} | maxDD=${mdd:>5.0f} | "
          f"MUERTES trailing $1k (2y): {muertes} | dias op={len(days)} verdes={dias_verdes} "
          f">=+$100: {dias_100} | <=-$400: {dias_rojos_400}")

def main():
    print("="*118)
    print("  TREND(v3.3) vs FADE(ext85 0.5R) vs COMBO — metricas de EVAL Lucid (GC=F 2y, trailing MLL $1,000 aprox)")
    print("="*118)
    daily=yh("1d","2y"); h1=yh("1h","730d")
    tmap=daily_trend_map(daily)
    tt=run_trend(h1,tmap); ff=run_fade(h1,tmap)
    print()
    eval_metrics(tt,"TREND solo")
    eval_metrics(ff,"FADE solo")
    eval_metrics(tt+ff,"COMBO T+F")
    print()
    # aporte por regimen
    lat=[p for _,p,tag in ff]; tnd=[p for _,p,tag in tt]
    print(f"  Aporte por regimen: dias tendencia (TREND) ${sum(tnd):+.0f} | dias laterales (FADE) ${sum(lat):+.0f}")
    print("  Leer: MUERTES = veces que una cuenta con MLL trailing $1,000 habria muerto en 2y (0 = sobrevive todo).")
    print("="*118)

if __name__=="__main__":
    main()
