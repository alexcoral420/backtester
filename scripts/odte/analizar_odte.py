"""
Uso:  python scripts/odte/analizar_odte.py                         (todas las definiciones acumuladas)
      python scripts/odte/analizar_odte.py p25_t2_d1000_v30_m5     (solo esa)

Analiza la muestra de toques 0DTE acumulada por validar_0dte (data/validacion/odte_toques.csv). $0.

Reglas (las mismas de analizar_validacion, adaptadas):
  1. Los toques de un mismo día NO son independientes (mismo régimen, mismo flujo, mismo recorrido).
     Tamaño honesto de la muestra = número de DÍAS (episodios), no de toques.
  2. Todo contra el PREDICTOR INGENUO:
       a) frecuencia base: predecir siempre el resultado más común de toda la muestra;
       b) recorrido: "aguanta si llegó desde lejos" (dist_previa > mediana).
     El signo medido del dealer tiene que ganarles EN LOS MISMOS toques.
  3. Hipótesis a probar: dealer + (largo de gamma) -> aguanta; dealer - (corto) -> se cruza.
     Solo los toques con signo medido (veredicto con peor caso) entran a la prueba. Los demás se
     cuentan, no se adivinan.

M2 está CERRADA (ODTE.md): el signo no es identificable con la regla de cotización. La sección
"Por qué no hay signo" deja la evidencia reproducible: la razón |neto| / indet, de qué está hecho lo
indeterminado, y si el signo cambia al firmar el interior del spread por cercanía (INFERIDO, no medido).
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.odte.toques import AGUANTO, CRUZO
from src.odte.veredicto import signo_dealer

RUTA = "data/validacion/odte_toques.csv"
MIN_DIAS = 10    # por debajo, una tasa de acierto no es evidencia (como las celdas de 1-2 episodios del GEX)

if not os.path.exists(RUTA):
    raise SystemExit(f"No existe {RUTA}: correr antes scripts/odte/validar_0dte.py")
todo = pd.read_csv(RUTA, dtype={"fecha": str})
defs = [sys.argv[1]] if len(sys.argv) > 1 else sorted(todo["definicion"].unique())
pd.set_option("display.width", 200)


def acierto(t, pred):
    """% de toques donde la predicción coincide con el resultado."""
    return float("nan") if t.empty else 100.0 * (pred == t["resultado"]).mean()


for nombre in defs:
    t0 = todo[todo["definicion"] == nombre]
    if t0.empty:
        raise SystemExit(f"Definición {nombre!r} sin filas. Hay: {sorted(todo['definicion'].unique())}")
    t = t0[t0["resultado"].isin([AGUANTO, CRUZO])].copy()
    print(f"\n=== Definición {nombre}: {len(t0)} toques en {t0['fecha'].nunique()} días "
          f"({t0['fecha'].min()} a {t0['fecha'].max()}); {len(t0) - len(t)} con ventana corta, fuera ===")
    if t.empty:
        continue

    base = (t["resultado"] == AGUANTO).mean()
    mayoria = AGUANTO if base >= 0.5 else CRUZO
    print(f"Frecuencia base: aguantó {100 * base:.0f}% de {len(t)} toques ({t['fecha'].nunique()} días)")

    por_dia = t.groupby("fecha").agg(toques=("strike", "size"),
                                      aguanto=("resultado", lambda r: int((r == AGUANTO).sum())),
                                      con_signo=("dealer_medido", lambda s: int(s.isin(["+", "-"]).sum())),
                                      pct_indet_med=("pct_indet", "median"))
    print("\n--- Por día (= episodio) ---")
    print(por_dia.round(1).to_string())

    print("\n--- Veredicto del signo MEDIDO antes del toque (peor caso contra lo indeterminado) ---")
    v = t.groupby("dealer_medido").agg(toques=("strike", "size"), dias=("fecha", "nunique"),
                                       pct_aguanto=("resultado", lambda r: 100 * (r == AGUANTO).mean()),
                                       pct_indet_med=("pct_indet", "median"))
    print(v.round(1).to_string())

    firmados = t[t["dealer_medido"].isin(["+", "-"])]
    n_dias = firmados["fecha"].nunique()
    print(f"\n--- LA PRUEBA: dealer + -> aguanta, dealer - -> cruza ({len(firmados)} toques, {n_dias} días) ---")
    if firmados.empty:
        print("  Ningún toque con signo medido: la prueba no se puede hacer. Ninguno pasó las dos pruebas")
        print("  del veredicto (ver tabla de arriba). Resultado de la muestra: SIN EVIDENCIA.")
    else:
        hip = firmados["dealer_medido"].map({"+": AGUANTO, "-": CRUZO})
        lejos = t["dist_previa"] > t["dist_previa"].median()
        rec = lejos.map({True: AGUANTO, False: CRUZO})
        print(f"  signo medido            : {acierto(firmados, hip):.0f}% de acierto")
        print(f"  ingenuo, frecuencia base: {acierto(firmados, mayoria):.0f}% (siempre '{mayoria}')")
        print(f"  ingenuo, recorrido      : {acierto(firmados, rec.loc[firmados.index]):.0f}%")
        if n_dias < MIN_DIAS:
            print(f"  Con {n_dias} días (< {MIN_DIAS}) esto NO es evidencia, aunque haya muchos toques.")

    print("\n--- Ingenuos en toda la muestra (referencia) ---")
    lejos = t["dist_previa"] > t["dist_previa"].median()
    print(f"  frecuencia base: {acierto(t, mayoria):.0f}% | recorrido (mediana {t['dist_previa'].median():.1f} pts): "
          f"{acierto(t, lejos.map({True: AGUANTO, False: CRUZO})):.0f}%")

    if "neto_inferido_interior" in t.columns:
        print("\n--- Por qué no hay signo (evidencia del cierre de M2) ---")
        con = t[t["indet"] > 0]
        razon = con["neto"].abs() / con["indet"]
        print(f"  |neto| / indet: mediana {razon.median():.3f}, máximo {razon.max():.2f} (el peor caso exige > 1)")
        print("  Toques que pasarían con un umbral menor: "
              + ", ".join(f"> {int(100 * u)}%: {int((razon > u).sum())}" for u in (1, .5, .25, .1, .05)))
        comp = con[["indet_medio", "indet_interior", "indet_fuera", "indet_sin_cotizacion"]].div(con["indet"], axis=0)
        print("  Lo indeterminado, % del indet. por toque (mediana / mín / máx):")
        for c, nom in [("indet_medio", "en el punto medio (ninguna regla lo firma)"),
                       ("indet_interior", "interior del spread"), ("indet_fuera", "fuera del spread (paquetes)"),
                       ("indet_sin_cotizacion", "sin cotización")]:
            print(f"    {nom:42s}: {100 * comp[c].median():3.0f} / {100 * comp[c].min():3.0f} / {100 * comp[c].max():3.0f}")
        n = con[(con["neto"] != 0) & (con["neto_inferido_interior"] != 0)]
        igual = int((n["neto"].gt(0) == n["neto_inferido_interior"].gt(0)).sum())
        print(f"  Signo del neto estricto vs del interior INFERIDO (por cercanía): coincide en {igual} de {len(n)}")
        # Interior firmado por cercanía (INFERIDO): cerca del ask = compra, cerca del bid = venta.
        # El medio, lo de fuera y lo sin cotización siguen indeterminados.
        ia = (con["indet_interior"] + con["neto_inferido_interior"]) // 2
        ib = con["indet_interior"] - ia
        relaj = [signo_dealer(int(c + a), int(v + b), int(m + f + s)) for c, v, a, b, m, f, s in
                 zip(con["compra"], con["venta"], ia, ib, con["indet_medio"], con["indet_fuera"],
                     con["indet_sin_cotizacion"])]
        print(f"  Veredicto con el interior firmado por cercanía (INFERIDO): {pd.Series(relaj).value_counts().to_dict()}")

    print("\n--- Descriptivo del flujo MEDIDO por resultado (medianas; sin signo, no es una predicción) ---")
    print(t.groupby("resultado")[["neto", "pct_indet", "dist_previa", "peor_exceso"]].median().round(1).to_string())
