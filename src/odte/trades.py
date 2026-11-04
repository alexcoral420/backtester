"""
trades.py — ¿Qué se negoció? Trades con bid/ask (schema tcbbo).
Lo caro del proyecto: siempre costo primero, caché siempre, UNA confirmación por rango.

Es la capa de tcbbo de TODO el proyecto (0DTE y fase B: b2_flujo, signo_walls, medir_niveles).
"""
import hashlib
import os

import pandas as pd

from src import datos
from .constantes import CARPETA_CACHE, DATASET, ZONA_NY

COLUMNAS = ["symbol", "price", "size", "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"]


def parametros_tcbbo(fecha: str, simbolos: list[str], desde: str = "09:30", hasta: str = "16:00") -> dict:
    """Parámetros de la consulta tcbbo. Horas en NY, convertidas a UTC para la API."""
    return dict(
        dataset=DATASET,
        symbols=simbolos,
        stype_in="raw_symbol",
        schema="tcbbo",
        start=pd.Timestamp(f"{fecha} {desde}", tz=ZONA_NY).tz_convert("UTC"),
        end=pd.Timestamp(f"{fecha} {hasta}", tz=ZONA_NY).tz_convert("UTC"),
    )


def ruta_cache_tcbbo(fecha: str, simbolos: list[str],
                     desde: str = "09:30", hasta: str = "16:00") -> str:
    """Ruta del parquet en caché para esta combinación de día, símbolos y franja."""
    huella = hashlib.md5("|".join(sorted(simbolos)).encode()).hexdigest()[:8]
    sufijo = "" if (desde, hasta) == ("09:30", "16:00") else \
        f"_{desde.replace(':', '')}-{hasta.replace(':', '')}"
    return os.path.join(CARPETA_CACHE, f"tcbbo0dte_{fecha}_{huella}{sufijo}.parquet")


def a_nueva_york(df: pd.DataFrame) -> pd.DataFrame:
    """Lo que se guarda: índice ts_recv (UTC) -> Nueva York, y solo las columnas que se usan."""
    df = df.copy()
    df.index = df.index.tz_convert(ZONA_NY)
    return df[COLUMNAS]


def asegurar_tcbbo(pedidos: dict, desde: str = "09:30", hasta: str = "16:00",
                   solo_costo: bool = False) -> float:
    """
    Deja en caché el tcbbo de VARIOS días con UNA confirmación del costo total.
    pedidos: {fecha: [símbolos]}. Devuelve el costo estimado de lo pendiente ($0 si todo en caché).
    solo_costo=True: consulta el costo sin preguntar ni descargar.
    """
    lista = [(ruta_cache_tcbbo(f, s, desde, hasta), parametros_tcbbo(f, s, desde, hasta), a_nueva_york)
             for f, s in pedidos.items()]
    series = len({x for s in pedidos.values() for x in s})
    return datos.asegurar_descargas(lista, f"tcbbo {len(pedidos)} días, {series} series, {desde}-{hasta}",
                                    solo_costo=solo_costo)


def costo_tcbbo_0dte(fecha: str, simbolos: list[str],
                     desde: str = "09:30", hasta: str = "16:00") -> float:
    """Solo CONSULTA el costo (no descarga nada, no gasta crédito). No mira la caché."""
    return datos._cliente().metadata.get_cost(**parametros_tcbbo(fecha, simbolos, desde, hasta))


def descargar_tcbbo_0dte(fecha: str, simbolos: list[str],
                         desde: str = "09:30", hasta: str = "16:00") -> pd.DataFrame:
    """
    Trades con bid/ask (tcbbo) de los `simbolos` en `fecha`, entre `desde` y `hasta` (hora NY).
    Caché: data/raw/tcbbo0dte_FECHA_HASH[_HHMM-HHMM].parquet
    (sin sufijo = día completo, compatible con lo ya descargado).
    """
    asegurar_tcbbo({fecha: simbolos}, desde, hasta)
    return pd.read_parquet(ruta_cache_tcbbo(fecha, simbolos, desde, hasta))
