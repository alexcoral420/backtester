"""
precio.py — ¿Dónde estaba el SPX cada minuto?
OPRA no tiene el índice: usamos el futuro ES menos la base (ES - SPX al cierre).
"""
import os

import pandas as pd

from src import datos
from src.datos import precio_spx as cierre_spx   # única fuente del cierre del SPX
from .calendario import ultima_barra
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


def spx_1min(fecha: str) -> tuple[pd.DataFrame, float]:
    """
    SPX estimado minuto a minuto = ES - base.
    base = cierre ES (barra 15:59) - cierre oficial SPX. Se asume constante en el día.
    Devuelve (df con columna 'spx', base).
    """
    es = descargar_es_1min(fecha)
    base = float(es["close"].iloc[-1]) - cierre_spx(fecha)
    df = es.copy()
    df["spx"] = df["close"] - base
    return df, base