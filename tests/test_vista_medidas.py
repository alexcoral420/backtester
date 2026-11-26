"""Tests de src/vista_medidas.py: el panel de medidas solo lee, no necesita la API key y dice qué falta."""
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from src import vista_medidas as vm

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_no_importa_config_ni_datos_y_no_necesita_la_clave():
    """En un proceso SIN la API key: importar la vista no debe traer config (gritaría) ni datos."""
    env = {k: v for k, v in os.environ.items() if k != "DATABENTO_API_KEY"}
    codigo = ("import sys; import src.vista_medidas; "
              "malos = [m for m in ('config', 'src.datos', 'src.gex', 'databento') if m in sys.modules]; "
              "print(malos); sys.exit(1 if malos else 0)")
    r = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_lo_que_falta_se_dice_con_el_comando(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for funcion, comando in ((vm.rango, "validar_rango"), (vm.verificacion, "verificar_gamma"),
                             (vm.gamma_local, "validar_gamma_local")):
        with pytest.raises(vm.SinDatos, match=comando):
            funcion()
    with pytest.raises(vm.SinDatos, match="perfil_gamma"):
        vm.perfil("2026-11-06")
    assert vm.fotos_con_perfil() == []


def test_clase_grita_con_columna_sin_clasificar():
    assert vm.clase("straddle") == "medido" and vm.clase("gex_bruto") == "modelo" and vm.clase("gex_sup") == "supuesto"
    with pytest.raises(ValueError):
        vm.clase("columna_nueva")
    for col in vm.NOMBRE:
        vm.clase(col)                                   # todo lo que el panel nombra tiene clase


def test_toda_columna_de_los_archivos_esta_clasificada(monkeypatch):
    """Las columnas de los acumuladores reales y de las tablas que arma la vista: clase o clave, nada suelto."""
    from src import perfil_gamma as pg
    monkeypatch.chdir(RAIZ)
    tablas = ((vm.RUTA_RANGO, vm.CLAVES), (vm.RUTA_LOCAL, vm.CLAVES), (vm.RUTA_VERIFICACION, vm.CLAVES_VERIFICACION))
    for ruta, claves in tablas:
        if not os.path.exists(ruta):
            continue
        for col in pd.read_csv(ruta, nrows=1).columns:
            if col not in claves:
                vm.clase(col)
    for col in list(vm.mapa(_perfil(), 7400.0).columns) + list(vm.totales_por_spot(_perfil()).columns):
        vm.clase(col)
    for col in ("gex_bruto", "gex_bruto_c", "gex_bruto_p", "gex_sup", "recalculada", "gex_bruto_total",
                "gex_sup_total"):
        assert vm.clase(col) == pg.clase(col)            # los dos contratos dicen lo mismo


def _perfil():
    filas = [dict(spot=s, zona=z, gex_bruto=1e9 * (1 + (z == s)), gex_sup=1e9 * (1 if z > s else -1), S=7500.0,
                  cobertura_pct=95.0) for s in (7400.0, 7500.0) for z in (7375.0, 7400.0, 7500.0, 7800.0)]
    p = pd.DataFrame(filas)
    # totales de TODAS las zonas (rejilla los suma antes de recortar): aquí, una zona de puts que no se guardó
    p["gex_bruto_total"] = p["spot"].map({7400.0: 8e9, 7500.0: 7e9})
    p["gex_sup_total"] = p["spot"].map({7400.0: -3e9, 7500.0: -1e9})
    return p


def test_mapa_compara_foto_y_recalculada_en_el_tramo():
    m = vm.mapa(_perfil(), 7400.0, radio=250)
    assert list(m.index) == [7375.0, 7400.0, 7500.0]                    # 7800 queda fuera del tramo
    assert m.loc[7400.0].to_dict() == {"foto": 1.0, "recalculada": 2.0}  # $B
    with pytest.raises(ValueError):
        vm.mapa(_perfil(), 7412.0)


def test_totales_por_spot_usa_los_totales_sin_recorte_y_no_mezcla_bruto_y_supuesto():
    t = vm.totales_por_spot(_perfil())
    assert list(t.columns) == ["gex_bruto_total", "gex_sup_total"]
    assert t.loc[7400.0].to_dict() == {"gex_bruto_total": 8.0, "gex_sup_total": -3.0}   # no la suma de lo guardado


def test_perfil_viejo_sin_totales_grita_con_el_comando(tmp_path, monkeypatch):
    from src import perfil_gamma as pg
    monkeypatch.setattr(pg, "RUTA_PERFIL", str(tmp_path / "perfil_gamma_{}.parquet"))
    _perfil().drop(columns=["gex_bruto_total", "gex_sup_total"]).to_parquet(tmp_path / "perfil_gamma_2026-11-06.parquet")
    with pytest.raises(vm.SinDatos, match="--rehacer"):
        vm.perfil("2026-11-06")


def _ver(movs, err):
    movs = np.asarray(movs, dtype=float)
    return pd.DataFrame(dict(mov_pct=movs, mov_abs=np.abs(movs), err_recalculada=err, err_vieja=np.asarray(err) * 3))


def test_banda_error_por_tramo():
    v = _ver([-0.1, -0.2, -0.3, -0.7, -1.5, -1.6, -4.0], [1.0, 3.0, 2.0, 5.0, 6.0, 7.0, 16.0])
    e = vm.banda_error(v, -0.25)
    assert e["tramo"] == "menos de 0,5%" and e["n"] == 3 and e["err_recalculada"] == 2.0 and e["peor"] == 3.0
    e = vm.banda_error(v, -1.5)                                          # 3 bajadas de 1,5% o más: hay banda
    assert e["tramo"] == "1% o más" and e["n"] == 3 and e["err_recalculada"] == 7.0 and e["peor"] == 16.0
    assert e["limite"] == 1.5
    vacio = vm.banda_error(v.drop(index=3), -0.8)                        # sin pares de 0,5% a 1%
    assert vacio["n"] == 0 and np.isnan(vacio["err_recalculada"])        # tramo vacío: nan, no un número inventado


def test_limite_verificado_exige_pares_del_mismo_sentido():
    v = _ver([-4.36, -2.02, -1.92, -1.82, 0.7, 1.31, 1.58, 2.35], [15.6, 4, 4, 4, 2, 4, 5, 6])
    assert vm.limite_verificado(v, -1) == 1.92                           # el tercer mayor de las bajadas
    assert vm.limite_verificado(v, 1) == 1.31
    assert vm.limite_verificado(v.iloc[:2], -1) == 0.0                   # menos de MIN_PARES_BANDA: nada verificado


def test_banda_error_no_presta_la_banda_mas_alla_de_lo_verificado():
    v = _ver([-4.36, -2.02, -1.92, -1.82, 0.7, 1.31, 1.58, 2.35], [15.6, 4, 4, 4, 2, 4, 5, 6])
    for mov in (-10.7, -4.0, -2.0):                                      # un par de −4,36% solo no alcanza
        e = vm.banda_error(v, mov)
        assert e["tramo"] == vm.SIN_VERIFICAR and e["n"] == 0 and e["limite"] == 1.92
        assert np.isnan(e["err_recalculada"]) and np.isnan(e["err_vieja"]) and np.isnan(e["peor"])
    assert vm.banda_error(v, 2.0)["tramo"] == vm.SIN_VERIFICAR           # al alza solo hay 3 pares hasta 1,31%
    e = vm.banda_error(v, -1.9)                                          # banda solo con las bajadas del tramo
    assert e["tramo"] == "1% o más" and e["sentido"] == "a la baja" and e["n"] == 4 and e["peor"] == 15.6
    t = vm.banda_error(v, -1.9, exigir_cobertura=False)                  # la tabla: tramo entero, los dos sentidos
    assert t["sentido"] == "ambos sentidos" and t["n"] == 7
    assert vm.banda_error(v, 2.0, exigir_cobertura=False)["tramo"] == "1% o más"   # la tabla del panel: el tramo


def test_resumen_local_separa_entre_dias_y_dentro_del_dia():
    filas = []
    for i in range(6):                                   # 6 días, 6 franjas; la gamma ordena los DÍAS, no las horas
        for j in range(6):
            filas.append(dict(fecha=f"2026-10-{i + 1:02d}", t=f"1{j}:00", gex_bruto_B=10 - i + 0.01 * ((j * 7) % 6),
                              gex_local_B=5 - i, rango_prev_pct=0.1 + 0.01 * i, impl_prev_pct=0.5 + 0.1 * i,
                              spx=7800.0 - 50 * i + j, rango_sig_pct=0.1 * (i + 1) + 0.001 * ((j * 5) % 6)))
    r = vm.resumen_local(pd.DataFrame(filas))
    assert r.at["spx", "clase"] == "medido" and r.at["spx", "entre_dias"] == pytest.approx(-1.0)   # el ingenuo va
    assert r.at["gex_bruto_B", "entre_dias"] == pytest.approx(-1.0) and r.at["gex_bruto_B", "franjas"] == 6
    assert r.at["gex_bruto_B", "clase"] == "modelo" and r.at["rango_prev_pct", "clase"] == "medido"
    assert np.isnan(r.at["impl_prev_pct", "dentro_del_dia"])            # un valor por día: sin corte dentro del día


def _bloques_con_precio(aporta: bool):
    """60 días × 4 franjas, con semilla fija. El rango depende del nivel del SPX y de un ruido propio; la gamma
    es el SPX más un extra por día que entra (o no) también en el rango."""
    rng = np.random.default_rng(7)
    extra, ruido = rng.normal(size=60), rng.normal(size=60)
    filas = []
    for i in range(60):
        for j in range(4):
            spx = 7800.0 - 10 * i
            filas.append(dict(fecha=str(pd.Timestamp("2026-08-03") + pd.Timedelta(days=i))[:10], t=f"1{j}:00",
                              spx=spx, gex_local_B=spx / 100 + 2 * extra[i], gex_bruto_B=spx / 10 + 20 * extra[i],
                              rango_sig_pct=(1.0 - spx / 10000 + 0.01 * ruido[i] + 0.0001 * j
                                             - (0.02 * extra[i] if aporta else 0.0))))
    return pd.DataFrame(filas)


def test_control_precio_distingue_una_gamma_que_solo_repite_el_precio():
    """Las dos gammas se parecen al SPX y las dos salen negativas sin descontar. Descontado el precio, la que
    no aporta se queda sin nada y la que aporta conserva su relación."""
    repite, aporta = vm.control_precio(_bloques_con_precio(False)), vm.control_precio(_bloques_con_precio(True))
    assert repite["gamma"] < -0.5 and aporta["gamma"] < -0.5 and 0.5 < repite["gamma_con_spx"] < 1.0
    assert repite["spx"] < -0.8
    assert abs(repite["parcial"]) < 0.3                       # el rango sigue al precio: a la gamma no le queda nada
    assert aporta["parcial"] < -0.5 and aporta["dias"] == 60
    lo, hi = repite["sin_un_dia"]
    assert lo <= repite["gamma"] <= hi


def test_parcial_no_inventa_cuando_el_predictor_es_el_control():
    from src import perfil_gamma as pg
    t = _bloques_con_precio(False)
    t["copia"] = t["spx"] * 2                                 # misma ordenación que el control
    assert pg.relacion_parcial_por_grupo(t, "t", "copia", "rango_sig_pct", "spx").isna().all()
