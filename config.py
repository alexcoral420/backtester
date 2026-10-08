import os

# La API key se lee de la variable de entorno (NUNCA hardcodeada)
DATABENTO_KEY = os.environ.get("DATABENTO_API_KEY")
if DATABENTO_KEY is None:
    raise ValueError(
        "Falta la API key. Configurala con:\n"
        '  $env:DATABENTO_API_KEY = "db-tu-clave"   (PowerShell)'
    )

# Constantes del proyecto
TASA_LIBRE_RIESGO = 0.047