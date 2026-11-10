"""
vista.py — Datos para el panel 0DTE (app/panel_odte.py). SOLO CACHÉ: nunca descarga ni cotiza.

Regla de costo: este módulo lee parquets y CSV que ya existen y reutiliza cálculos puros de precio, catalogo,
trades y carga. NO llama a datos.asegurar_descargas, asegurar_*, descargar_* ni a yfinance. Esos módulos
importan src.datos al cargarse (el cliente de Databento es diferido y no pide la clave), pero ninguna función
de aquí llega a una descarga: tests/test_vista.py lo verifica haciendo gritar a datos.asegurar_descargas y a
datos._cliente.

Un día al que le falta algo NO rompe: cada función levanta SinDatos con el motivo, y inventario() dice de
antemano qué se puede dibujar cada día. El 2026-10-20 (sin datos en Databento) y los feriados aparecen en el
inventario como días hábiles sin nada.
"""
import glob
import os
import re

import pandas as pd

from . import catalogo, precio, trades
from .carga import REFERENCIA_FIJA, carga_dia
from .carga import clase as clase_carga
from .clasificacion import clasificar_trades
from .flujo import flujo_por_minuto
from .toques import Definicion, toques

PROCESADO = "data/procesado/cadena_SPX+SPXW_horas_{}.parquet"
RUTA_CARGA = "data/validacion/odte_carga.csv"
RUTA_TOQUES = "data/validacion/odte_toques.csv"
_FECHA = re.compile(r"(\d{4}-\d{2}-\d{2})")


# Contrato de clases de lo que este módulo entrega (el de la carga está en carga.py). Todo sale de precios y
# trades observados: MEDIDO. Con la regla del punto medio el flujo deja de serlo (ver clase_flujo).
MEDIDAS = ["spx", "flujo_C", "flujo_P", "acum_C", "acum_P", "compra", "venta", "indet", "neto", "pct_indet",
           "razon_neto_indet", "indet_medio", "indet_interior", "indet_fuera", "indet_sin_cotizacion", "resultado"]


def clase(col: str) -> str:
    """'medido' / 'modelo' / 'supuesto' de una columna del panel. Grita si nadie la clasifica.
    Las columnas de precio de carga.py (clase 'precio': toques y excesos) son precio observado: 'medido'."""
    if col in MEDIDAS:
        return "medido"
    k = clase_carga(col)                                     # levanta ValueError si no está clasificada
    return "medido" if k == "precio" else k


def clase_flujo(estricto: bool) -> str:
    """Regla estricta: el flujo firmado es MEDIDO. Punto medio: firma el interior del spread por cercanía, que el
    proyecto trata como INFERIDO; no se rotula como medido."""
    return "medido" if estricto else "inferido"


class SinDatos(Exception):
    """Falta algo en caché para dibujar esto. El mensaje dice qué; el panel lo muestra y sigue."""


def _fechas(patron: str) -> list[str]:
    return sorted({m.group(1) for r in glob.glob(patron) if (m := _FECHA.search(os.path.basename(r)))})


def fotos() -> list[str]:
    """Fechas con cadena procesada (data/procesado), ordenadas."""
    return _fechas(PROCESADO.format("*"))


def foto_previa(fecha: str):
    """(fecha de la foto anterior, d1_vieja) o None. d1_vieja = la foto previa no es la del día hábil anterior
    (aproximado: no conoce feriados, igual que el panel de walls)."""
    antes = [f for f in fotos() if f < fecha]
    if not antes:
        return None
    habil = (pd.Timestamp(fecha) - pd.offsets.BDay(1)).strftime("%Y-%m-%d")
    return antes[-1], antes[-1] != habil


