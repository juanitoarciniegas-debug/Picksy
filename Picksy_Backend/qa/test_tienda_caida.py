"""
RF-06 y RNF-05: si una tienda no responde, el sistema lo informa y continúa con las demás.
Se simula una tienda caída, lenta, y la caída con datos viejos en caché.
"""
import time

import pytest

import buscador
from ayudas import buscar_ok, consulta_db
import cache
from mocks import producto

PRESUPUESTO = 500_000


@pytest.fixture
def tres_tiendas(tiendas):
    tiendas.poner("Éxito", producto("Éxito", "TV", 300_000))
    tiendas.poner("Alkosto", producto("Alkosto", "TV", 200_000))
    tiendas.poner("Ktronix", producto("Ktronix", "TV", 250_000))
    return tiendas


@pytest.mark.req("RF-06", "RNF-05")
def test_cp06_1_una_tienda_caida_se_avisa_y_se_muestran_las_demas(client, tres_tiendas, termino):
    tres_tiendas.hacer_fallar("Alkosto")
    r = client.get("/buscar", params={"producto": termino, "presupuesto": PRESUPUESTO})
    assert r.status_code == 200
    data = r.json()
    assert {o["tienda"] for o in data["viables"]} == {"Éxito", "Ktronix"}
    assert any("Alkosto" in aviso for aviso in data["avisos"]), data["avisos"]


@pytest.mark.req("RF-06", "RNF-05")
def test_cp06_2_todas_las_tiendas_caidas_responde_200_con_avisos(client, tres_tiendas, termino):
    for nombre in tres_tiendas.nombres:
        tres_tiendas.hacer_fallar(nombre)
    r = client.get("/buscar", params={"producto": termino, "presupuesto": PRESUPUESTO})
    assert r.status_code == 200
    data = r.json()
    assert data["viables"] == [] and data["mejor_opcion"] is None
    assert len(data["avisos"]) == len(tres_tiendas.nombres)


@pytest.mark.req("RF-06")
def test_cp06_3_tienda_caida_con_datos_viejos_usa_la_cache_y_lo_avisa(client, tres_tiendas, termino):
    buscar_ok(client, termino, PRESUPUESTO)                       # llena la caché
    consulta_db("UPDATE cache_busquedas SET consultado_en = NOW() - INTERVAL '25 hours' "
                "WHERE termino = %s", (cache.normalizar(termino),))   # ahora está vencida
    tres_tiendas.hacer_fallar("Alkosto")
    data = buscar_ok(client, termino, PRESUPUESTO)
    assert "Alkosto" in {o["tienda"] for o in data["viables"]}, "Debe mostrar los datos guardados"
    assert any("Alkosto" in a and "guardados" in a for a in data["avisos"]), data["avisos"]


@pytest.mark.req("RF-06", "RNF-05")
def test_cp06_4_tienda_lenta_no_bloquea_la_respuesta(client, tres_tiendas, termino, monkeypatch):
    monkeypatch.setattr(buscador, "LIMITE_SEGUNDOS", 0.4)
    tres_tiendas.hacer_lenta("Alkosto", 1.5)
    inicio = time.perf_counter()
    data = buscar_ok(client, termino, PRESUPUESTO)
    duracion = time.perf_counter() - inicio
    assert duracion < 1.2, f"Esperó a la tienda lenta ({duracion:.1f} s)"
    assert {o["tienda"] for o in data["viables"]} == {"Éxito", "Ktronix"}
    assert any("Alkosto" in a and "tardó" in a for a in data["avisos"]), data["avisos"]


@pytest.mark.req("RNF-05")
def test_rnf05_1_con_tiendas_caidas_el_resto_del_sistema_sigue_vivo(client, tres_tiendas, termino):
    for nombre in tres_tiendas.nombres:
        tres_tiendas.hacer_fallar(nombre)
    buscar_ok(client, termino, PRESUPUESTO)
    assert client.get("/").status_code == 200
    assert client.get("/tiendas").status_code == 200
