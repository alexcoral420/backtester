"""
Descargas de Databento: cadena de opciones y trades (para trade sign).
Esta es la capa que trae datos crudos del mundo exterior.

Reglas: costo primero (get_cost + confirmación) y caché "descargar si no existe".
Los mensajes de caché/costo van a stderr: así la salida normal (stdout) de los scripts
queda limpia para compararla antes/después.
"""
import os
import sys

import pandas as pd
import yfinance as yf

CARPETA_CACHE = "data/raw"
STAT_OI = 9                       # stat_type de Databento para open interest

_cliente_db = None


def _cliente():
    """Crea el cliente de Databento solo cuando hace falta (importar este archivo no exige la clave)."""
    global _cliente_db
    if _cliente_db is None:
        import databento as db
        from config import DATABENTO_KEY
        _cliente_db = db.Historical(DATABENTO_KEY)
    return _cliente_db


def _log(mensaje):
    print(mensaje, file=sys.stderr)


def _confirmar(mensaje) -> bool:
    print(mensaje, end="", file=sys.stderr, flush=True)
    return sys.stdin.readline().strip().lower() == "s"


def _parametros_cadena(raiz, schema, fecha):
    fin = (pd.to_datetime(fecha) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return dict(dataset="OPRA.PILLAR", symbols=[f"{raiz}.OPT"], stype_in="parent",
                schema=schema, start=fecha, end=fin)


def ruta_cadena(raiz, schema, fecha):
    """Ruta del parquet en caché de una parte de la cadena (ohlcv-1d o statistics)."""
    return os.path.join(CARPETA_CACHE, f"cadena_{raiz}_{schema}_{fecha}.parquet")


def descargar_cadena(fecha, raices=("SPX",)):
    """Precios (cierre del día) y open interest de toda la cadena de un día.
    raices: ("SPX",) = mensuales AM (lo que usaba la herramienta original);
            ("SPX", "SPXW") = también diarias y semanales.
    Devuelve (precios, oi) con UNA fila por símbolo."""
    pendientes = [(r, s) for r in raices for s in ("ohlcv-1d", "statistics")
                  if not os.path.exists(ruta_cadena(r, s, fecha))]

    if pendientes:
        cliente = _cliente()
        costo = sum(cliente.metadata.get_cost(**_parametros_cadena(r, s, fecha)) for r, s in pendientes)
        if not _confirmar(f"Cadena {fecha} ({'+'.join(raices)}): {len(pendientes)} descargas, "
                          f"costo estimado ${costo:.4f}. ¿Descargar? (s/n): "):
            raise SystemExit("Descarga cancelada.")
        os.makedirs(CARPETA_CACHE, exist_ok=True)
        for r, s in pendientes:
            try:
                df = cliente.timeseries.get_range(**_parametros_cadena(r, s, fecha)).to_df().reset_index()
            except Exception as e:
                raise RuntimeError(f"Falló la descarga de {r} {s} del {fecha}: {e}")
            df.to_parquet(ruta_cadena(r, s, fecha))
            _log(f"[guardado] {ruta_cadena(r, s, fecha)} ({len(df)} filas)")
    else:
        _log(f"[caché] cadena {fecha} ({'+'.join(raices)})")

    ohlcv = pd.concat([pd.read_parquet(ruta_cadena(r, "ohlcv-1d", fecha)) for r in raices],
                      ignore_index=True)
    stats = pd.concat([pd.read_parquet(ruta_cadena(r, "statistics", fecha)) for r in raices],
                      ignore_index=True)

    # Open interest: una fila por símbolo, la ÚLTIMA publicada (evita contar dos veces el mismo OI)
    oi = stats[stats["stat_type"] == STAT_OI]
    repetidos_oi = int(oi.duplicated("symbol").sum())
    if "ts_event" in oi.columns:
        oi = oi.sort_values("ts_event", kind="stable")
    oi = oi.drop_duplicates("symbol", keep="last")[["symbol", "quantity"]].rename(
        columns={"quantity": "open_interest"})

    repetidos_px = int(ohlcv.duplicated("symbol").sum())
    precios = ohlcv.drop_duplicates("symbol", keep="last")[["symbol", "close"]].rename(
        columns={"close": "precio_opcion"})

    _log(f"[cadena] {fecha}: {len(precios)} precios, {len(oi)} OI | "
         f"repetidos descartados: precios {repetidos_px}, OI {repetidos_oi}")
    return precios, oi


def asegurar_cadenas(fechas, raices=("SPX",)):
    """Deja en caché la cadena de VARIAS fechas con UNA sola confirmación de costo (el total).
    Las fechas que ya están en caché no cuestan nada. Después, descargar_cadena las lee sin preguntar."""
    pendientes = [(f, r, s) for f in fechas for r in raices for s in ("ohlcv-1d", "statistics")
                  if not os.path.exists(ruta_cadena(r, s, f))]
    if not pendientes:
        _log(f"[caché] las {len(fechas)} fechas ya están en caché")
        return
    cliente = _cliente()
    costo = sum(cliente.metadata.get_cost(**_parametros_cadena(r, s, f)) for f, r, s in pendientes)
    dias = sorted({f for f, _, _ in pendientes})
    if not _confirmar(f"{len(dias)} días sin caché ({', '.join(dias)}): {len(pendientes)} descargas, "
                      f"costo estimado TOTAL ${costo:.4f}. ¿Descargar todo? (s/n): "):
        raise SystemExit("Descarga cancelada.")
    os.makedirs(CARPETA_CACHE, exist_ok=True)
    for f, r, s in pendientes:
        try:
            df = cliente.timeseries.get_range(**_parametros_cadena(r, s, f)).to_df().reset_index()
        except Exception as e:
            raise RuntimeError(f"Falló la descarga de {r} {s} del {f}: {e}")
        df.to_parquet(ruta_cadena(r, s, f))
        _log(f"[guardado] {ruta_cadena(r, s, f)} ({len(df)} filas)")


def descargar_trades(simbolos, fecha_inicio, fecha_fin):
    """Descarga los trades con bid/ask (tcbbo) de opciones específicas.
    Para el trade sign. simbolos = lista de símbolos exactos.
    (La caché de estos trades la maneja trade_sign.clasificar_flujo.)"""
    return _cliente().timeseries.get_range(
        dataset="OPRA.PILLAR", symbols=simbolos, stype_in="raw_symbol",
        schema="tcbbo", start=fecha_inicio, end=fecha_fin).to_df().reset_index()


def precio_spx(fecha):
    """Cierre oficial del SPX (^GSPC) de una fecha, desde yfinance.
    ÚNICA función del proyecto para esto (odte.precio.cierre_spx es un alias de esta).
    Sin datos (fin de semana, feriado, fecha futura) -> RuntimeError con mensaje claro."""
    fin = (pd.to_datetime(fecha) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    hist = yf.Ticker("^GSPC").history(start=fecha, end=fin)
    if hist.empty:
        raise RuntimeError(f"yfinance no devolvió cierre del SPX para {fecha} (¿fin de semana o feriado?)")
    return float(hist["Close"].iloc[-1])