"""
simbolos.py — UNA sola forma de desarmar un símbolo de opción (formato OSI).

    'SPXW  261016C07800000'
     ^^^^  ^^^^^^^^^^^^^^^
     raíz  AAMMDD + C/P + strike x 1000 (8 dígitos)

Antes había 6 copias de esta lógica (gex, trade_sign x2, catalogo, 2 scripts).
Si el formato no es el esperado, lanza ValueError: mejor un error que grita
que un strike o una fecha equivocados que susurran.
"""
import pandas as pd

_PATRON = r"\d{6}[CP]\d{8}"


def parsear_simbolos(simbolos: pd.Series) -> pd.DataFrame:
    """
    Desarma una serie de símbolos. Devuelve un DataFrame con el MISMO índice y columnas:
      raiz         'SPX' (mensual AM) o 'SPXW' (diarias/semanales PM)
      venc_codigo  '261016' (texto, como viene en el símbolo)
      venc         2026-10-16 (fecha, sin hora: la hora real depende de la raíz)
      tipo         'C' o 'P'
      strike       7800.0
    """
    s = simbolos.astype(str)
    partes = s.str.split()
    raiz = partes.str[0]
    codigo = partes.str[-1]

    validos = (partes.str.len() == 2) & codigo.str.fullmatch(_PATRON).fillna(False)
    if not validos.all():
        ejemplos = s[~validos].head(3).tolist()
        raise ValueError(f"{int((~validos).sum())} símbolos con formato inesperado, por ejemplo: {ejemplos}")

    return pd.DataFrame({
        "raiz": raiz,
        "venc_codigo": codigo.str[:6],
        "venc": pd.to_datetime(codigo.str[:6], format="%y%m%d"),
        "tipo": codigo.str[6],
        "strike": codigo.str[7:].astype("int64") / 1000,
    }, index=simbolos.index)


def parsear_simbolo(simbolo: str) -> dict:
    """Versión para un solo símbolo (cómoda para pruebas y scripts)."""
    return parsear_simbolos(pd.Series([simbolo])).iloc[0].to_dict()

# Hora de vencimiento (NY) por raíz: SPX liquida con la APERTURA del día (AM), SPXW con el CIERRE (PM).
HORA_VENCIMIENTO = {"SPX": (9, 30), "SPXW": (16, 0)}
HORA_FOTO = (16, 0)                      # la cadena es la foto del cierre de 'fecha'
PLAZOS = ("dias", "horas")


def plazo_anios(fecha, venc, raiz, modo="dias"):
    """T en años de cada opción, desde el cierre de 'fecha' hasta su vencimiento.

    modo:
      "dias"  (default, el de siempre): días calendario / 365. Ignora la hora: AM y PM valen igual.
      "horas": de las 16:00 NY de 'fecha' a las 9:30 (SPX) o 16:00 (SPXW) NY de 'venc', en horas
               reales (con el cambio de horario incluido) / (365 · 24). En vencimientos de 1-3 días
               "dias" se equivoca hasta 6,5 h sobre 24 (la gamma ATM escala con 1/√T).
    venc, raiz: Series alineadas, como salen de parsear_simbolos. Raíz sin hora conocida -> ValueError.
    """
    if modo not in PLAZOS:
        raise ValueError(f"modo debe ser uno de {PLAZOS}, no {modo!r}")
    venc, f = pd.to_datetime(venc), pd.Timestamp(fecha)
    if modo == "dias":
        return (venc - f).dt.days / 365

    desconocidas = set(raiz.unique()) - set(HORA_VENCIMIENTO)
    if desconocidas:
        raise ValueError(f"Raíz sin hora de vencimiento conocida: {sorted(desconocidas)}")
    minutos = raiz.map({r: h * 60 + m for r, (h, m) in HORA_VENCIMIENTO.items()})
    fin = (venc + pd.to_timedelta(minutos, unit="min")).dt.tz_localize("America/New_York")
    inicio = (f + pd.Timedelta(hours=HORA_FOTO[0], minutes=HORA_FOTO[1])).tz_localize("America/New_York")
    return (fin - inicio).dt.total_seconds() / (365 * 24 * 3600)
