"""
precio.py — ¿Dónde estaba el SPX cada minuto?
OPRA no tiene el índice: usamos el futuro ES menos la base (ES - SPX al cierre).
"""
import os

import pandas as pd
import yfinance as yf

from src import datos
from src.datos import precio_spx as cierre_spx   # única fuente del cierre del SPX
from .calendario import hora_cierre, ultima_barra
from .constantes import CARPETA_CACHE, ZONA_NY


def ruta_es(fecha: str) -> str:
    return os.path.join(CARPETA_CACHE, f"es_1min_{fecha}.parquet")


def parametros_es(fecha: str) -> dict:
    fin = (pd.Timestamp(fecha) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return dict(dataset="GLBX.MDP3",       # CME Globex (futuros)
                symbols="ES.v.0",          # continuo: el contrato con más volumen ese día
                stype_in="continuous", schema="ohlcv-1m", start=fecha, end=fin)


def horario_regular(df: pd.DataFrame, fecha: str) -> pd.DataFrame:
    """El índice es ts_event (INICIO de cada barra) en UTC -> Nueva York. Horario regular: barras que
    empiezan entre 09:30 y la última de la sesión (15:59 un día normal, 12:59 en un cierre temprano)."""
    df = df.copy()
    df.index = df.index.tz_convert(ZONA_NY)
    return df.between_time("09:30", ultima_barra(fecha))[["open", "high", "low", "close", "volume"]]


def pedidos_es(fechas) -> list:
    """Pedidos para datos.asegurar_descargas."""
    return [(ruta_es(f), parametros_es(f), lambda df, f=f: horario_regular(df, f)) for f in fechas]


def descargar_es_1min(fecha: str) -> pd.DataFrame:
    """
    Barras de 1 minuto del ES (contrato más operado) para `fecha`, solo horario regular NY.
    Caché en data/raw/es_1min_FECHA.parquet; si falta, costo + confirmación.
    """
    datos.asegurar_descargas(pedidos_es([fecha]), f"ES 1-min {fecha}")
    return pd.read_parquet(ruta_es(fecha))


# --- SPX intradía de yfinance (gratis, pero yfinance solo guarda 60 días de 5m y 30 de 1m) ---------------
# Sirve para medir la base ES - SPX durante el día. Con la base de cierre (constante), el SPX estimado
# tenía un sesgo diario de hasta ~5 pts frente a la tolerancia de 2 pts de un toque (duda 3 de M4 en ODTE.md):
# el cierre oficial incluye el salto de la subasta y la base se mueve en el día.
MINUTOS_YF = {"1m": 1, "5m": 5}


def ruta_spx_yf(fecha: str, intervalo: str) -> str:
    if intervalo not in MINUTOS_YF:
        raise ValueError(f"Intervalo {intervalo!r} no soportado: usar uno de {list(MINUTOS_YF)}")
    return os.path.join(CARPETA_CACHE, f"spx_yf_{intervalo}_{fecha}.parquet")


def barras_esperadas(fecha: str, intervalo: str) -> int:
    """Barras de la sesión regular completa (390 de 1m o 78 de 5m un día normal)."""
    cierre = pd.Timestamp(f"{fecha} {hora_cierre(fecha)}")
    return int((cierre - pd.Timestamp(f"{fecha} 09:30")).total_seconds() // 60) // MINUTOS_YF[intervalo]


def _sesion_yf(hist: pd.DataFrame, fecha: str, intervalo: str) -> pd.DataFrame:
    """Índice = INICIO de la barra en hora NY; solo las barras de la sesión regular de `fecha`."""
    df = hist.rename(columns=str.lower)[["open", "high", "low", "close"]].copy()
    df.index = df.index.tz_convert(ZONA_NY)
    inicio = pd.Timestamp(f"{fecha} 09:30", tz=ZONA_NY)
    fin = pd.Timestamp(f"{fecha} {hora_cierre(fecha)}", tz=ZONA_NY)   # la última barra empieza antes
    return df[(df.index >= inicio) & (df.index < fin)]


def cachear_spx_intradia(fechas, intervalos=("5m", "1m")) -> pd.DataFrame:
    """Baja de yfinance (^GSPC) lo que falte en caché. Gratis: no pide confirmación.
    Una fecha sin datos (feriado, o ya fuera de la ventana de yfinance) no se guarda.
    Devuelve una tabla fecha/intervalo/estado/barras para ver qué quedó."""
    filas = []
    for f in fechas:
        for iv in intervalos:
            ruta = ruta_spx_yf(f, iv)
            if os.path.exists(ruta):
                filas.append(dict(fecha=f, intervalo=iv, estado="caché", barras=len(pd.read_parquet(ruta))))
                continue
            fin = (pd.Timestamp(f) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            hist = yf.Ticker("^GSPC").history(start=f, end=fin, interval=iv)
            df = _sesion_yf(hist, f, iv) if not hist.empty else hist
            if df.empty:
                datos._log(f"[sin datos] SPX yfinance {iv} {f}")
                filas.append(dict(fecha=f, intervalo=iv, estado="sin datos", barras=0))
                continue
            os.makedirs(CARPETA_CACHE, exist_ok=True)
            df.to_parquet(ruta)
            datos._log(f"[guardado] {ruta} ({len(df)} barras)")
            filas.append(dict(fecha=f, intervalo=iv, estado="bajado", barras=len(df)))
    t = pd.DataFrame(filas, columns=["fecha", "intervalo", "estado", "barras"])
    t["esperadas"] = [barras_esperadas(f, iv) for f, iv in zip(t["fecha"], t["intervalo"])]
    return t


def leer_spx_yf(fecha: str, intervalo: str) -> pd.DataFrame:
    """Solo caché. Grita si falta el archivo o si la sesión no está completa."""
    ruta = ruta_spx_yf(fecha, intervalo)
    if not os.path.exists(ruta):
        raise RuntimeError(f"Falta el SPX intradía de yfinance ({intervalo}, {fecha}) en caché: correr "
                           f"precio.cachear_spx_intradia (yfinance guarda solo 60 días de 5m y 30 de 1m)")
    df = pd.read_parquet(ruta)
    esperadas = barras_esperadas(fecha, intervalo)
    if len(df) != esperadas:
        raise ValueError(f"SPX yfinance {intervalo} {fecha}: {len(df)} barras, se esperaban {esperadas}")
    return df


def base_movil(es: pd.DataFrame, spx5: pd.DataFrame) -> pd.Series:
    """Base ES - SPX minuto a minuto, medida cada 5 min e interpolada en el tiempo.
    Cada barra de 5 min del SPX (inicio t) cierra en el mismo instante que la barra de 1 min del ES que
    empieza en t + 4 min: ahí se mide la base. Entre mediciones se interpola linealmente; antes de la
    primera y después de la última se repite la más cercana.
    Grita si el ES no tiene la barra correspondiente en más del 10% de las mediciones."""
    t = spx5.index + pd.Timedelta(minutes=4)
    medida = pd.Series(es["close"].reindex(t).values - spx5["close"].values, index=t).dropna()
    if len(medida) < 0.9 * len(spx5):
        raise ValueError(f"Base móvil: solo {len(medida)} de {len(spx5)} mediciones tienen barra del ES")
    union = medida.index.union(es.index)
    return (medida.reindex(union).interpolate(method="time").ffill().bfill()
            .reindex(es.index).rename("base"))


METODOS_BASE = ("cierre", "movil")


def spx_1min(fecha: str, metodo_base: str = "cierre") -> tuple[pd.DataFrame, object]:
    """
    SPX estimado minuto a minuto = ES - base. Devuelve (df con columnas 'spx' y 'base', base).
    metodo_base:
      "cierre" (por defecto, el original): base = cierre ES (barra 15:59) - cierre oficial SPX, constante en
               el día. Devuelve la base como float. Lleva el salto de la subasta de cierre y no sigue la
               deriva del día: sesgo de hasta ~5 pts (duda 3 de M4).
      "movil":  base medida cada 5 min contra el SPX de yfinance (caché, ver cachear_spx_intradia) e
               interpolada. Devuelve la base como Series. Necesita el SPX 5m de esa fecha en caché.
    """
    if metodo_base not in METODOS_BASE:
        raise ValueError(f"metodo_base {metodo_base!r}: usar uno de {METODOS_BASE}")
    es = descargar_es_1min(fecha)
    if metodo_base == "cierre":
        base = float(es["close"].iloc[-1]) - cierre_spx(fecha)
    else:
        base = base_movil(es, leer_spx_yf(fecha, "5m"))
    df = es.copy()
    df["base"] = base
    df["spx"] = df["close"] - df["base"]
    return df, base