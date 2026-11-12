"""
Uso:  python scripts/perfil_gamma.py 2026-11-06                       (spots: cierre y ±50, ±100, ±150, ±200)
      python scripts/perfil_gamma.py 2026-11-04 7353.7 7500           (spots a mano)

El mapa de gamma de la foto de FECHA recalculado a otros precios (src/perfil_gamma.py). $0, SOLO CACHÉ.
  1. Gamma bruta (MODELO, $B por 1% de movimiento) por zona en cada spot, y cuánto envejece el ranking.
  2. Qué queda mañana: la misma foto un día de calendario después, en el mismo spot (lo que vence sale).
  3. Neto con la hipótesis nula (SUPUESTO) por spot, aparte: dónde cambiaría de signo SI el supuesto valiera.
La banda de error de un perfil recalculado la da scripts/verificar_gamma.py.

      python scripts/perfil_gamma.py --todas                          (solo guarda la rejilla de cada foto)
Cada corrida guarda la rejilla zona × spot en data/procesado/perfil_gamma_FECHA.parquet: es lo que lee
app/panel_medidas.py, que no recalcula nada.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TASA_LIBRE_RIESGO                                   # noqa: E402
from src import perfil_gamma as pg                                     # noqa: E402

pd.set_option("display.width", 250)
if len(sys.argv) < 2:
    raise SystemExit("Uso: python scripts/perfil_gamma.py FECHA [spot ...]   |   --todas")


def guardar(fecha, c):
    ruta = pg.RUTA_PERFIL.format(fecha)
    pg.rejilla(c).to_parquet(ruta)
    print(f"[perfil] {ruta}", file=sys.stderr)


if sys.argv[1] == "--todas":
    from src.odte import vista
    for f in vista.fotos():
        if os.path.exists(pg.RUTA_PERFIL.format(f)):
            continue
        try:
            guardar(f, pg.insumos(f, TASA_LIBRE_RIESGO))
        except (FileNotFoundError, ValueError) as e:
            print(f"[saltado] {e}", file=sys.stderr)
    raise SystemExit(0)

fecha = sys.argv[1]
try:
    c = pg.insumos(fecha, TASA_LIBRE_RIESGO)
except (FileNotFoundError, ValueError) as e:
    raise SystemExit(str(e))
guardar(fecha, c)
S = float(c["S"].iloc[0])
spots = [float(x) for x in sys.argv[2:]] or [S + d for d in (-200, -150, -100, -50, 0, 50, 100, 150, 200)]
if S not in spots:
    spots = sorted(spots + [S])

print(f"=== Perfil de gamma recalculado | foto {fecha}, S = {S:.1f} | {len(c)} series, "
      f"{pg.cobertura(c):.1f}% del OI con volatilidad ===")
p = pg.perfil(c, spots)
lo, hi = min(spots) - 100, max(spots) + 100
m = p.pivot(index="zona", columns="spot", values="gex_bruto") / 1e9
m = m[(m.index >= lo) & (m.index <= hi)]
m.columns = [f"{s:.0f}{'*' if s == S else ''}" for s in m.columns]
print("\n--- 1. Gamma BRUTA por zona (MODELO, $B; columna = spot hipotético, * = cierre de la foto) ---")
print(m.round(2).to_string())
print("\n    Envejecimiento del ranking de zonas (a <= 250 pts del spot nuevo):")
for s in spots:
    if s != S:
        v = pg.envejecimiento(c, s)
        print(f"    spot {s:7.1f}: Spearman con el mapa de la foto {v['spearman']:+.2f} | top-5 que siguen: "
              f"{v['top_comunes']} de 5 | bruto en la franja {v['bruto_viejo'] / 1e9:6.1f} -> {v['bruto_nuevo'] / 1e9:6.1f} $B")

print("\n--- 2. Qué queda mañana (MODELO): misma foto un día de calendario después, mismo spot ---")
hoy = pg.perfil(c, [S]).set_index("zona")["gex_bruto"]
man = pg.perfil(c, [S], avance=1 / 365).set_index("zona")["gex_bruto"]
q = pd.DataFrame(dict(hoy=hoy, manana=man)).fillna(0.0) / 1e9
q["cambio"] = q["manana"] - q["hoy"]
q = q[(q.index >= S - 250) & (q.index <= S + 250)]
print(q.reindex(q["cambio"].abs().nlargest(10).index).sort_index().round(2).to_string())
print(f"    total en la franja: {q['hoy'].sum():.1f} -> {q['manana'].sum():.1f} $B")

print("\n--- 3. Neto con la hipótesis nula (SUPUESTO, $B) y bruto total (MODELO) por spot ---")
tot = p.groupby("spot")[["gex_sup", "gex_bruto"]].sum() / 1e9
tot["neto/bruto_%"] = 100 * tot["gex_sup"] / tot["gex_bruto"]
print(tot.round(1).to_string())
print("    El neto es una resta de dos números grandes con signo SUPUESTO: no es un nivel medido.")
