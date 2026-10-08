"""
trades.py — ¿Qué se negoció? Trades con bid/ask (schema tcbbo) de las 0DTE.
Lo caro del proyecto: siempre costo primero, caché siempre.
"""
import hashlib
import os

import databento as db
import pandas as pd

from config import DATABENTO_KEY
from .constantes import CARPETA_CACHE, DATASET, ZONA_NY


def _parametros_tcbbo(fecha: str, simbolos: list[str], desde: str, hasta: str) -> dict:
    """Parámetros de la consulta tcbbo. Horas en NY, convertidas a UTC para la API."""
    return dict(
        dataset=DATASET,
        symbols=simbolos,
        stype_in="raw_symbol",
        schema="tcbbo",
        start=pd.Timestamp(f"{fecha} {desde}", tz=ZONA_NY).tz_convert("UTC"),
        end=pd.Timestamp(f"{fecha} {hasta}", tz=ZONA_NY).tz_convert("UTC"),
    )


def costo_tcbbo_0dte(fecha: str, simbolos: list[str],
                     desde: str = "09:30", hasta: str = "16:00") -> float:
    """Solo CONSULTA el costo (no descarga nada, no gasta crédito)."""
    cliente = db.Historical(DATABENTO_KEY)
    return cliente.metadata.get_cost(**_parametros_tcbbo(fecha, simbolos, desde, hasta))


def ruta_cache_tcbbo(fecha: str, simbolos: list[str],
                     desde: str = "09:30", hasta: str = "16:00") -> str:
    """Ruta del parquet en caché para esta combinación de día, símbolos y franja."""
    huella = hashlib.md5("|".join(sorted(simbolos)).encode()).hexdigest()[:8]
    sufijo = "" if (desde, hasta) == ("09:30", "16:00") else \
        f"_{desde.replace(':', '')}-{hasta.replace(':', '')}"
    return os.path.join(CARPETA_CACHE, f"tcbbo0dte_{fecha}_{huella}{sufijo}.parquet")


def descargar_tcbbo_0dte(fecha: str, simbolos: list[str],
                         desde: str = "09:30", hasta: str = "16:00") -> pd.DataFrame:
    """
    Trades con bid/ask (tcbbo) de los `simbolos` en `fecha`, entre `desde` y `hasta` (hora NY).
    Caché: data/raw/tcbbo0dte_FECHA_HASH[_HHMM-HHMM].parquet
    (sin sufijo = día completo, compatible con lo ya descargado).
    """
    ruta = ruta_cache_tcbbo(fecha, simbolos, desde, hasta)
    if os.path.exists(ruta):
        print(f"[caché] leyendo {ruta}")
        return pd.read_parquet(ruta)

    cliente = db.Historical(DATABENTO_KEY)
    parametros = _parametros_tcbbo(fecha, simbolos, desde, hasta)

    costo = cliente.metadata.get_cost(**parametros)
    print(f"Costo estimado tcbbo ({len(simbolos)} opciones): ${costo:.4f}")
    if input("¿Descargar? (s/n): ").strip().lower() != "s":
        raise SystemExit("Descarga cancelada.")

    try:
        df = cliente.timeseries.get_range(**parametros).to_df()
    except Exception as e:
        raise RuntimeError(f"Falló la descarga del tcbbo: {e}")

    # Índice = ts_recv (UTC) -> Nueva York
    df.index = df.index.tz_convert(ZONA_NY)
    df = df[["symbol", "price", "size", "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"]]

    os.makedirs(CARPETA_CACHE, exist_ok=True)
    df.to_parquet(ruta)
    print(f"[guardado] {ruta} ({len(df)} trades)")
    return df