def inventario() -> pd.DataFrame:
    """Una fila por DÍA HÁBIL entre el primer y el último dato en caché: qué hay y qué se puede dibujar.
    precio_ok (ES + SPX 5m), carga_ok (foto de d + una foto anterior), flujo_ok (catálogo + algún tcbbo)."""
    con_foto = set(fotos())
    con_es = set(_fechas(os.path.join(precio.CARPETA_CACHE, "es_1min_*.parquet")))
    con_spx = set(_fechas(os.path.join(precio.CARPETA_CACHE, "spx_yf_5m_*.parquet")))
    con_def = set(_fechas(os.path.join(catalogo.CARPETA_CACHE, "definicion_SPXW_*.parquet")))
    con_tcbbo = set(_fechas(os.path.join(trades.CARPETA_CACHE, "tcbbo0dte_*.parquet")))
    todas = con_foto | con_es | con_spx | con_def | con_tcbbo
    if not todas:
        return pd.DataFrame(columns=["foto", "foto_previa", "es", "spx5m", "catalogo", "tcbbo",
                                     "precio_ok", "carga_ok", "flujo_ok", "falta"])
    filas = []
    for d in pd.bdate_range(min(todas), max(todas)):
        f = d.strftime("%Y-%m-%d")
        previa = foto_previa(f)
        r = dict(fecha=f, foto=f in con_foto, foto_previa=previa[0] if previa else "", es=f in con_es,
                 spx5m=f in con_spx, catalogo=f in con_def, tcbbo=f in con_tcbbo)
        r["precio_ok"] = r["es"] and r["spx5m"]
        r["carga_ok"] = r["foto"] and previa is not None
        r["flujo_ok"] = r["catalogo"] and r["tcbbo"]
        if not any(r[k] for k in ("foto", "es", "spx5m", "catalogo", "tcbbo")):
            r["falta"] = "todo (feriado, o día sin datos en Databento)"
        else:
            r["falta"] = ", ".join(n for n, ok in (("foto procesada", r["foto"]), ("ES 1-min", r["es"]),
                                                    ("SPX 5m", r["spx5m"]), ("catálogo 0DTE", r["catalogo"]),
                                                    ("tcbbo", r["tcbbo"])) if not ok)
        filas.append(r)
    return pd.DataFrame(filas).set_index("fecha")


def spx_dia(fecha: str) -> pd.Series:
    """SPX estimado por minuto (ES − base MÓVIL), leyendo solo los parquets en caché."""
    ruta = precio.ruta_es(fecha)
    if not os.path.exists(ruta):
        raise SinDatos(f"{fecha}: falta el ES 1-min en caché")
    if not os.path.exists(precio.ruta_spx_yf(fecha, "5m")):
        raise SinDatos(f"{fecha}: falta el SPX 5m de yfinance en caché (sin él no hay base móvil)")
    es = pd.read_parquet(ruta)
    if es.empty:
        raise SinDatos(f"{fecha}: el ES 1-min en caché está vacío")
    try:
        base = precio.base_movil(es, precio.leer_spx_yf(fecha, "5m"))
    except (ValueError, RuntimeError) as e:
        raise SinDatos(f"{fecha}: no se puede medir la base ES − SPX ({e})") from e
    return (es["close"] - base).rename("spx")


def toques_dia(fecha: str, d: Definicion = Definicion()) -> pd.DataFrame:
    """Toques del día (toques.py) más t_fin = fin de la ventana que decide el resultado."""
    t = toques(spx_dia(fecha), d)
    t["t_fin"] = t["t_toque"] + pd.Timedelta(minutes=d.ventana_min)
    return t


def carga_del_dia(fecha: str) -> dict:
    """Carga por zona conocida antes de la apertura (carga.carga_dia) y de qué fotos salió."""
    if not os.path.exists(PROCESADO.format(fecha)):
        raise SinDatos(f"{fecha}: falta la foto procesada (el OI de la mañana)")
    previa = foto_previa(fecha)
    if previa is None:
        raise SinDatos(f"{fecha}: no hay una foto anterior (la gamma bruta y el wall salen de la foto de d−1)")
    foto_p = pd.read_parquet(PROCESADO.format(previa[0]))
    S_previo = float(foto_p["S"].iloc[0])
    try:
        z = carga_dia(pd.read_parquet(PROCESADO.format(fecha)), foto_p, fecha, S_previo)
    except ValueError as e:
        raise SinDatos(f"{fecha}: la carga no se pudo calcular ({e})") from e
    return dict(zonas=z, S_previo=S_previo, foto_previa=previa[0], d1_vieja=previa[1])


