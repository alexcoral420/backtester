"""
descargas.py — ¿Qué falta en caché para estudiar estos días 0DTE, y cuánto cuesta?

asegurar_odte deja en caché catálogo + ES + tcbbo de un RANGO de días con, como mucho, DOS
confirmaciones en total (no una por día ni una por archivo):
  1) catálogo (definition) + ES 1-min de todos los días que falten   (centavos por día)
  2) tcbbo de las 0DTE de cada día en su ventana de strikes            (lo caro)
Son dos porque el costo del tcbbo depende de QUÉ símbolos existían ese día, y eso solo lo dice el
catálogo: no se puede sumar el costo del paso 2 sin tener antes el paso 1.
Después, las funciones de un día (seleccionar_0dte, spx_1min, descargar_tcbbo_0dte) leen de la
caché sin preguntar.
"""
from src import datos
from .catalogo import pedidos_definicion, seleccionar_0dte
from .precio import pedidos_es
from .trades import asegurar_tcbbo


def asegurar_odte(ventanas: dict, desde: str = "09:30", hasta: str = "16:00",
                  solo_costo: bool = False) -> float:
    """
    ventanas: {fecha: (strike_min, strike_max)}. Devuelve el costo estimado de lo pendiente.
    solo_costo=True: consulta sin descargar. Si al catálogo le faltan días, el costo del tcbbo
    no se puede calcular todavía: se informa y se devuelve solo el del paso 1.
    """
    fechas = sorted(ventanas)
    base = pedidos_definicion(fechas) + pedidos_es(fechas)
    costo = datos.asegurar_descargas(base, f"0DTE catálogo + ES, {len(fechas)} días", solo_costo=solo_costo)
    if solo_costo and costo > 0:
        datos._log("[costo] el tcbbo se puede cotizar recién cuando el catálogo esté en caché")
        return costo

    simbolos = {f: seleccionar_0dte(f, *ventanas[f])["raw_symbol"].tolist() for f in fechas}
    vacios = [f for f, s in simbolos.items() if not s]
    if vacios:
        raise RuntimeError(f"Sin opciones 0DTE en la ventana pedida: {', '.join(vacios)} "
                           f"(¿feriado, fin de semana o strikes fuera de rango?)")
    return costo + asegurar_tcbbo(simbolos, desde, hasta, solo_costo=solo_costo)
