"""
cero_dte.py — PUENTE de compatibilidad.

El código vive ahora en el paquete src/odte/ (un módulo por responsabilidad).
Este archivo solo reexporta los nombres para que los scripts existentes sigan
funcionando sin cambios. Cuando todos los scripts importen desde src.odte,
este archivo se puede borrar.
"""
from src.odte.constantes import CARPETA_CACHE, DATASET, RAIZ, ZONA_NY  # noqa: F401
from src.odte.catalogo import (descargar_definicion, filtrar_0dte,  # noqa: F401
                               seleccionar_0dte, resumen)
from src.odte.precio import descargar_es_1min, cierre_spx, spx_1min  # noqa: F401
from src.odte.trades import (_parametros_tcbbo, costo_tcbbo_0dte,  # noqa: F401
                             ruta_cache_tcbbo, descargar_tcbbo_0dte)
from src.odte.clasificacion import clasificar_trades  # noqa: F401
from src.odte.flujo import flujo_por_minuto  # noqa: F401