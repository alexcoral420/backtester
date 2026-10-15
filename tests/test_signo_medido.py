"""B3: el veredicto exige evidencia mínima y el % supuesto se mide sin fusionar fuentes."""
import math

from src.signo_medido import pct_delta_indet, pct_oi_supuesto, veredicto


def test_quince_contratos_no_son_evidencia():
    """Regresión del 15-oct: 7400P oct, neto +15 sobre ΔOI 45 salía 'confirma'."""
    assert veredicto(15, 45, "compra") == "demasiado chico"


def test_contradice_con_evidencia_suficiente():
    """7500P dic: neto -1.270 sobre ΔOI +4.592 -> el público VENDIÓ, la nula decía 'compra'."""
    assert veredicto(-1270, 4592, "compra") == "CONTRADICE"


def test_confirma():
    assert veredicto(800, 2000, "compra") == "confirma"


def test_flujo_mayor_que_el_delta_y_opuesto_no_se_atribuye():
    """7500P oct: neto -511 con ΔOI +219 -> apertura y cierre mezclados."""
    assert veredicto(-511, 219, "compra") == "no atribuible"


def test_pct_indeterminado():
    assert pct_delta_indet(-1270, 4592) == 100 * (1 - 1270 / 4592)
    assert pct_delta_indet(0, 1000) == 100.0              # nada medido: signo 100% supuesto
    assert pct_delta_indet(5000, 1000) == 0.0             # topa en 0, no da negativo
    assert math.isnan(pct_delta_indet(10, 0))


def test_pct_oi_supuesto():
    assert pct_oi_supuesto(1270, 38965) == 100 * (1 - 1270 / 38965)