"""
Uso:  python scripts/verificar_gamma.py                    (todas las fotos consecutivas de data/procesado)
      python scripts/verificar_gamma.py 2026-10-26 2026-11-06

¿Se puede confiar en la gamma RECALCULADA a otro precio (src/perfil_gamma.py)? $0, SOLO CACHÉ.

Para cada par de fotos de días de mercado seguidos (d, d+1):
  - identidad: la gamma de d recalculada en su propio spot reproduce la guardada (si no, grita);
  - realidad: la gamma de d llevada al spot y al plazo del cierre de d+1 (vol fija) contra la gamma REAL de
    la foto de d+1, sobre las mismas series, con el OI de d, en las zonas a <= 250 pts del spot nuevo;
  - al lado, el error de usar la foto VIEJA sin recalcular. El recálculo solo sirve si su error es menor.
Todo es MODELO (gamma · OI sin signo): aquí no entra la hipótesis nula.

err_* = suma por zona de |x − real| en % del real. sesgo > 0 = el recálculo dio MÁS gamma que la real
(típico cuando la volatilidad subió: la vol fija se queda corta).
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TASA_LIBRE_RIESGO                                   # noqa: E402
from src import perfil_gamma as pg                                     # noqa: E402
from src.odte import vista                                             # noqa: E402

pd.set_option("display.width", 250)
if len(sys.argv) not in (1, 3):
    raise SystemExit("Uso: python scripts/verificar_gamma.py [INICIO FIN]")
fotos = vista.fotos()
if len(sys.argv) == 3:
    fotos = [f for f in fotos if sys.argv[1] <= f <= sys.argv[2]]

cadenas, filas = {}, []
for f in fotos:
    try:
        cadenas[f] = pg.insumos(f, TASA_LIBRE_RIESGO)                  # incluye la identidad
    except (FileNotFoundError, ValueError) as e:
        print(f"[saltado] {e}", file=sys.stderr)
for a, b in zip(fotos, fotos[1:]):
    if a not in cadenas or b not in cadenas:
        continue
    if (pd.Timestamp(a) + pd.offsets.BDay(1)).strftime("%Y-%m-%d") != b:
        print(f"[saltado] {a} -> {b}: no son días hábiles seguidos", file=sys.stderr)
        continue
    e = pg.error_prediccion(cadenas[a], cadenas[b])
    v = pg.envejecimiento(cadenas[a], e["S2"])
    filas.append(dict(foto=a, sig=b, S=e["S"], S_sig=e["S2"], mov_pct=100 * (e["S2"] / e["S"] - 1),
                      cubierto_pct=e["pct_cubierto"], err_recalculada=e["err_recalculada"],
                      err_vieja=e["err_vieja"], sesgo=e["sesgo_recalculada"],
                      rho_recalculada=e["spearman_recalculada"], rho_vieja=e["spearman_vieja"],
                      top5_que_siguen=v["top_comunes"]))
if not filas:
    raise SystemExit("No hay pares de fotos consecutivas para verificar.")
t = pd.DataFrame(filas)

print(f"=== Gamma recalculada contra la foto real del día siguiente | {len(t)} pares | MODELO, sin signo ===")
print(f"identidad: {len(cadenas)} fotos reproducen su gamma guardada (tolerancia {pg.TOL_IDENTIDAD:.0e}); "
      f"OI con volatilidad: mediana {pd.Series([pg.cobertura(c) for c in cadenas.values()]).median():.1f}%\n")
print(t.round(2).to_string(index=False))

gana = int((t["err_recalculada"] < t["err_vieja"]).sum())
print(f"\nError por zona (% del real, zonas a <= {pg.RADIO} pts): recalculada mediana {t['err_recalculada'].median():.1f} "
      f"(peor {t['err_recalculada'].max():.1f}) | vieja mediana {t['err_vieja'].median():.1f} (peor {t['err_vieja'].max():.1f})")
print(f"La recalculada tiene menos error que la foto vieja en {gana} de {len(t)} pares.")
t["mov_abs"] = t["mov_pct"].abs()
for nombre, x in (("movimiento < 0,5%", t[t["mov_abs"] < 0.5]), ("0,5% a 1%", t[(t["mov_abs"] >= 0.5) & (t["mov_abs"] < 1)]),
                  (">= 1%", t[t["mov_abs"] >= 1])):
    if len(x):
        print(f"  {nombre:18s} n={len(x):2d}  recalculada {x['err_recalculada'].median():5.1f}  vieja {x['err_vieja'].median():5.1f}"
              f"  sesgo {x['sesgo'].median():+5.1f}  top-5 de la foto que siguen top-5: {x['top5_que_siguen'].median():.0f}")
print("\nLectura: err_recalculada es la banda de error con la que hay que leer cualquier perfil recalculado a ese"
      "\ntamaño de movimiento. El sesgo no se corrige: corregirlo sería suponer cómo se mueve la volatilidad.")
