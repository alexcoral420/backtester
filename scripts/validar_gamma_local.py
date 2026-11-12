"""
Uso:  python scripts/validar_gamma_local.py 2026-09-25 2026-11-06     (suma esos días al acumulador y analiza)
      python scripts/validar_gamma_local.py                           (solo analiza el acumulador)

Pregunta SIN SIGNO: cuando la gamma bruta en el precio actual es alta, ¿el SPX se mueve distinto en los
30 minutos siguientes? (Con el dealer comprado en gamma se movería menos; vendido, más. Aquí no se supone.)

Por día d y por bloque de 30 min desde las 10:00 (src/perfil_gamma.py):
  MODELO   gex_bruto_B, gex_local_B: la foto de d−1 llevada al spot y a la hora del inicio del bloque, sin
           lo que vence en d (vol fija; su banda de error: scripts/verificar_gamma.py)
  MEDIDO   rango_prev_pct (los 30 min previos: el predictor INGENUO), rango_sig_pct (el objetivo),
           impl_prev_pct (straddle del cierre de d−1, de data/validacion/rango_implicito.csv),
           spx (el NIVEL del índice al inicio del bloque: el segundo ingenuo. La gamma bruta sube y baja con el
           precio, así que solo aporta lo que quede después de descontarlo: sección E)

$0, SOLO CACHÉ: un día sin ES 1-min, sin SPX 5m de yfinance o sin la foto del día de mercado anterior se
salta y se lista. Acumulador propio: data/validacion/gamma_local.csv.

Reglas: la gamma se conoce ANTES del bloque; todo contra el ingenuo; los bloques de un día no son
independientes, así que el tamaño honesto de la muestra son los DÍAS. Dos confusiones conocidas, por eso
dos cortes: la gamma de corto plazo sube sola con la hora (corte por FRANJA, entre días) y el nivel del día
depende del régimen de volatilidad (corte por DÍA, entre bloques).
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TASA_LIBRE_RIESGO                                   # noqa: E402
from src import perfil_gamma as pg                                     # noqa: E402
from src import vista_medidas as vm                                    # noqa: E402
from src.odte import vista                                             # noqa: E402
from src.simbolos import HORA_FOTO                                     # noqa: E402

RUTA = "data/validacion/gamma_local.csv"
RUTA_IMPL = "data/validacion/rango_implicito.csv"
PREDICTORES = ["gex_bruto_B", "gex_local_B", "spx", "rango_prev_pct", "impl_prev_pct"]   # spx = el NIVEL del índice
pd.set_option("display.width", 250)

if len(sys.argv) not in (1, 3):
    raise SystemExit("Uso: python scripts/validar_gamma_local.py [INICIO FIN]")

if len(sys.argv) == 3:
    impl = pd.read_csv(RUTA_IMPL, index_col="fecha")["impl_pct"] if os.path.exists(RUTA_IMPL) else pd.Series(dtype=float)
    partes = []
    for fecha in [d.strftime("%Y-%m-%d") for d in pd.bdate_range(sys.argv[1], sys.argv[2])]:
        prev = (pd.Timestamp(fecha) - pd.offsets.BDay(1)).strftime("%Y-%m-%d")
        try:
            spx = vista.spx_dia(fecha)
            c_prev = pg.insumos(prev, TASA_LIBRE_RIESGO)
        except (vista.SinDatos, FileNotFoundError, ValueError) as e:
            print(f"[saltado] {fecha}: {e}", file=sys.stderr)
            continue
        b = pg.bloques(spx)
        if b.empty:
            print(f"[saltado] {fecha}: sin bloques completos", file=sys.stderr)
            continue
        cierre_prev = pd.Timestamp(f"{prev} {HORA_FOTO[0]:02d}:{HORA_FOTO[1]:02d}", tz="America/New_York")
        g = pg.serie_intradia(c_prev, b.set_index("t")["spx"], fecha, cierre_prev)
        b["gex_bruto_B"], b["gex_local_B"] = g["gex_bruto"].to_numpy() / 1e9, g["gex_bruto_local"].to_numpy() / 1e9
        b["impl_prev_pct"] = impl.get(prev, float("nan"))
        b.insert(0, "fecha", fecha)
        b["t"] = b["t"].dt.strftime("%H:%M")
        partes.append(b)
        print(f"[día] {fecha}: {len(b)} bloques, foto {prev}", file=sys.stderr)
    if partes:
        nuevo = pd.concat(partes, ignore_index=True)
        os.makedirs(os.path.dirname(RUTA), exist_ok=True)
        acum = pd.read_csv(RUTA) if os.path.exists(RUTA) else pd.DataFrame(columns=nuevo.columns)
        acum = pd.concat([acum[~acum["fecha"].isin(nuevo["fecha"])], nuevo]).sort_values(["fecha", "t"])
        acum.round(6).to_csv(RUTA, index=False)
        print(f"[acumulado] {nuevo['fecha'].nunique()} días guardados en {RUTA} (total {acum['fecha'].nunique()})",
              file=sys.stderr)

if not os.path.exists(RUTA):
    raise SystemExit(f"No existe {RUTA}: corre primero con un rango de fechas.")
t = pd.read_csv(RUTA)
dias = t["fecha"].nunique()
print(f"=== Gamma bruta en el precio actual (MODELO) contra el rango de los 30 min siguientes | "
      f"{len(t)} bloques, {dias} días ({t['fecha'].min()} a {t['fecha'].max()}) ===")

print("\n--- A. Misma FRANJA horaria, entre días (quita el efecto de la hora): Spearman por franja ---")
filas = []
for col in PREDICTORES:
    r = pg.relacion_por_grupo(t, "t", col, "rango_sig_pct")
    filas.append(dict(predictor=col, clase=vm.clase(col), franjas=len(r),
                      mediana=r.median(), negativas=int((r < 0).sum()), minimo=r.min(), maximo=r.max()))
print(pd.DataFrame(filas).round(2).to_string(index=False))

print("\n--- B. Mismo DÍA, entre bloques (quita el régimen del día): Spearman por día; muestra = días ---")
filas = []
for col in PREDICTORES[:4]:
    r = pg.relacion_por_grupo(t, "fecha", col, "rango_sig_pct")
    filas.append(dict(predictor=col, dias=len(r), mediana=r.median(), dias_negativos=int((r < 0).sum()),
                      dias_positivos=int((r > 0).sum())))
print(pd.DataFrame(filas).round(2).to_string(index=False))
print("    Ojo: dentro del día la gamma de corto plazo sube con la hora y el rango tiene forma de U.")

print("\n--- C. LA PRUEBA, por DÍA: mismo control, distinta gamma bruta ---")
print("    Una fila por día (mediana de sus bloques); alto / bajo contra la mediana de los DEMÁS días. Columnas:"
      "\n    rango siguiente (mediana, %) con gamma alta y baja, y cuántos días hay en cada celda.")
MIN_DIAS = 10
for control, nombre in (("rango_prev_pct", "rango de los 30 min previos (ingenuo)"),
                        ("impl_prev_pct", "straddle de la víspera"), ("spx", "nivel del SPX (ingenuo)")):
    x = pg.tabla_por_dia(t, control)
    chicas = int((x[["dias_pred_alto", "dias_pred_bajo"]] < MIN_DIAS).sum().sum())
    print(f"  control = {nombre}  [{vm.clase(control)}]")
    print(x.rename(columns={"objetivo_pred_alto": "gamma alta", "objetivo_pred_bajo": "gamma baja",
                            "dias_pred_alto": "días g. alta", "dias_pred_bajo": "días g. baja"}).round(3).to_string())
    print(f"    {chicas} de 4 celdas con menos de {MIN_DIAS} días: " + ("no es evidencia." if chicas else "muestra suficiente."))
print("    (Hasta el 2026-11-12 estas tablas iban por bloque, con el umbral de toda la muestra y los días contados"
      "\n    por celda sin separar: los números casi no cambian, pero las celdas no tenían los días que decían.)")

print("\n--- E. ¿Es otra forma de leer el PRECIO? (revisor de validación, 2026-11-12) ---")
c = vm.control_precio(t)
print(f"    Entre días, misma franja (medianas por franja; las franjas NO son pruebas independientes: la gamma casi"
      f"\n    no cambia dentro del día, así que repiten la misma ordenación de {c['dias']} días):")
print(f"    gamma bruta con el nivel del SPX            {c['gamma_con_spx']:+.2f}")
print(f"    nivel del SPX con el rango siguiente        {c['spx']:+.2f}   (ingenuo: no usa opciones)")
print(f"    gamma bruta con el rango siguiente          {c['gamma']:+.2f}   (al quitar un día: de "
      f"{c['sin_un_dia'][0]:+.2f} a {c['sin_un_dia'][1]:+.2f})")
print(f"    gamma bruta DESCONTANDO el nivel del SPX    {c['parcial']:+.2f}   (local ±50 pts: {c['parcial_local']:+.2f})")
print("    Si lo que queda al descontar el precio ronda 0, la gamma bruta no agrega nada sobre mirar el índice.")
