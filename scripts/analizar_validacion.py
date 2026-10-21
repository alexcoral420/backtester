"""
Uso:  python scripts/analizar_validacion.py

Analiza TODAS las ventanas acumuladas por validar_gex (data/validacion/gex_dias.csv). $0, sin descargas.

Reglas (aprendidas el 12-oct, no negociables):
  1. Los días NO son independientes: el GEX cambia lento y viene en rachas. Se reportan EPISODIOS
     (rachas de un mismo signo), y el tamaño honesto de la muestra es el número de episodios.
  2. Todo se compara contra el PREDICTOR INGENUO: el rango de hoy (la volatilidad se agrupa sola).
     Si el GEX no le gana, no aporta nada para operar.
  3. La prueba que importa: días con rango de hoy PARECIDO y signo de GEX distinto.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RUTA = "data/validacion/gex_dias.csv"
if not os.path.exists(RUTA):
    raise SystemExit(f"No existe {RUTA}: corre primero scripts/validar_gex.py en alguna ventana.")
t = pd.read_csv(RUTA, parse_dates=["fecha"]).sort_values("fecha").reset_index(drop=True)
pd.set_option("display.width", 200)


def episodios(df, col):
    """Rachas de un mismo signo. Un hueco de más de 7 días corridos entre fechas corta la racha (otra ventana)."""
    signo = np.sign(df[col])
    corte = (signo != signo.shift()) | (df["fecha"].diff().dt.days > 7)
    return corte.cumsum()


print(f"=== {len(t)} días acumulados | {t['fecha'].min():%Y-%m-%d} a {t['fecha'].max():%Y-%m-%d} ===")

for metodo in ["nuevo", "viejo"]:
    col = f"gex_{metodo}"
    t["ep"] = episodios(t, col)
    eps = t.groupby("ep").agg(desde=("fecha", "min"), hasta=("fecha", "max"), dias=("fecha", "size"),
                              signo=(col, lambda g: "+" if g.iloc[0] > 0 else "-"),
                              rango_sig_med=("rango_pct", "median"), rango_hoy_med=("rango_hoy_pct", "median"))
    print(f"\n=== Método {metodo}: {len(eps)} episodios (= tamaño honesto de la muestra) ===")
    e = eps.copy()
    e["desde"], e["hasta"] = e["desde"].dt.strftime("%Y-%m-%d"), e["hasta"].dt.strftime("%Y-%m-%d")
    print(e.round(2).to_string(index=False))
    pos, neg = eps[eps["signo"] == "+"], eps[eps["signo"] == "-"]
    print(f"  Por episodio: GEX+ ({len(pos)} ep.) rango siguiente mediana {pos['rango_sig_med'].median():.2f}% | "
          f"GEX- ({len(neg)} ep.) {neg['rango_sig_med'].median():.2f}%")

print("\n=== Contra el predictor ingenuo (Spearman con el rango de mañana; días, solo orientativo) ===")
for col, nombre in [("rango_hoy_pct", "rango de hoy (ingenuo)"), ("gex_nuevo", "GEX nuevo (nivel)"),
                    ("gex_viejo", "GEX viejo (nivel)")]:
    print(f"  {nombre:24s}: {t[col].corr(t['rango_pct'], method='spearman'):+.2f}")
t["signo_nuevo"] = np.sign(t["gex_nuevo"])
print(f"  {'signo GEX nuevo':24s}: {t['signo_nuevo'].corr(t['rango_pct'], method='spearman'):+.2f}")

print("\n=== LA PRUEBA: mismo rango de hoy, distinto signo de GEX (método nuevo) ===")
t["tercio_hoy"] = pd.qcut(t["rango_hoy_pct"], 3, labels=["hoy bajo", "hoy medio", "hoy alto"])
p = t.pivot_table(index="tercio_hoy", columns="signo_nuevo", values="rango_pct",
                  aggfunc=["median", "size"], observed=False)
p.columns = [f"{'mediana %' if a == 'median' else 'n días'} GEX{'+' if b > 0 else '-'}" for a, b in p.columns]
print(p.round(2).to_string())
t["ep"] = episodios(t, "gex_nuevo")
cruce = t.groupby(["tercio_hoy", "signo_nuevo"], observed=True)["ep"].nunique().unstack()
cruce.columns = [f"episodios GEX{'+' if c > 0 else '-'}" for c in cruce.columns]
print(cruce.to_string())
print("  Una celda con 1-2 episodios NO es evidencia, aunque tenga muchos días.")