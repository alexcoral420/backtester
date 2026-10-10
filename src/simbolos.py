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