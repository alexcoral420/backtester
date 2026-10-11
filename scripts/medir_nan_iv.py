"""
Uso:  python scripts/medir_nan_iv.py 2026-09-24        (sin dividendos, q = 0: la corrida original)
      python scripts/medir_nan_iv.py 2026-09-24 q      (con el forward medido por vencimiento)

Mide el hueco de la versión C (punto medio, todas las opciones con OI): las opciones a las que
NO se les pudo calcular la IV. ¿Cuántas son, cuánto OI tienen, por qué fallan, qué tan dentro o
fuera del dinero están y, sobre todo, cuánta gamma tendrían si las incluyéramos?
Todo desde la caché. Costo $0. No cambia el proyecto.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TASA_LIBRE_RIESGO
from src.black_scholes import calcular_iv, gamma_opcion, precio_bs
from src.datos import precio_spx
from src.forward import forward_por_vencimiento, q_por_opcion
from src.precio_justo import tabla_cierre

fecha = sys.argv[1] if len(sys.argv) > 1 else "2026-09-24"
con_q = len(sys.argv) > 2 and sys.argv[2] == "q"
S, r = precio_spx(fecha), TASA_LIBRE_RIESGO

c = tabla_cierre(fecha)
c = c[c["T"] > 0].copy()
c["q"] = q_por_opcion(c, forward_por_vencimiento(c, S, r)) if con_q else 0.0
c["iv"] = [calcular_iv(p, S, k, T, r, tp, q) for p, k, T, tp, q in
           zip(c["mid"], c["strike"], c["T"], c["tipo"], c["q"])]
nan = c["iv"].isna()
oi_tot = c["open_interest"].sum()

print(f"=== {fecha} | SPX {S:.2f} | versión C: {len(c):,} opciones | "
      f"{'q = forward medido' if con_q else 'q = 0 (sin dividendos)'} ===\n")
print(f"IV nan: {nan.sum():,} opciones ({nan.mean():.1%}) | "
      f"OI {c.loc[nan, 'open_interest'].sum():,.0f} contratos ({c.loc[nan, 'open_interest'].sum() / oi_tot:.1%} del OI)")


# ------------------------------------------------------------
# 1) ¿Por qué falla cada una?
# ------------------------------------------------------------
def motivo(f):
    if np.isnan(f["mid"]):
        return "1 sin cotización válida"
    desc = f["strike"] * np.exp(-r * f["T"])
    s_desc = S * np.exp(-f["q"] * f["T"])
    piso = max(s_desc - desc, 0.0) if f["tipo"] == "C" else max(desc - s_desc, 0.0)
    if f["mid"] < piso:
        return "2 mid bajo el intrínseco"
    if f["mid"] < precio_bs(S, f["strike"], f["T"], r, 0.01, f["tipo"], f["q"]):
        return "3 vol < 1% (solo intrínseco)"
    if f["mid"] > precio_bs(S, f["strike"], f["T"], r, 5.0, f["tipo"], f["q"]):
        return "4 vol > 500%"
    return "5 otro"


n = c[nan].copy()
n["motivo"] = n.apply(motivo, axis=1)

# Qué tan dentro o fuera del dinero: distancia porcentual del strike al SPX, con signo de "dentro"
dentro = np.where(n["tipo"] == "C", S - n["strike"], n["strike"] - S) / S * 100
n["moneyness"] = pd.cut(dentro, [-np.inf, -10, -2, 2, 10, np.inf],
                        labels=["muy fuera (>10%)", "fuera (2-10%)", "cerca (±2%)",
                                "dentro (2-10%)", "muy dentro (>10%)"])
n["plazo"] = pd.cut(n["T"] * 365, [0, 30, 180, np.inf], labels=["<30 días", "30-180 días", ">180 días"])

pd.set_option("display.width", 200)
for col in ["motivo", "moneyness", "plazo"]:
    tabla = n.groupby(col, observed=True).agg(opciones=("open_interest", "size"),
                                              oi=("open_interest", "sum"))
    tabla["% del OI nan"] = (tabla["oi"] / tabla["oi"].sum() * 100).round(1)
    print(f"\n=== Por {col} ===")
    print(tabla.to_string())

# ------------------------------------------------------------
# 1b) ¿Qué tan preciso es el punto medio PARA LA IV?
# La IV sale solo del VALOR TEMPORAL (mid - intrínseco), no del precio entero.
# Un spread de 20 pts es 0,5% de una call de 3.700, pero puede ser MAYOR que todo su valor temporal.
# Métrica: spread / valor temporal. > 100% = el spread es más ancho que lo que mide la IV.
# ------------------------------------------------------------
intrinseco = np.where(c["tipo"] == "C", np.maximum(S - c["strike"], 0), np.maximum(c["strike"] - S, 0))
c["valor_temporal"] = c["mid"] - intrinseco
c["spread_sobre_vt_%"] = np.where(c["valor_temporal"] > 0,
                                  (c["ask"] - c["bid"]) / c["valor_temporal"] * 100, np.inf)
print("\n=== Spread sobre valor temporal, en % (inf = el mid no supera el intrínseco) ===")
grupo = nan.map({True: "IV nan", False: "IV calculada"})
q = c.groupby(grupo)["spread_sobre_vt_%"].quantile([0.25, 0.5, 0.75, 0.9])
print(q.unstack().round(1).rename(columns={0.25: "p25", 0.5: "mediana", 0.75: "p75", 0.9: "p90"}).to_string())
print("Opciones con spread mayor que su valor temporal (>100% o inf):")
print((c["spread_sobre_vt_%"] > 100).groupby(grupo).mean().map("{:.0%}".format).to_string())

# ------------------------------------------------------------
# 2) Lo que importa: ¿cuánta gamma tendrían?
# Volatilidad "razonable" = mediana de la IV válida del MISMO vencimiento (o la global si no hay)
# ------------------------------------------------------------
iv_venc = c.loc[~nan].groupby("venc")["iv"].median()
iv_global = c.loc[~nan, "iv"].median()
c["iv_usada"] = c["iv"].fillna(c["venc"].map(iv_venc)).fillna(iv_global)

c["gamma"] = [gamma_opcion(S, k, T, r, v, q) for k, T, v, q in zip(c["strike"], c["T"], c["iv_usada"], c["q"])]
c["signo"] = np.where(c["tipo"] == "C", 1, -1)
c["gex_contrib"] = c["gamma"] * c["open_interest"] * c["signo"] * 100 * S**2 * 0.01

peso = c.loc[nan, "gex_contrib"].abs().sum() / c["gex_contrib"].abs().sum()
sin = c.loc[~nan, "gex_contrib"].sum()
con = c["gex_contrib"].sum()
print(f"\n=== Gamma estimada de las opciones con IV nan (vol = mediana de su vencimiento) ===")
print(f"Peso en |GEX|: {peso:.2%}")
print(f"GEX total C sin ellas: ${sin / 1e9:+.2f}B  |  con ellas: ${con / 1e9:+.2f}B")

# ------------------------------------------------------------
# 3) Los errores que SUSURRAN: opciones CON IV pero de spread ancho.
# ¿Qué fracción del |GEX| de C viene de gamma estimada con un mid poco preciso?
# ------------------------------------------------------------
v = c[~nan].copy()                                   # = versión C (solo IV real, sin rellenar)
dentro_c = np.where(v["tipo"] == "C", S - v["strike"], v["strike"] - S) / S * 100
v["moneyness"] = pd.cut(dentro_c, [-np.inf, -10, -2, 2, 10, np.inf],
                        labels=["muy fuera", "fuera", "cerca", "dentro", "muy dentro"])
v["calidad"] = pd.cut(v["spread_sobre_vt_%"], [-np.inf, 10, 50, 100, np.inf],
                      labels=["<10% preciso", "10-50%", "50-100%", ">100% flojo"])
abs_tot = v["gex_contrib"].abs().sum()

print("\n=== Opciones CON IV por calidad del mid (spread / valor temporal) ===")
t = v.groupby("calidad", observed=False).agg(
    opciones=("gex_contrib", "size"),
    pct_abs_gex=("gex_contrib", lambda g: g.abs().sum() / abs_tot * 100),
    gex_neto_B=("gex_contrib", "sum"),
)
t["gex_neto_B"] = (t["gex_neto_B"] / 1e9).round(2)
print(t.round(1).rename(columns={"pct_abs_gex": "% del |GEX|", "gex_neto_B": "GEX neto ($B)"}).to_string())

print("\n=== % del |GEX| por calidad x moneyness (dónde está la gamma floja) ===")
pv = v.pivot_table(index="calidad", columns="moneyness", values="gex_contrib",
                   aggfunc=lambda g: g.abs().sum() / abs_tot * 100, observed=False, fill_value=0)
print(pv.round(1).to_string())

# El salto de B a C es exactamente lo que aportan las invisibles (sin trade) con IV
inv = v[~v["con_trade"]]
salto = inv["gex_contrib"].sum()
print(f"\n=== El salto B -> C (aporte neto de las invisibles con IV): ${salto / 1e9:+.2f}B ===")
s = inv.groupby("calidad", observed=False)["gex_contrib"].sum()
for cal, val in s.items():
    print(f"  {cal:13s}: ${val / 1e9:+.2f}B  ({val / salto:.0%} del salto)" if salto else f"  {cal}: 0")

print("\nLas 5 opciones nan con más gamma estimada (las que más importarían):")
top = c[nan].assign(abs_gex=lambda d: d["gex_contrib"].abs()).nlargest(5, "abs_gex")
top = top[["tipo", "strike", "venc", "open_interest", "bid", "ask", "mid", "iv_usada", "gex_contrib"]].copy()
top["venc"] = top["venc"].dt.strftime("%Y-%m-%d")
print(top.round(3).to_string())

# ------------------------------------------------------------
# 4) Solo con q: ¿DÓNDE cambió el GEX respecto a q = 0? (versión C, solo IV real)
# ------------------------------------------------------------
if con_q:
    b = c.copy()
    b["iv0"] = [calcular_iv(p, S, k, T, r, tp) for p, k, T, tp in zip(b["mid"], b["strike"], b["T"], b["tipo"])]
    b["gex0"] = [gamma_opcion(S, k, T, r, v) for k, T, v in zip(b["strike"], b["T"], b["iv0"])]
    b["gex0"] = b["gex0"] * b["open_interest"] * b["signo"] * 100 * S**2 * 0.01
    b["gexq"] = b["gex_contrib"].where(~nan)                       # C con q, solo IV real
    b[["gex0", "gexq"]] = b[["gex0", "gexq"]].fillna(0)
    dentro_b = np.where(b["tipo"] == "C", S - b["strike"], b["strike"] - S) / S * 100
    b["moneyness"] = pd.cut(dentro_b, [-np.inf, -10, -2, 2, 10, np.inf],
                            labels=["muy fuera", "fuera", "cerca", "dentro", "muy dentro"])
    b["estado"] = np.select([b["iv0"].isna() & ~nan, ~b["iv0"].isna() & nan],
                            ["antes nan, ahora IV", "antes IV, ahora nan"], "igual")
    print(f"\n=== ¿Dónde cambió el GEX? q = 0: ${b['gex0'].sum() / 1e9:+.2f}B  ->  "
          f"q medido: ${b['gexq'].sum() / 1e9:+.2f}B ===")
    d = b.groupby(["tipo", "moneyness"], observed=True)[["gex0", "gexq"]].sum() / 1e9
    d["cambio"] = d["gexq"] - d["gex0"]
    print(d.round(2).rename(columns={"gex0": "q=0 ($B)", "gexq": "q medido ($B)", "cambio": "cambio ($B)"}).to_string())
    e = b.groupby("estado")[["gex0", "gexq"]].sum() / 1e9
    e["cambio"] = e["gexq"] - e["gex0"]
    print("\nPor estado de la IV:")
    print(e.round(2).to_string())