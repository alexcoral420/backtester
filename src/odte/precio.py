"""
precio.py — ¿Dónde estaba el SPX cada minuto?
OPRA no tiene el índice: usamos el futuro ES menos la base (ES - SPX al cierre).
"""
import os
from datetime import datetime, timedelta

import databento as db
import pandas as pd
import yfinance as yf

from config import DATABENTO_KEY
from .constantes import CARPETA_CACHE, ZONA_NY


def descargar_es_1min(fecha: str) -> pd.DataFrame:
    """
    Barras de 1 minuto del ES (contrato más operado) para `fecha`, solo horario regular NY.
    Caché en data/raw/es_1min_FECHA.parquet.
    """
    ruta = os.path.join(CARPETA_CACHE, f"es_1min_{fecha}.parquet")
    if os.path.exists(ruta):
        print(f"[caché] leyendo {ruta}")
        return pd.read_parquet(ruta)

    fin = (datetime.strptime(fecha, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    cliente = db.Historical(DATABENTO_KEY)
    parametros = dict(
        dataset="GLBX.MDP3",       # CME Globex (futuros)
        symbols="ES.v.0",          # continuo: el contrato con más volumen ese día
        stype_in="continuous",
        schema="ohlcv-1m",
        start=fecha,
        end=fin,
    )

    costo = cliente.metadata.get_cost(**parametros)
    print(f"Costo estimado ES: ${costo:.4f}")
    if input("¿Descargar? (s/n): ").strip().lower() != "s":
        raise SystemExit("Descarga cancelada.")

    try:
        df = cliente.timeseries.get_range(**parametros).to_df()
    except Exception as e:
        raise RuntimeError(f"Falló la descarga del ES: {e}")

    # El índice es ts_event (INICIO de cada barra) en UTC -> lo pasamos a Nueva York
    df.index = df.index.tz_convert(ZONA_NY)
    # Horario regular: barras que empiezan entre 09:30 y 15:59 (la de 15:59 cierra a las 16:00)
    df = df.between_time("09:30", "15:59")[["open", "high", "low", "close", "volume"]]

    os.makedirs(CARPETA_CACHE, exist_ok=True)
    df.to_parquet(ruta)
    print(f"[guardado] {ruta} ({len(df)} barras)")
    return df


def cierre_spx(fecha: str) -> float:
    """Cierre oficial diario del SPX (^GSPC) desde yfinance."""
    fin = (datetime.strptime(fecha, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    hist = yf.Ticker("^GSPC").history(start=fecha, end=fin)
    if hist.empty:
        raise RuntimeError(f"yfinance no devolvió cierre del SPX para {fecha}")
    return float(hist["Close"].iloc[-1])


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