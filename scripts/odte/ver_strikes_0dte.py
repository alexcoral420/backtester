"""
Uso:  python scripts/odte/ver_strikes_0dte.py 2026-10-12 7750 7870

Flujo ESTRICTO de las 0DTE por STRIKE (todo desde caché, sin costo).
Tres estados: compra (en el ask), venta (en el bid), indeterminado (todo lo demás).
Responde: ¿en qué strikes se concentró la compra o la venta del público?

Cada trade se ubica respecto al SPX DE ESE MINUTO: no es lo mismo vender una put cuando el precio
está ARRIBA del strike (el strike aguanta, la put está fuera del dinero) que cuando ya está ABAJO
(el strike se rompió, la put está dentro del dinero).
Comportamiento del strike en el día:
  aguantó arriba  = el precio nunca bajó del strike      (strike debajo: soporte no tocado)
  aguantó abajo   = el precio nunca subió del strike     (strike encima: techo no tocado)
  cruzado N veces = el precio lo atravesó; se indica de qué lado cerró
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.odte.catalogo import seleccionar_0dte
from src.odte.clasificacion import clasificar_trades
from src.odte.precio import spx_1min
from src.odte.trades import descargar_tcbbo_0dte

if len(sys.argv) < 4:
    raise SystemExit("Uso: python scripts/odte/ver_strikes_0dte.py AAAA-MM-DD STRIKE_MIN STRIKE_MAX")
fecha, kmin, kmax = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])

sel = seleccionar_0dte(fecha, kmin, kmax)
tr = descargar_tcbbo_0dte(fecha, sel["raw_symbol"].tolist())
tr = tr.reset_index().merge(sel[["raw_symbol", "instrument_class", "strike_price"]],
                            left_on="symbol", right_on="raw_symbol", how="left")
tr = clasificar_trades(tr, estricto=True)
tr["size"] = tr["size"].astype("int64")
tr["estado"] = tr["signo"].map({1: "compra", -1: "venta", 0: "indet"})

spx, _ = spx_1min(fecha)
dia = spx.between_time("09:30", "16:00")["spx"]
cierre, lo, hi = dia.iloc[-1], dia.min(), dia.max()

# SPX del minuto de cada trade (el último minuto conocido, sin mirar al futuro)
ts = "ts_recv" if "ts_recv" in tr.columns else tr.columns[0]
tr = tr.sort_values(ts)
px = dia.rename("spx_min").reset_index().rename(columns={dia.index.name or "index": "minuto"})
px["minuto"] = px["minuto"] + pd.Timedelta(minutes=1)     # la barra de las 9:31 se conoce al cerrar, a las 9:32
tr = pd.merge_asof(tr, px.sort_values("minuto"), left_on=ts, right_on="minuto", direction="backward")
tr["lado"] = (tr["spx_min"] > tr["strike_price"]).map({True: "arriba", False: "abajo"})

t = tr.pivot_table(index="strike_price", columns=["instrument_class", "estado"], values="size",
                   aggfunc="sum", fill_value=0)
filas = []
for k in t.index:
    f = {"strike": int(k)}
    for tipo, nom in [("C", "calls"), ("P", "puts")]:
        c = t.loc[k].get((tipo, "compra"), 0)
        v = t.loc[k].get((tipo, "venta"), 0)
        i = t.loc[k].get((tipo, "indet"), 0)
        f[f"{nom}_neto"] = c - v
        f[f"{nom}_vol"] = c + v + i
        f[f"{nom}_%indet"] = round(i / (c + v + i) * 100) if c + v + i else None
    filas.append(f)
r = pd.DataFrame(filas).set_index("strike")


def comportamiento(k):
    arriba = dia > k
    if arriba.all():
        return "aguantó arriba"
    if (~arriba).all():
        return "aguantó abajo"
    cruces = int((arriba != arriba.shift()).iloc[1:].sum())
    return f"cruzado {cruces}x, cerró {'arriba' if cierre > k else 'abajo'}"


r["comportamiento"] = [comportamiento(k) for k in r.index]
r["% min arriba"] = [round((dia > k).mean() * 100) for k in r.index]

# Neto estricto separado por dónde estaba el precio al momento del trade
neto = tr.assign(n=tr["signo"].astype("int64") * tr["size"]).pivot_table(
    index="strike_price", columns=["instrument_class", "lado"], values="n", aggfunc="sum", fill_value=0)
for tipo, nom in [("C", "calls"), ("P", "puts")]:
    for lado in ["arriba", "abajo"]:
        r[f"{nom}_neto_precio_{lado}"] = [int(neto.loc[k].get((tipo, lado), 0)) if k in neto.index else 0
                                          for k in r.index]

pd.set_option("display.width", 200)
print(f"\n=== {fecha} | SPX rango {lo:.1f}-{hi:.1f} | cierre {cierre:.1f} | flujo ESTRICTO del público ===")
print("(neto + = el público compró, - = vendió; el dealer queda con el signo contrario)\n")
print(r[["comportamiento", "% min arriba", "calls_neto", "calls_vol", "calls_%indet",
         "puts_neto", "puts_vol", "puts_%indet"]].to_string())
print("\n=== Neto ESTRICTO según dónde estaba el SPX en el minuto del trade ===")
print("(precio_arriba = SPX por encima del strike: la put está fuera del dinero y el strike aguanta;")
print(" precio_abajo  = SPX por debajo: la put está dentro del dinero, el strike está roto)")
print(r[["comportamiento", "puts_neto_precio_arriba", "puts_neto_precio_abajo",
         "calls_neto_precio_arriba", "calls_neto_precio_abajo"]].to_string())
print(f"\nTotal: calls neto {r['calls_neto'].sum():+,} | puts neto {r['puts_neto'].sum():+,} | "
      f"indeterminado {(tr['estado'] == 'indet').mul(tr['size']).sum() / tr['size'].sum():.0%} del volumen")

# ---------------- signo del DEALER medido (sin hipótesis nula) ----------------
# Calls y puts del mismo strike tienen la MISMA gamma: se suman los contratos.
# El veredicto (src/odte/veredicto.py) exige |neto| >= MIN_ABS y que lo indeterminado NO pueda
# invertirlo (peor caso). La hipótesis nula se lee de src/gex, no se escribe a mano.
from src.gex import HIPOTESIS_NULA_PUBLICO
from src.odte.veredicto import pct_indet, signo_dealer, volumenes, vs_nula

vol = volumenes(tr, ["strike_price", "instrument_class"])
vc = vol.xs("C", level="instrument_class").reindex(r.index, fill_value=0)
vp = vol.xs("P", level="instrument_class").reindex(r.index, fill_value=0)
vt = vc + vp
r["neto_total"] = r["calls_neto"] + r["puts_neto"]
r["dealer_medido"] = [signo_dealer(*x) for x in vt.itertuples(index=False)]
r["%indet"] = [round(pct_indet(*x)) for x in vt.itertuples(index=False)]
r["calls_vs_nula"] = [vs_nula(*x, HIPOTESIS_NULA_PUBLICO["C"]) for x in vc.itertuples(index=False)]
r["puts_vs_nula"] = [vs_nula(*x, HIPOTESIS_NULA_PUBLICO["P"]) for x in vp.itertuples(index=False)]
print("\n=== Signo del DEALER MEDIDO por strike (contratos, no gamma; sin supuesto) ===")
print("(+ = dealer largo de gamma: el público vendió | - = dealer corto: el público compró)")
print("('indet. domina' = |neto| >= 200 pero lo indeterminado alcanza para invertirlo: sin signo)\n")
print(r[["comportamiento", "calls_neto", "puts_neto", "neto_total", "dealer_medido", "%indet",
         "calls_vs_nula", "puts_vs_nula"]].to_string())
print(f"\nStrikes por signo del dealer: {r['dealer_medido'].value_counts().to_dict()}")
print(f"Calls vs nula: {r['calls_vs_nula'].value_counts().to_dict()}")
print(f"Puts  vs nula: {r['puts_vs_nula'].value_counts().to_dict()}")
for estado in ["aguantó", "cerró arriba", "cerró abajo"]:
    g = r[r["comportamiento"].str.contains(estado)]
    if len(g):
        print(f"  strikes que '{estado}': dealer {g['dealer_medido'].value_counts().to_dict()}")

# ---------------- flujo ANTES del primer cruce (orden temporal) ----------------
# Solo vale el flujo previo a que el precio llegara al strike (regla de corte en src/odte/cruce.py).
from src.odte.cruce import corte_strike

tr["neto"] = tr["signo"].astype("int64") * tr["size"]
cruces, antes, min_antes, dealer_antes, indet_antes = [], [], [], [], []
for k in r.index:
    t0, etiqueta = corte_strike(dia, k)
    g = tr[tr["strike_price"] == k]
    pre = g[g[ts] < t0]
    v = volumenes(pre, "strike_price").reindex([k], fill_value=0).iloc[0]
    cruces.append(etiqueta)
    antes.append(int(pre["neto"].sum()))
    min_antes.append(int((t0 - dia.index[0]).total_seconds() // 60))
    dealer_antes.append(signo_dealer(*v))
    p = pct_indet(*v)
    indet_antes.append(None if p != p else round(p))
r["primer_cruce"], r["min_antes"], r["neto_antes_cruce"] = cruces, min_antes, antes
r["dealer_antes_cruce"], r["%indet_antes"] = dealer_antes, indet_antes
r["neto_despues_cruce"] = r["neto_total"] - r["neto_antes_cruce"]

print("\n=== Signo del dealer con el flujo ANTES del primer cruce (lo que había cuando llegó el precio) ===")
print("(min_antes = minutos de sesión antes del corte; 'nunca (aprox HH:MM)' = no se cruzó: corte en la máxima "
      "aproximación del precio)\n")
print(r[["comportamiento", "primer_cruce", "min_antes", "neto_antes_cruce", "dealer_antes_cruce", "%indet_antes",
         "neto_despues_cruce", "neto_total", "dealer_medido", "%indet"]].to_string())
print("\nResumen (antes del cruce vs día completo):")
for estado in ["aguantó", "cerró arriba", "cerró abajo"]:
    g = r[r["comportamiento"].str.contains(estado)]
    if len(g):
        print(f"  '{estado}' ({len(g)} strikes): antes del cruce {g['dealer_antes_cruce'].value_counts().to_dict()}"
              f" | día completo {g['dealer_medido'].value_counts().to_dict()}")