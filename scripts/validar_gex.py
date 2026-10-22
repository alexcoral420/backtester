"""
Uso:  python scripts/validar_gex.py 2026-03-25 2026-04-05
      python scripts/validar_gex.py 2026-03-25 2026-04-05 --spxw   (SPX+SPXW, plazo horas)

Validación (fase E, versión inicial): ¿el GEX del CIERRE de un día anticipa el día SIGUIENTE?
Regla anti-trampa: siempre la foto de la víspera contra lo que pasó después, nunca el mismo día.

Para cada día de mercado del rango (los da yfinance: feriados y fines de semana se saltan solos):
  - GEX de los dos métodos y su CAMBIO en $B contra el día anterior del rango
    (en $B y no en %: con GEX negativo el % invierte el signo; -27B -> -17B es una SUBIDA)
  - del día siguiente: máximo, mínimo, rango (pts y %)
  - wall más cercano arriba/abajo de cada método, y si el día siguiente lo TOCÓ o lo CRUZÓ (cierre)
Cadenas en caché: $0. Las que falten: UNA confirmación con el costo total (~$0,20 por día;
con --spxw ~$0,66 por día sin caché).

--spxw: los dos métodos con raíces SPX+SPXW y T con hora (plazo="horas"). Va a OTRO acumulador
(data/validacion/gex_dias_spxw.csv): el de siempre no se toca y las filas nunca se mezclan.
"""
import os
import sys

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.datos import asegurar_cadenas
from src.gex import construir_cadena, gamma_walls, gex_total

METODOS = {"viejo": "ultimo_trade", "nuevo": "mid_forward"}

SPXW = "--spxw" in sys.argv
sys.argv = [a for a in sys.argv if a != "--spxw"]
RAICES, PLAZO = (("SPX", "SPXW"), "horas") if SPXW else (("SPX",), "dias")

if len(sys.argv) < 3:
    raise SystemExit("Uso: python scripts/validar_gex.py INICIO FIN   (ej: 2026-03-25 2026-04-05), "
                     "desde la raíz del proyecto")
inicio, fin = sys.argv[1], sys.argv[2]
hist = yf.Ticker("^GSPC").history(start=inicio, end=(pd.to_datetime(fin) + pd.Timedelta(days=10)).strftime("%Y-%m-%d"))
hist.index = hist.index.tz_localize(None).normalize()
dias = [d for d in hist.index if d <= pd.to_datetime(fin)]

asegurar_cadenas([d.strftime("%Y-%m-%d") for d in dias], RAICES)      # UNA sola confirmación de costo

filas = []
for i, dia in enumerate(dias):
    if i + 1 >= len(hist.index):
        print(f"{dia:%Y-%m-%d}: sin día siguiente en yfinance, se omite")
        continue
    fecha, sig = dia.strftime("%Y-%m-%d"), hist.index[i + 1]
    S = float(hist.loc[dia, "Close"])
    alto, bajo, cierre_sig = (float(hist.loc[sig, c]) for c in ("High", "Low", "Close"))
    h_hoy, l_hoy = float(hist.loc[dia, "High"]), float(hist.loc[dia, "Low"])
    f = dict(fecha=fecha, sig=sig.strftime("%m-%d"), S=S, rango=alto - bajo, rango_pct=(alto - bajo) / S * 100,
             rango_hoy_pct=(h_hoy - l_hoy) / S * 100)        # el predictor ingenuo: lo que ya se sabía al cierre
    for nombre, metodo in METODOS.items():
        c = construir_cadena(fecha, S, metodo=metodo, raices=RAICES, plazo=PLAZO).dropna(subset=["gex_contrib"])
        arriba, abajo = gamma_walls(c, S, n=5)
        w_ar = arriba["nivel"].min() if len(arriba) else float("nan")      # wall más cercano arriba
        w_ab = abajo["nivel"].max() if len(abajo) else float("nan")        # wall más cercano abajo
        f[f"gex_{nombre}"] = gex_total(c) / 1e9
        f[f"ar_{nombre}"] = f"{w_ar:.0f} " + ("cruzó" if cierre_sig > w_ar else "tocó" if alto >= w_ar else "-")
        f[f"ab_{nombre}"] = f"{w_ab:.0f} " + ("cruzó" if cierre_sig < w_ab else "tocó" if bajo <= w_ab else "-")
    filas.append(f)

t = pd.DataFrame(filas).set_index("fecha")
for nombre in METODOS:
    t[f"cambio_{nombre}"] = t[f"gex_{nombre}"].diff()

# Acumulador: cada corrida suma (o reemplaza) sus días en un solo CSV para analizar todas las ventanas juntas
RUTA_ACUM = "data/validacion/gex_dias_spxw.csv" if SPXW else "data/validacion/gex_dias.csv"
os.makedirs(os.path.dirname(RUTA_ACUM), exist_ok=True)
acum = pd.read_csv(RUTA_ACUM, index_col="fecha") if os.path.exists(RUTA_ACUM) else pd.DataFrame()
acum = pd.concat([acum[~acum.index.isin(t.index)], t]).sort_index()
acum.to_csv(RUTA_ACUM, index_label="fecha")
print(f"[acumulado] {len(t)} días guardados en {RUTA_ACUM} (total {len(acum)}). "
      f"Análisis conjunto: python scripts/analizar_validacion.py {RUTA_ACUM if SPXW else ''}")

pd.set_option("display.width", 250)
print(f"\n=== GEX al cierre (víspera) vs el día SIGUIENTE | {inicio} a {fin} | {'+'.join(RAICES)}, plazo {PLAZO} ===")
print(t[["S", "gex_viejo", "cambio_viejo", "gex_nuevo", "cambio_nuevo", "sig", "rango", "rango_pct"]]
      .round(2).to_string())

print("\n=== Walls más cercanos de la víspera: ¿el día siguiente los tocó o cruzó? ===")
print(t[["S", "sig", "ar_viejo", "ar_nuevo", "ab_viejo", "ab_nuevo"]].round(2).to_string())

if len(t) >= 4:
    print("\n=== Relación con el rango del día siguiente (Spearman; negativa = más GEX, rango más corto) ===")
    for col in ["gex_viejo", "gex_nuevo", "cambio_viejo", "cambio_nuevo"]:
        s = t[[col, "rango_pct"]].dropna()
        print(f"  {col:15s}: {s[col].corr(s['rango_pct'], method='spearman'):+.2f}  (n = {len(s)})")
    print("  (con menos de ~20 días esto es orientativo, no estadística)")