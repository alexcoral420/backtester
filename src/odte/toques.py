"""
toques.py — Cuando el precio llegó a un strike, ¿el nivel aguantó o se cruzó? ¿Y qué flujo había antes?

Es la unidad de la muestra de M2 (ODTE.md, "M2: definiciones"). Todo con el SPX por minuto
(precio.spx_1min: CIERRES de barras de 1 min, índice = inicio de la barra, hora NY).

Definición vigente (la de Definicion() por defecto; las alternativas a probar están en ODTE.md):
  - Niveles: strikes múltiplos de `paso` (25).
  - TOQUE: la primera barra, desde `desde` (10:00), cuyo cierre entra a la banda |SPX - K| <= `tolerancia`
    (2 pts) o salta al otro lado del strike, viniendo de FUERA de la banda (la barra anterior estaba a más
    de `tolerancia`). `lado` = de qué lado venía el precio (el de la barra anterior). Si el precio ya
    estaba dentro de la banda a las 10:00, no cuenta hasta que salga y vuelva a entrar.
  - RESULTADO: en las `ventana_min` (30) barras que empiezan en la del toque (incluida), si algún cierre
    pasa el strike hacia el lado contrario por MÁS de `margen` (5 pts) -> "cruzó"; si no -> "aguantó".
    Si la sesión termina antes de completar la ventana -> "ventana corta" (no se cuenta como ninguno).
  - FLUJO MEDIDO: trades del strike (calls + puts, misma gamma) desde la apertura hasta ANTES del inicio de
    la barra del toque (el minuto del toque queda fuera, como en cruce.py), regla estricta. El signo del
    dealer lo da veredicto.signo_dealer (peor caso contra lo indeterminado) y va con su % indeterminado.

Las columnas son de tres clases y no se mezclan:
  - precio: toque, lado, dist_previa, peor_exceso, resultado;
  - flujo MEDIDO: compra, venta, indet, neto, neto_calls, neto_puts, pct_indet, dealer_medido, y la
    descomposición de lo indeterminado por ubicación (indet_medio, indet_interior, indet_fuera, indet_sin_cotizacion);
  - flujo INFERIDO: neto_inferido_interior = interior más cerca del ask − más cerca del bid (tipo
    Lee-Ready). No es medido: sirve solo para ver si el signo depende de la regla (cierre de M2).
No hay nada supuesto: la hipótesis nula no entra en este módulo.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .clasificacion import ubicar_trades
from .veredicto import pct_indet, signo_dealer, volumenes

AGUANTO, CRUZO, VENTANA_CORTA = "aguantó", "cruzó", "ventana corta"


@dataclass(frozen=True)
class Definicion:
    paso: int = 25            # niveles = múltiplos de este número
    tolerancia: float = 2.0   # pts: a esta distancia o menos, el precio "tocó"
    desde: str = "10:00"      # hora NY desde la que cuentan los toques (evita la apertura)
    ventana_min: int = 30     # minutos para decidir si aguantó
    margen: float = 5.0       # pts más allá del strike que cuentan como cruce

    def __post_init__(self):
        if self.paso <= 0 or self.tolerancia < 0 or self.ventana_min <= 0 or self.margen < 0:
            raise ValueError(f"definición inválida: {self}")

    def etiqueta(self) -> str:
        """Identificador estable para el acumulador, p. ej. 'p25_t2_d1000_v30_m5'."""
        return (f"p{self.paso}_t{self.tolerancia:g}_d{self.desde.replace(':', '')}"
                f"_v{self.ventana_min}_m{self.margen:g}")


def _validar_serie(dia: pd.Series):
    if dia.empty:
        raise ValueError("serie de precios vacía: no hay sesión")
    if not dia.index.is_monotonic_increasing:
        raise ValueError("la serie de precios debe estar ordenada en el tiempo")
    if dia.index.tz is None:
        raise ValueError("la serie de precios necesita hora NY explícita (índice con zona)")


def niveles(dia: pd.Series, d: Definicion) -> list[int]:
    """Strikes múltiplos de d.paso que el precio del día pudo tocar (dentro de [mín - tol, máx + tol])."""
    lo, hi = dia.min() - d.tolerancia, dia.max() + d.tolerancia
    return list(range(int(np.ceil(lo / d.paso)) * d.paso, int(np.floor(hi / d.paso)) * d.paso + 1, d.paso))


def primer_toque(dia: pd.Series, strike: float, d: Definicion):
    """(índice de la barra del toque, lado 'arriba'/'abajo') o None si no hubo toque."""
    x = dia - strike
    fuera = x.abs() > d.tolerancia
    salto = np.sign(x) != np.sign(x.shift())
    previo_fuera = fuera.shift(1, fill_value=False).astype(bool)
    desde = pd.Timestamp(f"{dia.index[0]:%Y-%m-%d} {d.desde}", tz=dia.index.tz)
    cond = previo_fuera & (~fuera | salto) & (dia.index >= desde)
    if not cond.any():
        return None
    i = int(np.flatnonzero(cond.to_numpy())[0])
    return i, ("arriba" if x.iloc[i - 1] > 0 else "abajo")


def toques(dia: pd.Series, d: Definicion = Definicion()) -> pd.DataFrame:
    """Un renglón por strike tocado: strike, t_toque (inicio de la barra), lado, dist_previa (|SPX - K|
    `ventana_min` minutos antes del toque, o en la primera barra si es antes de la apertura),
    peor_exceso (pts máximos más allá del strike, contra el lado de llegada, dentro de la ventana) y
    resultado."""
    _validar_serie(dia)
    filas = []
    ultima = dia.index[-1]
    paso_ventana = pd.Timedelta(minutes=d.ventana_min)
    for k in niveles(dia, d):
        r = primer_toque(dia, k, d)
        if r is None:
            continue
        i, lado = r
        t = dia.index[i]
        previa = dia[dia.index <= t - paso_ventana]
        dist_previa = abs((previa.iloc[-1] if len(previa) else dia.iloc[0]) - k)
        if t + paso_ventana - pd.Timedelta(minutes=1) > ultima:
            exceso, resultado = float("nan"), VENTANA_CORTA
        else:
            v = dia[(dia.index >= t) & (dia.index < t + paso_ventana)]
            contra = (k - v) if lado == "arriba" else (v - k)
            exceso = float(contra.max())
            resultado = CRUZO if exceso > d.margen else AGUANTO
        filas.append(dict(strike=k, t_toque=t, lado=lado, dist_previa=float(dist_previa),
                          peor_exceso=exceso, resultado=resultado))
    cols = ["strike", "t_toque", "lado", "dist_previa", "peor_exceso", "resultado"]
    return pd.DataFrame(filas, columns=cols)


def flujo_previo(tq: pd.DataFrame, clasificados: pd.DataFrame, ts: str = "ts_recv") -> pd.DataFrame:
    """Agrega a cada toque el flujo MEDIDO de su strike ANTES de t_toque (regla estricta ya aplicada:
    columnas `signo`, `size`, `strike_price`, `instrument_class` y `ts`)."""
    faltan = ({"signo", "size", "strike_price", "instrument_class", "price", "bid_px_00", "ask_px_00", ts}
              - set(clasificados.columns))
    if faltan:
        raise ValueError(f"faltan columnas en los trades clasificados: {sorted(faltan)}")
    clasificados = clasificados.assign(_ubic=ubicar_trades(clasificados))
    filas = []
    for _, r in tq.iterrows():
        g = clasificados[(clasificados["strike_price"] == r["strike"]) & (clasificados[ts] < r["t_toque"])]
        v = volumenes(g, "strike_price").reindex([r["strike"]], fill_value=0).iloc[0]
        c, vt, i = int(v["compra"]), int(v["venta"]), int(v["indet"])
        neto = (g["signo"].astype("int64") * g["size"].astype("int64"))
        tipo = g["instrument_class"]
        p = pct_indet(c, vt, i)
        u = g.groupby("_ubic")["size"].sum().astype("int64")
        partes = dict(indet_medio=int(u.get("medio", 0)),
                      indet_interior=int(u.get("interior_ask", 0) + u.get("interior_bid", 0)),
                      indet_fuera=int(u.get("fuera", 0)), indet_sin_cotizacion=int(u.get("sin cotización", 0)))
        if sum(partes.values()) != i:
            raise RuntimeError(f"strike {r['strike']}: la ubicación ({partes}) no suma el indeterminado ({i})")
        filas.append(dict(compra=c, venta=vt, indet=i, neto=c - vt,
                          neto_calls=int(neto[tipo == "C"].sum()), neto_puts=int(neto[tipo == "P"].sum()),
                          pct_indet=None if p != p else round(p, 1), dealer_medido=signo_dealer(c, vt, i),
                          **partes, neto_inferido_interior=int(u.get("interior_ask", 0) - u.get("interior_bid", 0))))
    medido = pd.DataFrame(filas, index=tq.index,
                          columns=["compra", "venta", "indet", "neto", "neto_calls", "neto_puts",
                                   "pct_indet", "dealer_medido", "indet_medio", "indet_interior",
                                   "indet_fuera", "indet_sin_cotizacion", "neto_inferido_interior"])
    return pd.concat([tq, medido], axis=1)
