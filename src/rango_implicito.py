"""
rango_implicito.py — ¿Cuánto movimiento espera el MERCADO para el día siguiente?

La medida: el STRADDLE ATM (call + put del mismo strike, el más cercano al forward) del primer
vencimiento SPXW posterior a `fecha`, con el punto medio del bid/ask de CIERRE (precio_justo).
Es un precio MEDIDO: no usa la hipótesis nula del dealer, ni Black-Scholes, ni volatilidad implícita.
Lo único de modelo es el forward (paridad call-put), que solo elige QUÉ strike es el ATM.

Qué significa: con el strike en el forward, straddle ≈ E|S_venc − K| descontado, es decir el movimiento
absoluto cierre → cierre que el mercado paga por cubrir. El RANGO (máximo − mínimo) es otra cantidad,
más grande: por eso para compararlos el predictor se escala, y la escala de cada día se mide con los
DEMÁS días (escala_sin_mirar), nunca con el propio.

Reglas de validación (las de validar_gex, no negociables):
  - siempre la foto del cierre de d contra lo que pasó DESPUÉS (el día del vencimiento del straddle);
  - todo contra el predictor ingenuo (el rango de hoy);
  - los días no son independientes (la volatilidad se agrupa): se reportan EPISODIOS de volatilidad
    (rachas del objetivo sobre / bajo su mediana) y ese es el tamaño honesto de la muestra.

Hora de la cotización (medido el 2026-11-12 en los statistics en caché): el bid/ask "de cierre" de OPRA es
el del cierre de las opciones (16:15 NY), publicado a las 16:23 y repetido igual a las 17:30-17:45. El SPX
cierra a las 16:00: hay 15 minutos de desfase, y cuando el mercado se mueve en ese rato el forward queda lejos
del cierre (−36,6 pts el 10-29). Por eso (a) el strike sale del forward de las propias opciones, (b) la
calibración mide lo que el straddle PAGA, |cierre siguiente − K|, y no el movimiento desde el cierre de las
16:00, y (c) contra el rango de hoy el straddle corre con 15 minutos de ventaja: está dicho, no corregido.

Incertidumbre de la medición, siempre al lado del número: `ancho` (suma de los dos bid/ask: el straddle
está entre straddle − ancho/2 y straddle + ancho/2), `dispersion` del forward y `dist_FK` (|F − K|).
"""
import numpy as np
import pandas as pd

from src.forward import forward_por_vencimiento

RAIZ = "SPXW"            # vencimientos PM diarios: el primero después de `fecha` es el del día siguiente
HUECO_DIAS = 7           # más días corridos que esto entre dos fechas corta el episodio (otra ventana)


def straddle_atm(tabla: pd.DataFrame, S: float, r: float) -> dict:
    """tabla: precio_justo.tabla_cierre(fecha, raices que incluyan SPXW, plazo="horas").
    Devuelve venc, T, forward, dispersion, K, dist_FK, call, put, straddle, ancho.
    Grita si no hay SPXW vivo o si el primer vencimiento no tiene strikes para medir el forward."""
    w = tabla[(tabla["raiz"] == RAIZ) & (tabla["T"] > 0)]
    if w.empty:
        raise ValueError(f"la tabla no trae opciones {RAIZ} con T > 0: sin ellas no hay straddle del día siguiente")
    venc = w["venc"].min()
    g = w[w["venc"] == venc]
    fw = forward_por_vencimiento(g, S, r)          # grita si no hay strikes suficientes
    F = float(fw.at[venc, "forward"])

    lados = {}
    for tipo in ("C", "P"):
        x = g[g["tipo"] == tipo].set_index("strike")[["bid", "ask", "mid"]]
        if x.index.has_duplicates:
            raise ValueError(f"strikes repetidos en {RAIZ} {venc:%Y-%m-%d} {tipo}")
        lados[tipo] = x
    pares = lados["C"].join(lados["P"], lsuffix="_c", rsuffix="_p", how="inner").dropna(subset=["mid_c", "mid_p"])
    if pares.empty:
        raise ValueError(f"{RAIZ} {venc:%Y-%m-%d}: ningún strike con call y put cotizados")
    K = float((pares.index.to_series() - F).abs().idxmin())
    p = pares.loc[K]
    return dict(venc=pd.Timestamp(venc), T=float(g["T"].iloc[0]), forward=F,
                dispersion=float(fw.at[venc, "dispersion"]), K=K, dist_FK=abs(F - K),
                call=float(p["mid_c"]), put=float(p["mid_p"]), straddle=float(p["mid_c"] + p["mid_p"]),
                ancho=float((p["ask_c"] - p["bid_c"]) + (p["ask_p"] - p["bid_p"])))


def escala_sin_mirar(pred: pd.Series, obj: pd.Series) -> pd.Series:
    """pred · k, con k de cada día = mediana de obj/pred en los OTROS días (dejar uno fuera).
    Así un predictor en otra unidad (el straddle contra el rango) se compara sin mirar el día que predice."""
    if (pred <= 0).any():
        raise ValueError("escala_sin_mirar necesita un predictor positivo")
    razon = (obj / pred).to_numpy(dtype=float)
    if len(razon) < 3:
        raise ValueError("hacen falta al menos 3 días para escalar dejando uno fuera")
    k = [np.nanmedian(np.delete(razon, i)) for i in range(len(razon))]
    return pred * np.array(k)


