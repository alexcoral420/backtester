"""
signo_medido.py — Fase B3: el signo SUPUESTO (hipótesis nula) y el signo MEDIDO, lado a lado.

Nunca se fusionan en un número: cada wall muestra cuánto de su signo descansa en suposición.

  pct_delta_indet = qué parte del ΔOI del período NO quedó explicada por flujo con signo medido.
                    100% = el signo del cambio es pura suposición. ESTA es la conclusión de la fase B.
  pct_oi_supuesto = lo mismo sobre el OI total del wall (incluye el OI anterior al período, todo supuesto).

Veredicto contra la hipótesis nula (exige las DOS condiciones para opinar):
  - |neto medido| >= MIN_ABS contratos            (mínimo absoluto: 15 contratos no son evidencia)
  - |neto medido| >= MIN_REL x |ΔOI| del período  (mínimo relativo)
  si no -> "demasiado chico". Si el neto medido supera al ΔOI en magnitud y con signo opuesto a la
  apertura, hubo apertura y cierre mezclados -> "no atribuible".
"""
MIN_ABS = 200
MIN_REL = 0.20


def veredicto(neto_medido, delta_oi, accion_supuesta):
    """accion_supuesta: lo que la hipótesis nula dice que hace el público ('compra' o 'vende')."""
    if delta_oi == 0:
        return "sin ΔOI"
    if abs(neto_medido) < MIN_ABS or abs(neto_medido) < MIN_REL * abs(delta_oi):
        return "demasiado chico"
    if abs(neto_medido) > abs(delta_oi) and (neto_medido > 0) != (delta_oi > 0):
        return "no atribuible"
    medido = "compra" if neto_medido > 0 else "vende"
    return "confirma" if medido == accion_supuesta else "CONTRADICE"


def pct_delta_indet(neto_medido, delta_oi):
    """% del ΔOI sin signo medido (0 a 100). Con ΔOI 0 no hay nada que explicar -> nan."""
    if delta_oi == 0:
        return float("nan")
    explicado = min(abs(neto_medido), abs(delta_oi))
    return 100.0 * (1 - explicado / abs(delta_oi))


def pct_oi_supuesto(neto_medido, oi_final):
    """% del OI total del wall cuyo signo es supuesto (todo lo que no explica el flujo medido)."""
    if oi_final <= 0:
        return float("nan")
    return 100.0 * (1 - min(abs(neto_medido), oi_final) / oi_final)