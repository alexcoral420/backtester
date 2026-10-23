"""walls.py: la descomposición del ΔGEX es exacta y cada causa cae en su componente."""
import pandas as pd
import pytest

from src.walls import descomponer, evolucion, zonas_dia


def _cadena(filas, S=7700.0):
    """filas: (symbol, tipo, strike, OI, k) -> cadena mínima con gex_contrib = OI · k."""
    c = pd.DataFrame(filas, columns=["symbol", "tipo", "strike", "open_interest", "k"])
    c["gex_contrib"] = c["open_interest"] * c.pop("k")
    c["S"] = S
    return c


AYER = _cadena([("A", "C", 7800.0, 100, 10.0),      # sigue, mismo OI, cambia k  -> solo mercado
                ("B", "P", 7600.0, 200, -5.0),      # sigue, OI sube, mismo k    -> solo posicionamiento
                ("V", "P", 7610.0, 50, -8.0)])      # vence                      -> solo vencidas
HOY = _cadena([("A", "C", 7800.0, 100, 12.0),
               ("B", "P", 7600.0, 260, -5.0),
               ("N", "C", 7790.0, 30, 11.0)])       # nueva                      -> posicionamiento entero


def test_la_suma_cierra_exacta():
    p = descomponer(AYER, HOY)
    assert p[["pos", "mer", "ven"]].to_numpy().sum() == pytest.approx(
        HOY["gex_contrib"].sum() - AYER["gex_contrib"].sum())


def test_cada_causa_en_su_componente():
    p = descomponer(AYER, HOY)
    assert (p.loc["A", "pos"], p.loc["A", "mer"]) == (0, 200)              # 100 · (12 - 10)
    assert (p.loc["B", "pos"], p.loc["B", "mer"], p.loc["B", "doi"]) == (-300, 0, 60)
    assert (p.loc["N", "pos"], p.loc["N", "doi"]) == (330, 30)
    assert (p.loc["V", "ven"], p.loc["V", "oi_venc"], p.loc["V", "doi"]) == (400, 50, 0)


def test_vencer_no_cuenta_como_posicion_cerrada():
    """V (7610) cae en la zona 7600 con B: su salida va a oi_venc, no resta al ΔOI de puts."""
    _, z = evolucion({pd.Timestamp("2026-10-15"): AYER, pd.Timestamp("2026-10-16"): HOY})
    fila = z[(z["fecha"] == pd.Timestamp("2026-10-16")) & (z["zona"] == 7600)].iloc[0]
    assert fila["doi_p"] == 60 and fila["oi_venc"] == 50 and fila["ven"] == 400


def test_zonas_dia_mide_carga_y_balance():
    z = zonas_dia(HOY)
    assert (z.loc[7600, "oi_p"], z.loc[7600, "pct_puts"]) == (260, 100)
    assert (z.loc[7800, "oi_c"], z.loc[7800, "gex"]) == (130, 1200 + 330)    # 7790 cae en la zona 7800


def test_evolucion_primer_dia_sin_cambios_y_resumen():
    d, z = evolucion({pd.Timestamp("2026-10-15"): AYER, pd.Timestamp("2026-10-16"): HOY})
    assert z.loc[z["fecha"] == pd.Timestamp("2026-10-15"), "pos"].isna().all()
    assert d.loc[pd.Timestamp("2026-10-16"), ["pos", "mer", "ven"]].sum() == pytest.approx(
        d.loc[pd.Timestamp("2026-10-16"), "gex"] - d.loc[pd.Timestamp("2026-10-15"), "gex"])


def test_una_sola_fecha_no_rompe():
    d, z = evolucion({pd.Timestamp("2026-10-15"): AYER})
    assert len(d) == 1 and z["pos"].isna().all()


# --- Contrato medido / supuesto ---

def test_contrato_cubre_todas_las_columnas_y_no_se_solapa():
    """Toda columna de datos que sale de walls.py está clasificada: si alguien agrega una sin
    clasificarla, este test falla (la app no podría saber si etiquetarla como supuesta)."""
    from src.walls import CLAVES, MEDIDAS, MODELO, SUPUESTAS, rotacion, zonas_por_tramo
    assert not set(MEDIDAS) & set(SUPUESTAS) and not set(MODELO) & (set(MEDIDAS) | set(SUPUESTAS))
    d, z = evolucion({pd.Timestamp("2026-10-15"): AYER, pd.Timestamp("2026-10-16"): HOY})
    hoy = HOY.assign(raiz="SPXW", dte=3)
    for df in (d, z, zonas_dia(HOY).reset_index(), zonas_por_tramo(hoy), rotacion(z, [7600, 7800]).reset_index()):
        sin_clasificar = set(df.columns) - set(MEDIDAS) - set(MODELO) - set(SUPUESTAS) - set(CLAVES)
        assert not sin_clasificar, sin_clasificar


