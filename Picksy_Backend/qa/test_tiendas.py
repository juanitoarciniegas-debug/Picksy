"""
Datos de referencia de las tiendas (RF-04). DEF-02 como prueba PERMANENTE:
si agregan una tienda sin conector, o se quita una, estas pruebas lo detectan solas.
Tres listas deben coincidir: las 10 del ERS, la tabla `tiendas` y los conectores de la API.
"""
import re

import pytest

import buscador
from ayudas import consulta_db
from conftest import REQUISITOS

ERS = set(REQUISITOS["tiendas_ers"])


def _bd():
    return {f[0] for f in consulta_db("SELECT nombre FROM tiendas")}


def _api(client):
    return {t["nombre"] for t in client.get("/tiendas").json()}


@pytest.mark.req("RF-04")
def test_cp04_2_la_base_tiene_las_tiendas_del_ers():
    assert _bd() == ERS, f"Faltan: {ERS - _bd()} · Sobran: {_bd() - ERS}"


@pytest.mark.req("RF-04")
@pytest.mark.xfail(strict=False, reason=(
    "DEF-02: la API expone 9 tiendas y el ERS dice 10 (falta Mercado Libre). "
    "Pasa a verde cuando el equipo agregue el conector o corrija el ERS."))
def test_cp04_2b_la_api_expone_las_10_tiendas_del_ers(client):
    api = _api(client)
    assert api == ERS, f"Sin conector: {sorted(ERS - api)} · Fuera del ERS: {sorted(api - ERS)}"


@pytest.mark.req("RF-04")
def test_cp04_2c_todo_conector_tiene_su_tienda_en_la_base(client):
    """Si el nombre de un conector no coincide EXACTO con la tabla tiendas (ej. una tilde),
    la caché de esa tienda no se guarda y nadie se entera."""
    assert _api(client) - _bd() == set()


@pytest.mark.req("RF-04")
def test_cp04_2d_ningun_conector_es_una_tienda_fuera_del_ers(client):
    assert _api(client) - ERS == set()


@pytest.mark.req("RF-04")
def test_cp04_2e_los_conectores_cumplen_la_interfaz_y_no_se_repiten():
    nombres = [c.nombre for c in buscador.CONECTORES]
    assert len(nombres) == len(set(nombres)), "Hay conectores con el mismo nombre"
    for c in buscador.CONECTORES:
        assert isinstance(c.nombre, str) and c.nombre.strip()
        assert callable(getattr(c, "buscar", None)), f"{c.nombre} no tiene buscar()"


@pytest.mark.req("RF-04")
def test_cp04_2f_tiendas_devuelve_nombre_y_especialidad(client):
    for t in client.get("/tiendas").json():
        assert {"nombre", "especialidad"} <= set(t)
