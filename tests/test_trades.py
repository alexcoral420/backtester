"""
Ruta de caché del tcbbo. Si esto se rompe, el proyecto vuelve a PAGAR por datos que ya tiene.
"""
from src.odte.trades import ruta_cache_tcbbo

SIMBOLOS = ["SPXW  261002P07700000", "SPXW  261002P07695000"]


def test_el_orden_de_los_simbolos_no_importa():
    a = ruta_cache_tcbbo("2026-10-02", SIMBOLOS)
    b = ruta_cache_tcbbo("2026-10-02", list(reversed(SIMBOLOS)))
    assert a == b


def test_dia_completo_no_lleva_sufijo():
    """Compatibilidad: los archivos del día completo ya descargados no tienen sufijo de franja."""
    ruta = ruta_cache_tcbbo("2026-10-02", SIMBOLOS)
    assert ruta.endswith(".parquet")
    assert "_0930-1600" not in ruta


def test_franja_lleva_sufijo():
    ruta = ruta_cache_tcbbo("2026-10-02", SIMBOLOS, "09:30", "11:00")
    assert ruta.endswith("_0930-1100.parquet")


def test_simbolos_distintos_rutas_distintas():
    """Si dos listas distintas compartieran archivo, leeríamos datos de OTRAS opciones."""
    a = ruta_cache_tcbbo("2026-10-02", SIMBOLOS)
    b = ruta_cache_tcbbo("2026-10-02", SIMBOLOS[:1])
    assert a != b


def test_fechas_distintas_rutas_distintas():
    assert ruta_cache_tcbbo("2026-10-02", SIMBOLOS) != ruta_cache_tcbbo("2026-09-29", SIMBOLOS)