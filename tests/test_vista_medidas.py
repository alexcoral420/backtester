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
    for col in ("gex_bruto", "gex_bruto_c", "gex_bruto_p", "gex_sup", "recalculada"):
        assert vm.clase(col) == pg.clase(col)            # los dos contratos dicen lo mismo


def _perfil():
    filas = [dict(spot=s, zona=z, gex_bruto=1e9 * (1 + (z == s)), gex_sup=1e9 * (1 if z > s else -1), S=7500.0,
                  cobertura_pct=95.0) for s in (7400.0, 7500.0) for z in (7375.0, 7400.0, 7500.0, 7800.0)]
    return pd.DataFrame(filas)


def test_mapa_compara_foto_y_recalculada_en_el_tramo():
    m = vm.mapa(_perfil(), 7400.0, radio=250)
    assert list(m.index) == [7375.0, 7400.0, 7500.0]                    # 7800 queda fuera del tramo
    assert m.loc[7400.0].to_dict() == {"foto": 1.0, "recalculada": 2.0}  # $B
    with pytest.raises(ValueError):
        vm.mapa(_perfil(), 7412.0)


def test_totales_por_spot_no_mezcla_bruto_y_supuesto():
    t = vm.totales_por_spot(_perfil())
    assert t.loc[7400.0, "gex_bruto"] == pytest.approx(5.0) and t.loc[7400.0, "gex_sup"] == pytest.approx(0.0)


def test_banda_error_por_tramo():
    v = pd.DataFrame(dict(mov_abs=[0.1, 0.2, 0.7, 1.5, 4.0], err_recalculada=[1.0, 3.0, 5.0, 6.0, 16.0],
                          err_vieja=[4.0, 6.0, 10.0, 20.0, 30.0]))
    assert vm.banda_error(v, -0.3) == dict(tramo="menos de 0,5%", n=2, err_recalculada=2.0, err_vieja=5.0, peor=3.0)
    e = vm.banda_error(v, -4.4)
    assert e["n"] == 2 and e["err_recalculada"] == 11.0 and e["peor"] == 16.0
    assert np.isnan(vm.banda_error(v.iloc[:2], 2.0)["err_recalculada"])  # tramo vacío: nan, no un número inventado


def test_resumen_local_separa_entre_dias_y_dentro_del_dia():
    filas = []
    for i in range(6):                                   # 6 días, 6 franjas; la gamma ordena los DÍAS, no las horas
        for j in range(6):
            filas.append(dict(fecha=f"2026-10-{i + 1:02d}", t=f"1{j}:00", gex_bruto_B=10 - i + 0.01 * ((j * 7) % 6),
                              gex_local_B=5 - i, rango_prev_pct=0.1 + 0.01 * i, impl_prev_pct=0.5 + 0.1 * i,
                              rango_sig_pct=0.1 * (i + 1) + 0.001 * ((j * 5) % 6)))
    r = vm.resumen_local(pd.DataFrame(filas))
    assert r.at["gex_bruto_B", "entre_dias"] == pytest.approx(-1.0) and r.at["gex_bruto_B", "franjas"] == 6
    assert r.at["gex_bruto_B", "clase"] == "modelo" and r.at["rango_prev_pct", "clase"] == "medido"
    assert np.isnan(r.at["impl_prev_pct", "dentro_del_dia"])            # un valor por día: sin corte dentro del día
