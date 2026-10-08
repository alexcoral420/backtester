"""
dealer.py — La tabla de signos del dealer, convertida en código.

Reglas (ver master class, módulo 1):
  0) El dealer es el lado PASIVO: hace lo contrario del público.
  1) delta del dealer = signo del dealer x signo de la opción
       signo dealer: long = +1, short = -1
       signo opción: call = +1, put = -1
  2) gamma del dealer = signo del dealer (toda opción comprada tiene gamma +)
  3) delta - -> compra índice para cubrirse | delta + -> vende índice
     gamma + -> frena (barrera)            | gamma - -> amplifica (trampolín)
"""

ACCIONES = {"compra": -1, "vende": +1}   # acción del público -> signo del DEALER (lo contrario)
TIPOS = {"C": +1, "P": -1}               # signo de la opción


def posicion_dealer(publico: str, tipo: str) -> dict:
    """
    publico: "compra" o "vende" (lo que hizo el agresor)
    tipo:    "C" o "P"
    Devuelve el lado del dealer, el signo de su delta y gamma, su cobertura y el efecto.
    """
    if publico not in ACCIONES:
        raise ValueError(f"publico debe ser 'compra' o 'vende', no {publico!r}")
    if tipo not in TIPOS:
        raise ValueError(f"tipo debe ser 'C' o 'P', no {tipo!r}")

    signo_dealer = ACCIONES[publico]
    delta = signo_dealer * TIPOS[tipo]
    gamma = signo_dealer
    return {
        "lado": "long" if signo_dealer > 0 else "short",
        "delta": delta,
        "gamma": gamma,
        "cobertura": "compra índice" if delta < 0 else "vende índice",
        "efecto": "frena" if gamma > 0 else "amplifica",
    }