def flujo_dia(fecha: str, estricto: bool = True) -> dict:
    """Flujo neto del PÚBLICO por minuto en las 0DTE que haya en caché (calls y puts aparte) y su cobertura.
    El tcbbo en caché cubre solo los strikes que se bajaron: la cobertura dice cuántas series y qué rango."""
    ruta = catalogo.ruta_definicion(fecha)
    if not os.path.exists(ruta):
        raise SinDatos(f"{fecha}: falta el catálogo 0DTE (definition) en caché")
    sel = catalogo.filtrar_0dte(pd.read_parquet(ruta), fecha).drop_duplicates("raw_symbol")
    if sel.empty:
        raise SinDatos(f"{fecha}: el catálogo no tiene series 0DTE")
    simbolos = sel["raw_symbol"].tolist()
    # Franjas en caché, de la más larga a la más corta: se usa la primera que cubra alguna serie 0DTE.
    # Sesión completa si existe; si no, la franja parcial más larga (p. ej. solo la apertura).
    franjas = sorted({(a["inicio"], a["fin"]) for a in trades.archivos_tcbbo(fecha)},
                     key=lambda x: (x[1] - x[0], x[0]), reverse=True)
    cubiertos, desde, hasta = [], None, None
    for ini, fin in franjas:
        desde, hasta = ini.strftime("%H:%M:%S"), fin.strftime("%H:%M:%S")
        _, faltan = trades.plan_tcbbo(fecha, simbolos, desde, hasta)
        cubiertos = sorted(set(simbolos) - set(faltan))
        if cubiertos:
            break
    if not cubiertos:
        raise SinDatos(f"{fecha}: no hay tcbbo en caché para las series 0DTE")
    tr = trades.leer_tcbbo(fecha, cubiertos, desde, hasta)
    if tr.empty:
        raise SinDatos(f"{fecha}: el tcbbo en caché no tiene trades de las series 0DTE")
    tr = tr.reset_index().merge(sel[["raw_symbol", "instrument_class", "strike_price"]],
                                left_on="symbol", right_on="raw_symbol", how="left").set_index("ts_recv")
    c = clasificar_trades(tr, estricto=estricto)
    por_min = flujo_por_minuto(c)
    for col in ("flujo_C", "flujo_P"):                       # un día sin calls o sin puts no rompe
        if col not in por_min.columns:
            por_min[col] = 0
    por_min["acum_C"], por_min["acum_P"] = por_min["flujo_C"].cumsum(), por_min["flujo_P"].cumsum()
    tam = c["size"].astype("int64")
    vol = dict(compra=int(tam[c["signo"] == 1].sum()), venta=int(tam[c["signo"] == -1].sum()),
               indet=int(tam[c["signo"] == 0].sum()))
    total = sum(vol.values())
    con_trades = sel[sel["raw_symbol"].isin(c["symbol"].astype(str).unique())]
    return dict(flujo=por_min, volumen=vol, pct_indet=100.0 * vol["indet"] / total if total else float("nan"),
                series_cubiertas=len(cubiertos), series_0dte=len(simbolos),
                desde=desde[:5], hasta=hasta[:5],
                sesion_completa=(desde[:5], hasta[:5]) == ("09:30", precio.hora_cierre(fecha)),
                strike_min=float(con_trades["strike_price"].min()), strike_max=float(con_trades["strike_price"].max()))


def leer_carga():
    """Acumulador de M4 (odte_carga.csv) o None si no existe. Las filas sin `referencia` son radio250."""
    if not os.path.exists(RUTA_CARGA):
        return None
    t = pd.read_csv(RUTA_CARGA, dtype={"fecha": str, "clase": str})
    if "referencia" not in t.columns:
        t["referencia"] = REFERENCIA_FIJA
    return t


def leer_toques_m2():
    """Acumulador de M2 (odte_toques.csv) o None si no existe."""
    if not os.path.exists(RUTA_TOQUES):
        return None
    return pd.read_csv(RUTA_TOQUES, dtype={"fecha": str})


def razon_neto_indet(t: pd.DataFrame) -> pd.Series:
    """|neto| / indeterminado por toque (el peor caso del veredicto exige > 1). NaN sin indeterminado."""
    return (t["neto"].abs() / t["indet"].where(t["indet"] > 0)).astype(float)


def partes_indet(t: pd.DataFrame) -> pd.DataFrame:
    """Lo indeterminado de cada toque, en % por ubicación: punto medio, interior, fuera, sin cotización."""
    cols = ["indet_medio", "indet_interior", "indet_fuera", "indet_sin_cotizacion"]
    return t[cols].div(t["indet"].where(t["indet"] > 0), axis=0) * 100


def mapa_toques(t: pd.DataFrame) -> pd.DataFrame:
    """Día × zona con el resultado de cada toque (texto), para el mapa de la muestra. Filas = zonas."""
    if t.duplicated(["fecha", "strike"]).any():
        raise ValueError("hay zonas repetidas en un mismo día: pasar una sola definición y referencia")
    return t.pivot(index="strike", columns="fecha", values="resultado").sort_index()

