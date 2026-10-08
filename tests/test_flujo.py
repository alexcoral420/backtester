"""Agregación por minuto: separa calls y puts, suma dentro del minuto y acumula."""
import pandas as pd

from src.odte.flujo import flujo_por_minuto


def test_agrupa_por_minuto_y_acumula():
    idx = pd.to_datetime([
        "2026-10-02 09:50:10", "2026-10-02 09:50:40",   # minuto 09:50: dos calls
        "2026-10-02 09:51:05",                          # minuto 09:51: un put
    ]).tz_localize("America/New_York")
    clasificados = pd.DataFrame({
        "instrument_class": ["C", "C", "P"],
        "flujo": pd.Series([100, -30, -50], dtype="int64").values,
    }, index=idx)

    r = flujo_por_minuto(clasificados)

    assert list(r["flujo_C"]) == [70, 0]      # 100 - 30 en el primer minuto
    assert list(r["flujo_P"]) == [0, -50]
    assert list(r["acum_C"]) == [70, 70]      # el acumulado se mantiene
    assert list(r["acum_P"]) == [0, -50]