def comparar(t: pd.DataFrame, objetivo: str, predictores: list) -> pd.DataFrame:
    """Por predictor: n, Spearman con el objetivo y error absoluto medio y MEDIANO (escalado sin mirar; nan
    si el predictor tiene valores <= 0, como el GEX con signo). El mediano va siempre al lado: un par de días
    enormes mueven el medio y no dicen nada del día típico."""
    filas = []
    for col in predictores:
        s = t[[col, objetivo]].dropna()
        error = mediano = np.nan
        if len(s) >= 3 and (s[col] > 0).all():
            e = (escala_sin_mirar(s[col], s[objetivo]) - s[objetivo]).abs()
            error, mediano = float(e.mean()), float(e.median())
        filas.append(dict(predictor=col, n=len(s), spearman=s[col].corr(s[objetivo], method="spearman"),
                          error_medio=error, error_mediano=mediano))
    return pd.DataFrame(filas).set_index("predictor")


def episodios(t: pd.DataFrame, objetivo: str) -> pd.Series:
    """Número de episodio de cada fila: rachas del objetivo sobre / bajo su mediana (regímenes de
    volatilidad). Un hueco de más de HUECO_DIAS días corridos corta la racha. t ordenada por 'fecha'."""
    if not t["fecha"].is_monotonic_increasing:
        raise ValueError("episodios necesita las filas ordenadas por fecha")
    alto = t[objetivo] > t[objetivo].median()
    corte = (alto != alto.shift()) | (pd.to_datetime(t["fecha"]).diff().dt.days > HUECO_DIAS)
    return corte.cumsum()


def duelo_por_episodio(t: pd.DataFrame, objetivo: str, pred: str, ingenuo: str) -> pd.DataFrame:
    """Por episodio: días, error medio de `pred` y de `ingenuo` (los dos escalados sin mirar) y quién gana."""
    s = t[["fecha", objetivo, pred, ingenuo]].dropna().sort_values("fecha").reset_index(drop=True)
    s["e_pred"] = (escala_sin_mirar(s[pred], s[objetivo]) - s[objetivo]).abs()
    s["e_ing"] = (escala_sin_mirar(s[ingenuo], s[objetivo]) - s[objetivo]).abs()
    s["ep"] = episodios(s, objetivo)
    e = s.groupby("ep").agg(desde=("fecha", "min"), hasta=("fecha", "max"), dias=("fecha", "size"),
                            objetivo_med=(objetivo, "median"), e_pred=("e_pred", "mean"), e_ing=("e_ing", "mean"))
    e["gana"] = np.where(e["e_pred"] < e["e_ing"], pred, ingenuo)
    return e


def calibracion(t: pd.DataFrame, mov: str = "pago_sig_pct", impl: str = "impl_pct") -> dict:
    """¿El straddle cobra lo que después paga? razón = |cierre siguiente − K| / straddle (pago_sig_pct: lo que
    el straddle paga de verdad; medirlo desde el cierre de las 16:00 contaría como "día siguiente" lo que el
    mercado ya se había movido cuando se cotizó).
    Sin escalar ni ajustar nada: con precio justo la media ronda 1 y ~57% de los días quedan por debajo
    (P(|Z| < E|Z|) de una normal)."""
    s = t[[mov, impl]].dropna()
    razon = s[mov] / s[impl]
    return dict(n=len(s), razon_media=float(razon.mean()), razon_mediana=float(razon.median()),
                pct_dentro=float(100 * (razon < 1).mean()))


def robustez(t: pd.DataFrame, objetivo: str, pred: str, ingenuo: str, fuera: int = 2) -> pd.DataFrame:
    """¿De qué depende la ventaja? La misma comparación en cuatro cortes: todo, sin los `fuera` días de mayor
    objetivo, y cada mitad de la ventana. Por corte: días, error medio y mediano de cada uno (escalado sin
    mirar DENTRO del corte) y en cuántos días el error de `pred` fue menor."""
    s = t[["fecha", objetivo, pred, ingenuo]].dropna().sort_values("fecha").reset_index(drop=True)
    mitad = len(s) // 2
    cortes = [("todo", s), (f"sin los {fuera} días de mayor objetivo", s.drop(s[objetivo].nlargest(fuera).index)),
              ("primera mitad", s.iloc[:mitad]), ("segunda mitad", s.iloc[mitad:])]
    filas = []
    for nombre, x in cortes:
        e_p = (escala_sin_mirar(x[pred], x[objetivo]) - x[objetivo]).abs()
        e_i = (escala_sin_mirar(x[ingenuo], x[objetivo]) - x[objetivo]).abs()
        filas.append(dict(corte=nombre, dias=len(x), medio_pred=float(e_p.mean()), medio_ing=float(e_i.mean()),
                          mediano_pred=float(e_p.median()), mediano_ing=float(e_i.median()),
                          dias_gana=int((e_p < e_i).sum())))
    return pd.DataFrame(filas).set_index("corte")
