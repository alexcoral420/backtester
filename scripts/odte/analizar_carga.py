"""
Uso:  python scripts/odte/analizar_carga.py                                 (todo lo acumulado)
      python scripts/odte/analizar_carga.py p25_t2_d1000_v30_m5             (solo esa definición)
      python scripts/odte/analizar_carga.py p25_t2_d1000_v30_m5 tocadas     (solo esa definición y referencia)
Cada (definición, referencia) se analiza aparte. Con la referencia "tocadas", los toques sin comparación (única
zona de su clase tocada ese día) quedan fuera y se cuentan.

Analiza M4 (ODTE.md, "Diseño fijo de M4") sobre data/validacion/odte_carga.csv. $0.
Pregunta: dentro de cada clase de redondez (100 / 50 / 25), ¿las zonas de carga relativa alta aguantan más?

Reglas:
  1. Episodio = día. Con menos de MIN_DIAS días en una celda: "NO es evidencia".
  2. La carga tiene que ganarles a los ingenuos EN LOS MISMOS toques: frecuencia base, "múltiplo de 100
     aguanta" y distancia previa.
  3. Control por zona (las zonas se repiten por rotación): un voto por zona y dejar una zona fuera.
  4. El wall SUPUESTO (signo de la hipótesis nula) es un predictor más, rotulado, nunca mezclado con la carga.
  5. Todo con y sin los días d1_vieja (el 10-21: su gamma MODELO sale de una foto dos sesiones vieja).
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.odte import carga as cg
from src.odte.toques import AGUANTO

RUTA = "data/validacion/odte_carga.csv"
NOMBRES = {"base": "ingenuo: frecuencia base", "mult100": "ingenuo: múltiplo de 100 aguanta",
           "distancia": "ingenuo: distancia previa", "carga_oi": "CARGA OI (MEDIDA)",
           "carga_bruto": "CARGA gamma bruta (MODELO)", "wall_sup": "wall con signo (SUPUESTO)"}

if not os.path.exists(RUTA):
    raise SystemExit(f"No existe {RUTA}: correr antes scripts/odte/validar_carga.py")
todo = pd.read_csv(RUTA, dtype={"fecha": str, "clase": str})
if "referencia" not in todo.columns:                  # acumulador de antes de la variante: todo radio250
    todo["referencia"] = cg.REFERENCIA_FIJA
grupos = sorted(todo.groupby(["definicion", "referencia"]).groups)
if len(sys.argv) > 1:
    grupos = [g for g in grupos if g[0] == sys.argv[1] and (len(sys.argv) < 3 or g[1] == sys.argv[2])]
    if not grupos:
        raise SystemExit(f"Sin filas para {sys.argv[1:]}. Hay: "
                         f"{sorted(todo.groupby(['definicion', 'referencia']).groups)}")
pd.set_option("display.width", 200)


def reporte(t, titulo):
    print(f"\n##### {titulo}: {len(t)} toques, {t['fecha'].nunique()} días, {t['strike'].nunique()} zonas #####")
    print(f"Frecuencia base: aguantó {cg.tasa(t):.0f}%")

    for col, rot in (("pct_carga_oi", "OI, MEDIDA"), ("pct_carga_bruto", "gamma bruta, MODELO")):
        print(f"\n--- Celdas clase × mitad de carga ({rot}; alta = >= mediana de su clase ese día) ---")
        print(cg.celdas(t, col).round(1).to_string())
        dif = cg.diferencia(t, col)
        v = cg.voto_por_zona(t, col)
        print(f"  Diferencia alta − baja (pts de % de aguante), por toque: {dif:+.1f}")
        print(f"  Un voto por zona ({v['zonas']} zonas: {v['alta']} alta, {v['baja']} baja): {v['diferencia']:+.1f}")
        f = cg.dejar_una_fuera(t, col)
        da = f[f["cambia_signo"] == True]                                           # noqa: E712
        print(f"  Dejar una zona fuera: diferencia entre {f['diferencia_sin'].min():+.1f} y {f['diferencia_sin'].max():+.1f}; "
              + ("ninguna zona sola da vuelta el signo" if da.empty else
                 "DEPENDE DE LA ZONA " + ", ".join(f"{int(r.zona)} ({r.toques} toques)" for r in da.itertuples())))

    print("\n--- Predictores sobre los MISMOS toques (% de acierto) ---")
    for k, v in cg.aciertos(t).items():
        print(f"  {NOMBRES[k]:34s}: {v:5.1f}%")
    n = t["fecha"].nunique()
    if n < cg.MIN_DIAS:
        print(f"  Con {n} días (< {cg.MIN_DIAS}) esto NO es evidencia.")
    print("  (la carga tiene que ganarles a los tres ingenuos para decir algo; con muestras chicas,"
          " 1-2 toques mueven varios puntos)")


for nombre, ref in grupos:
    t0 = todo[(todo["definicion"] == nombre) & (todo["referencia"] == ref)]
    t = cg.contables(t0)
    print(f"\n=== M4, definición {nombre}, referencia {ref}: {len(t0)} toques en {t0['fecha'].nunique()} días "
          f"({t0['fecha'].min()} a {t0['fecha'].max()}); {len(t0) - len(t)} con ventana corta, fuera ===")
    sin_comp = t["pct_carga_oi"].isna() | t["pct_carga_bruto"].isna()
    if sin_comp.any():
        print(f"Sin comparación (única zona de su clase tocada ese día): {int(sin_comp.sum())} toques, fuera; "
              f"quedan {int((~sin_comp).sum())} en {t.loc[~sin_comp, 'fecha'].nunique()} días")
        t = t[~sin_comp]
    print(f"Fuera del radio de referencia (±{cg.RADIO} pts del cierre de d−1): {int(t['fuera_radio'].sum())} toques")

    por_dia = t.groupby("fecha").agg(toques=("strike", "size"),
                                      aguanto=("resultado", lambda r: int((r == AGUANTO).sum())),
                                      zonas=("strike", lambda s: ", ".join(str(int(x)) for x in s)),
                                      d1_vieja=("d1_vieja", "first"))
    print("\n--- Por día (= episodio) ---")
    print(por_dia.to_string())

    print("\n--- Zonas que se repiten (rotación) ---")
    rep = t.groupby("strike").agg(toques=("fecha", "size"), dias=("fecha", "nunique"),
                                  pct_aguanto=("resultado", lambda r: 100 * (r == AGUANTO).mean()),
                                  oi_k_mediana=("oi_total", lambda s: s.median() / 1e3),
                                  pct_carga_oi_med=("pct_carga_oi", "median"), clase=("clase", "first"))
    print(rep.sort_values("toques", ascending=False).round(0).to_string())

    reporte(t, "Toda la muestra")
    sin = t[~t["d1_vieja"].astype(bool)]
    if len(sin) < len(t):
        reporte(sin, "Sin los días d1_vieja")

    print("\n--- Descriptivo por resultado (medianas; no es una predicción) ---")
    print(t.groupby("resultado")[["pct_carga_oi", "pct_carga_bruto", "dist_previa", "peor_exceso"]]
          .median().round(1).to_string())
