"""
Uso:  python scripts/explorar_statistics.py 2026-09-24

Explora el archivo de statistics de la cadena SPX que ya está en caché (costo $0).
¿Qué tipos de estadística trae, a cuántas opciones cubre cada uno (sobre todo a las del
"OI invisible", sin trades ese día), cuándo se publica y si sus precios son razonables?
No cambia nada del proyecto: solo mira.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.odte.constantes import ZONA_NY

# Numeración de stat_type de Databento
NOMBRES = {
    1: "OPENING_PRICE", 2: "INDICATIVE_OPENING_PRICE", 3: "SETTLEMENT_PRICE",
    4: "SESSION_LOW", 5: "SESSION_HIGH", 6: "CLEARED_VOLUME", 7: "LOWEST_OFFER",
    8: "HIGHEST_BID", 9: "OPEN_INTEREST", 10: "FIXING_PRICE", 11: "CLOSE_PRICE",
    12: "NET_CHANGE", 13: "VWAP", 14: "VOLATILITY", 15: "DELTA", 16: "UNCROSSING_PRICE",
}

fecha = sys.argv[1] if len(sys.argv) > 1 else "2026-09-24"
stats = pd.read_parquet(f"data/raw/cadena_SPX_statistics_{fecha}.parquet")
ohlcv = pd.read_parquet(f"data/raw/cadena_SPX_ohlcv-1d_{fecha}.parquet")

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)

print(f"=== statistics del {fecha}: {len(stats):,} filas ===")
print("Columnas:", list(stats.columns))

con_trade = set(ohlcv["symbol"])
oi = stats[stats["stat_type"] == 9].drop_duplicates("symbol", keep="last")
oi_por_simbolo = oi.set_index("symbol")["quantity"]
invisibles = set(oi_por_simbolo.index) - con_trade
oi_invisible_total = oi_por_simbolo[list(invisibles)].sum()
print(f"\nOpciones con OI: {len(oi_por_simbolo):,} | sin trade (invisibles): {len(invisibles):,} "
      f"| OI invisible: {oi_invisible_total:,.0f} contratos")

# ------------------------------------------------------------
# 1) y 2) Qué trae y a quién cubre
# ------------------------------------------------------------
filas = []
for st, g in stats.groupby("stat_type"):
    simbolos = set(g["symbol"])
    cubre_inv = simbolos & invisibles
    filas.append({
        "stat_type": st,
        "nombre": NOMBRES.get(int(st), "desconocido"),
        "filas": len(g),
        "opciones": len(simbolos),
        "invisibles_cubiertas": len(cubre_inv),
        "%OI_invisible_cubierto": oi_por_simbolo[list(cubre_inv)].sum() / oi_invisible_total * 100
        if oi_invisible_total else 0,
        "con_precio": int(g["price"].notna().sum()) if "price" in g else 0,
        "publishers": g["publisher_id"].nunique() if "publisher_id" in g else None,
    })
print("\n=== Tipos de estadística y cobertura ===")
print(pd.DataFrame(filas).round(1).to_string(index=False))

# ------------------------------------------------------------
# 3) Cuándo se publica cada tipo (hora de Nueva York)
# ------------------------------------------------------------
if "ts_event" in stats.columns:
    hora = pd.to_datetime(stats["ts_event"], utc=True).dt.tz_convert(ZONA_NY)
    stats = stats.assign(hora_ny=hora)
    print("\n=== Hora de publicación (Nueva York): primera y última ===")
    print(stats.groupby("stat_type")["hora_ny"].agg(["min", "max"]).to_string())

# ------------------------------------------------------------
# 4) ¿Son razonables los precios? Contra el último trade del día (ohlcv close)
# ------------------------------------------------------------
cierre_trade = ohlcv.drop_duplicates("symbol", keep="last").set_index("symbol")["close"]
print("\n=== Precios de cada tipo contra el último trade (solo opciones con trade) ===")
for st in [1, 3, 4, 5, 7, 8, 10, 11, 13]:
    g = stats[(stats["stat_type"] == st) & stats["price"].notna()]
    if g.empty:
        continue
    p = g.drop_duplicates("symbol", keep="last").set_index("symbol")["price"]
    comun = p.index.intersection(cierre_trade.index)
    if len(comun) == 0:
        continue
    dif = (p[comun] - cierre_trade[comun]).abs()
    print(f"{NOMBRES.get(st, st):16s}: {len(comun):5d} opciones | "
          f"diferencia mediana {dif.median():.2f} | igual al último trade: {(dif < 0.005).mean():.0%}")

# Un ejemplo concreto: una opción invisible con mucho OI, ¿qué estadísticas tiene?
if invisibles:
    top = oi_por_simbolo[list(invisibles)].sort_values(ascending=False).head(3)
    print("\n=== Las 3 opciones invisibles con más OI y todo lo que statistics dice de ellas ===")
    for sym, q in top.items():
        print(f"\n{sym}  (OI {q:,.0f})")
        cols = [c for c in ["stat_type", "price", "quantity", "publisher_id", "hora_ny"] if c in stats.columns]
        ej = stats[stats["symbol"] == sym][cols].copy()
        ej["nombre"] = ej["stat_type"].map(lambda s: NOMBRES.get(int(s), "?"))
        print(ej.to_string(index=False))