"""
paquetes.py — Reconstruir paquetes de varias patas en el tcbbo, donde la regla estricta deja el ~90% indeterminado.

Agrupación: prints de series DISTINTAS en el mismo milisegundo (ts_recv) = un paquete. Control placebo
(scripts/signo_walls.py --paquetes): desplazando las calls 3-61 s, los pares C+P caen de ~5.500 a 2-3.

Forma que se clasifica: COMBO C+P del MISMO strike y vencimiento, mismo tamaño, un print por pata.
Como la gamma de la call y la put del mismo strike y vencimiento es la MISMA (Black-Scholes):
  sintético  (una pata arriba del medio y la otra abajo: compra una, vende la otra)
             -> gamma neta 0 para quien lo tenga, SEA CUAL SEA la dirección. El signo no importa.
             (La hipótesis nula también le da 0: dealer + en la call y - en la put.)
  straddle   (las dos patas del mismo lado del medio) -> gamma ±2γ; la nula le da 0 (se equivoca de tamaño).
             ambas arriba = el público COMPRÓ (dealer corto de gamma); ambas abajo = VENDIÓ (dealer largo).
  indeterminado: alguna pata en el medio exacto o sin cotización.
El lado de cada pata es INFERIDO del precio de la pata contra su propio medio: en un paquete el precio se
negocia en conjunto y el reparto entre patas puede ser arbitrario. Es flujo (volumen), no OI.
"""
import numpy as np
import pandas as pd

from src.simbolos import parsear_simbolos

VENTANA = "1ms"


def lado_pata(trades):
    """+1 si el print está arriba del medio de su propio bid/ask, -1 abajo, 0 en el medio o sin cotización."""
    medio = (trades["bid_px_00"] + trades["ask_px_00"]) / 2
    d = (trades["price"] - medio).round(4)
    ok = (trades["bid_px_00"] > 0) & (trades["ask_px_00"] >= trades["bid_px_00"])
    return np.sign(d).where(ok & d.notna(), 0).astype(int)


def combos_cp(trades, ventana=VENTANA, banda=25):
    """trades: tcbbo con índice de tiempo (NY), columnas symbol, price, size, bid_px_00, ask_px_00.
    Una fila por combo C+P (mismo strike, venc y tamaño, dos prints en la misma ventana):
    ts, strike, zona, venc, size, lado_c, lado_p, forma ('sintetico'/'straddle'/'indeterminado') y
    publico ('compra'/'vende' solo en straddle)."""
    t = trades.copy()
    t = t.rename_axis(None)
    t["ts"] = t.index.floor(ventana)
    info = parsear_simbolos(t["symbol"])
    for c in ["venc", "tipo", "strike"]:
        t[c] = info[c].values
    t["lado"] = lado_pata(t)
    g = t.groupby("ts")
    t = t[(g["symbol"].transform("size") == 2) & (g["symbol"].transform("nunique") == 2)]
    c, p = t[t["tipo"] == "C"].set_index("ts"), t[t["tipo"] == "P"].set_index("ts")
    m = c.join(p, how="inner", lsuffix="_c", rsuffix="_p")
    m = m[(m["strike_c"] == m["strike_p"]) & (m["venc_c"] == m["venc_p"]) & (m["size_c"] == m["size_p"])]
    r = pd.DataFrame({"strike": m["strike_c"], "venc": m["venc_c"], "size": m["size_c"].astype("int64"),
                      "lado_c": m["lado_c"], "lado_p": m["lado_p"]})
    r["zona"] = (r["strike"] / banda).round() * banda
    prod = r["lado_c"] * r["lado_p"]
    r["forma"] = np.select([prod < 0, prod > 0], ["sintetico", "straddle"], "indeterminado")
    r["publico"] = np.where(r["forma"] == "straddle", np.where(r["lado_c"] > 0, "compra", "vende"), "")
    return r.rename_axis("ts").reset_index()


def resumen_combos(combos, volumen_zona):
    """Por zona: volumen total de las series (volumen_zona), en combos C+P y su reparto (contratos por pata).
    straddle_neto = compra - venta del público en straddles (+ = el público compró gamma: dealer corto)."""
    v = combos.pivot_table(index="zona", columns="forma", values="size", aggfunc="sum", fill_value=0)
    v = v.reindex(columns=["sintetico", "straddle", "indeterminado"], fill_value=0)
    s = combos[combos["forma"] == "straddle"]
    neto = s["size"].where(s["publico"] == "compra", -s["size"]).groupby(s["zona"]).sum()
    r = pd.DataFrame({"volumen": volumen_zona}).join(v, how="left").fillna(0)
    r["en_combos"] = r[["sintetico", "straddle", "indeterminado"]].sum(axis=1) * 2   # dos patas por combo
    r["straddle_neto"] = neto.reindex(r.index).fillna(0)
    r["pct_en_combos"] = (r["en_combos"] / r["volumen"] * 100).where(r["volumen"] > 0)
    clasif = r["sintetico"] + r["straddle"]
    r["pct_sintetico"] = (r["sintetico"] / clasif * 100).where(clasif > 0)
    return r.astype({c: "int64" for c in ["volumen", "sintetico", "straddle", "indeterminado", "en_combos",
                                          "straddle_neto"]})
