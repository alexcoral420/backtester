"""
Descargas de Databento: cadena de opciones y trades (para trade sign).
Esta es la capa que trae datos crudos del mundo exterior.
"""
import pandas as pd
import databento as db
from config import DATABENTO_KEY

# Un solo cliente, reutilizado por todas las funciones
_client = db.Historical(DATABENTO_KEY)


def descargar_cadena(fecha):
    """Descarga precios y open interest de toda la cadena SPX de un día.
    Devuelve el DataFrame de precios y el de open interest."""
    fin = (pd.to_datetime(fecha) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    ohlcv = _client.timeseries.get_range(
        dataset="OPRA.PILLAR", symbols=["SPX.OPT"], stype_in="parent",
        schema="ohlcv-1d", start=fecha, end=fin).to_df().reset_index()

    stats = _client.timeseries.get_range(
        dataset="OPRA.PILLAR", symbols=["SPX.OPT"], stype_in="parent",
        schema="statistics", start=fecha, end=fin).to_df().reset_index()

    oi = stats[stats["stat_type"] == 9][["symbol", "quantity"]].rename(
        columns={"quantity": "open_interest"})
    precios = ohlcv[["symbol", "close"]].rename(columns={"close": "precio_opcion"})
    return precios, oi


def descargar_trades(simbolos, fecha_inicio, fecha_fin):
    """Descarga los trades con bid/ask (tcbbo) de opciones específicas.
    Para el trade sign. simbolos = lista de símbolos exactos."""
    return _client.timeseries.get_range(
        dataset="OPRA.PILLAR", symbols=simbolos, stype_in="raw_symbol",
        schema="tcbbo", start=fecha_inicio, end=fecha_fin).to_df().reset_index()

        # Agregar al final de src/datos.py
import yfinance as yf

def precio_spx(fecha):
    """Baja el cierre del SPX de una fecha (de yfinance)."""
    fin = (pd.to_datetime(fecha) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    spx = yf.download("^GSPC", start=fecha, end=fin, interval="1d", progress=False)
    spx.columns = spx.columns.droplevel(1) if spx.columns.nlevels > 1 else spx.columns
    return float(spx["Close"].iloc[0])