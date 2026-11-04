"""
veredicto.py — ¿Qué signo del dealer sostiene el flujo MEDIDO, y con cuánto respaldo?

Entrada: los tres estados de la regla estricta (clasificacion.clasificar_trades(estricto=True)),
en contratos: compra (en el ask), venta (en el bid) e indeterminado (todo lo demás). Lo
indeterminado NUNCA se redistribuye: se usa solo para saber si podría invertir el signo.

El neto medido (compra - venta) da un signo solo si pasa DOS pruebas, en este orden:
  1) |neto| >= MIN_ABS contratos                       si no -> "sin evidencia"
  2) |neto| >  indeterminado (PEOR CASO: aunque todo   si no -> "indet. domina"
     lo indeterminado hubiera ido en contra, el signo
     no cambia)
Sin trades -> "sin flujo". El % indeterminado se devuelve SIEMPRE, al lado del signo.

No hay mínimo relativo (MIN_REL de signo_medido): en el intradía 0DTE no hay un ΔOI contra el
cual medir. La prueba 2 cumple ese papel contra el volumen que no se pudo firmar.

El peor caso es DELIBERADO (cierre de M1, ODTE.md): |neto| / indeterminado tiene mediana 0,04-0,08 por
strike. Relajarlo a una fracción del indeterminado solo daría signos con umbrales del 5-10%, que ya no
son un criterio. No relajar sin volver a medir esa razón.

Signo del dealer: lo da la tabla de dealer.py (el dealer hace lo contrario del público). Calls y
puts del MISMO strike y vencimiento tienen la misma gamma, por eso sus contratos se pueden sumar.
"""
import pandas as pd

from src.signo_medido import MIN_ABS
from .dealer import posicion_dealer

ESTADOS = {1: "compra", -1: "venta", 0: "indet"}
SIN_FLUJO, SIN_EVIDENCIA, INDET_DOMINA = "sin flujo", "sin evidencia", "indet. domina"


def _validar(compra, venta, indet):
    if min(compra, venta, indet) < 0:
        raise ValueError(f"volúmenes negativos: compra={compra}, venta={venta}, indet={indet}")


def _pruebas(compra, venta, indet):
    """None si el neto pasa las dos pruebas; si no, el estado que corresponde."""
    neto = compra - venta
    if compra + venta + indet == 0:
        return SIN_FLUJO
    if abs(neto) < MIN_ABS:
        return SIN_EVIDENCIA
    if indet >= abs(neto):
        return INDET_DOMINA
    return None


def pct_indet(compra, venta, indet):
    """% del volumen sin signo medido (0 a 100). Sin volumen -> nan."""
    _validar(compra, venta, indet)
    total = compra + venta + indet
    return float("nan") if total == 0 else 100.0 * indet / total


def signo_dealer(compra, venta, indet):
    """'+' (dealer largo de gamma: el público vendió), '-' (corto: el público compró),
    o el estado que impide opinar: 'sin flujo', 'sin evidencia', 'indet. domina'."""
    _validar(compra, venta, indet)
    estado = _pruebas(compra, venta, indet)
    if estado:
        return estado
    publico = "compra" if compra > venta else "vende"
    gamma = posicion_dealer(publico, "C")["gamma"]   # la gamma del dealer no depende del tipo
    return "+" if gamma > 0 else "-"


def vs_nula(compra, venta, indet, accion_supuesta):
    """Lo medido en UN tipo (calls o puts) contra lo que supone la hipótesis nula para ese tipo
    ('compra' o 'vende'): 'confirma', 'CONTRADICE', o el estado que impide opinar."""
    if accion_supuesta not in ("compra", "vende"):
        raise ValueError(f"accion_supuesta debe ser 'compra' o 'vende', no {accion_supuesta!r}")
    _validar(compra, venta, indet)
    estado = _pruebas(compra, venta, indet)
    if estado:
        return estado
    medido = "compra" if compra > venta else "vende"
    return "confirma" if medido == accion_supuesta else "CONTRADICE"


def volumenes(clasificados: pd.DataFrame, por) -> pd.DataFrame:
    """Contratos compra / venta / indet agrupados por `por` (columna o lista de columnas),
    a partir de trades ya clasificados (columnas 'signo' y 'size'). Grupos sin un estado -> 0."""
    if "signo" not in clasificados.columns:
        raise ValueError("faltan trades clasificados: no hay columna 'signo'")
    if clasificados.empty:
        return pd.DataFrame(columns=list(ESTADOS.values()), dtype="int64")
    df = clasificados.assign(estado=clasificados["signo"].map(ESTADOS),
                             contratos=clasificados["size"].astype("int64"))
    t = df.pivot_table(index=por, columns="estado", values="contratos", aggfunc="sum", fill_value=0)
    return t.reindex(columns=list(ESTADOS.values()), fill_value=0).rename_axis(columns=None)