def test_es_supuesta_grita_con_columna_desconocida():
    from src.walls import clase, es_supuesta
    assert es_supuesta("gex") and not es_supuesta("oi_c") and not es_supuesta("gex_bruto")
    assert (clase("gex"), clase("gex_bruto"), clase("oi_c")) == ("supuesto", "modelo", "medido")
    with pytest.raises(ValueError, match="sin clasificar"):
        es_supuesta("gex_bonito")


def test_zonas_por_tramo_parte_por_raiz_y_plazo():
    from src.walls import zonas_por_tramo
    c = HOY.assign(raiz=["SPX", "SPXW", "SPXW"], dte=[40, 2, 2])
    t = zonas_por_tramo(c).set_index(["zona", "raiz", "tramo"])
    assert t.loc[(7800, "SPX", ">35d"), "oi_c"] == 100
    assert t.loc[(7800, "SPXW", "1-3d"), "gex"] == 330
    assert t.loc[(7600, "SPXW", "1-3d"), "oi_p"] == 260
    assert t["gex"].sum() == pytest.approx(HOY["gex_contrib"].sum())


def test_rotacion_cuenta_abierto_y_vencido_sin_el_primer_dia():
    from src.walls import rotacion
    _, z = evolucion({pd.Timestamp("2026-10-15"): AYER, pd.Timestamp("2026-10-16"): HOY})
    r = rotacion(z, [7600]).loc[7600]
    assert (r["oi_ini"], r["oi_fin"]) == (250, 260)               # B 200 + V 50 -> B 260
    assert (r["doi_p"], r["oi_venc"], r["renovado_pct"]) == (60, 50, 20)
    assert r["pos"] + r["mer"] + r["ven"] == pytest.approx(-1300 - (-1400))


def test_evolucion_agrega_dS_y_distancia():
    d, z = evolucion({pd.Timestamp("2026-10-15"): AYER, pd.Timestamp("2026-10-16"): HOY.assign(S=7750.0)})
    assert d["dS"].iloc[1] == 50
    fila = z[(z["fecha"] == pd.Timestamp("2026-10-16")) & (z["zona"] == 7800)].iloc[0]
    assert fila["dist_pct"] == pytest.approx(50 / 7750 * 100) and fila["oi_total"] == 130


def test_rotacion_wall_sin_fila_el_primer_dia_queda_nan():
    """Regresión del revisor: 7775 solo existe el 2º día; su oi_ini no debe tomarse de otra fecha."""
    from src.walls import rotacion
    hoy = pd.concat([HOY, _cadena([("M", "C", 7775.0, 40, 9.0)])], ignore_index=True)
    _, z = evolucion({pd.Timestamp("2026-10-15"): AYER, pd.Timestamp("2026-10-16"): hoy})
    r = rotacion(z, [7600, 7775])
    assert pd.isna(r.loc[7775, "oi_ini"]) and pd.isna(r.loc[7775, "renovado_pct"])
    assert (r.loc[7775, "oi_fin"], r.loc[7775, "doi_c"]) == (40, 40)
    assert r.loc[7600, "oi_ini"] == 250


def test_gex_bruto_suma_sin_signo_y_desbalance():
    """Zona 7800: A (k 12, OI 100) y N (k 11, OI 30) calls -> bruto 1530, todo calls: desbalance 100.
    Con calls y puts de igual bruto el desbalance es 0 aunque cada lado sea grande (GEX neto frágil)."""
    z = zonas_dia(HOY)
    assert (z.loc[7800, "gex_bruto"], z.loc[7800, "desbalance_pct"]) == (1530, 100)
    assert z.loc[7600, "gex_bruto_p"] == 1300 and z.loc[7600, "gex"] == -1300
    eq = zonas_dia(_cadena([("X", "C", 8000.0, 100, 10.0), ("Y", "P", 8000.0, 100, -10.0)]))
    assert (eq.loc[8000, "gex"], eq.loc[8000, "gex_bruto"], eq.loc[8000, "desbalance_pct"]) == (0, 2000, 0)
