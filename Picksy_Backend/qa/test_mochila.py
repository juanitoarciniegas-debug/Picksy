"""
MOCHILA 0/1 (RF-14): de todos los productos del carrito, elegir los que MÁS prioridad suman sin pasar del presupuesto.
Nuevo en la v3: POST /carritos/{id}/optimizar.

El resultado de la API se compara contra el ORÁCULO de QA (qa/referencia_mochila.py), que prueba todas las
combinaciones posibles (fuerza bruta). Si coinciden en cientos de casos al azar, la mochila es correcta.
Desempate documentado en el oráculo y en carritos.py: a igual prioridad gana el menor costo.
"""
import random
import time

import pytest

from ayudas import agregar_item_ok, crear_carrito, usuario_con_sesion
from referencia_mochila import fuerza_bruta

pytestmark = pytest.mark.req("RF-14")


@pytest.fixture
def u(client):
    return usuario_con_sesion(client)[1]


def _optimizar(client, u, presupuesto, items):
    """items: lista de (precio_total, prioridad). Devuelve (carrito_id, respuesta_de_optimizar)."""
    c = crear_carrito(client, u, presupuesto)
    for precio, prio in items:
        agregar_item_ok(client, u, c["id"], precio, prio)
    r = client.post(f"/carritos/{c['id']}/optimizar", headers=u)
    assert r.status_code == 200, r.text
    return c["id"], r.json()


def _optimizar_y_borrar(client, u, presupuesto, items):
    """Igual que _optimizar pero borra el carrito: un usuario solo puede tener 30."""
    cid, d = _optimizar(client, u, presupuesto, items)
    client.delete(f"/carritos/{cid}", headers=u)
    return d


# ----------------------------------------------------------------------------- casos calculados a mano
def test_cp14_1_ejemplo_a_mano(client, u):
    """(300,5) (200,4) (250,3) (100,1) con $500: lo mejor es 300+200 = prioridad 9."""
    _, d = _optimizar(client, u, 500, [(300, 5), (200, 4), (250, 3), (100, 1)])
    assert sorted((i["precio_total"], i["prioridad"]) for i in d["incluidos"]) == [(200, 4), (300, 5)]
    assert d["prioridad_total"] == 9 and d["total"] == 500 and d["sobrante"] == 0
    assert len(d["excluidos"]) == 2


def test_cp14_2_el_mas_caro_puede_quedar_fuera_si_hay_dos_que_suman_mas_prioridad(client, u):
    """Un solo producto de prioridad 5 por $600 vs. dos de prioridad 4 por $300 c/u, con $600: gana el par (8 > 5)."""
    _, d = _optimizar(client, u, 600, [(600, 5), (300, 4), (300, 4)])
    assert d["prioridad_total"] == 8 and len(d["incluidos"]) == 2


def test_cp14_3_todos_caben(client, u):
    _, d = _optimizar(client, u, 10_000, [(100, 1), (200, 2), (300, 3)])
    assert len(d["incluidos"]) == 3 and d["excluidos"] == []
    assert d["mensaje"] == "Todos los productos caben en el presupuesto."
    assert d["sobrante"] == 10_000 - 600


def test_cp14_4_ninguno_cabe_se_avisa(client, u):
    _, d = _optimizar(client, u, 500, [(600, 5), (700, 4)])
    assert d["incluidos"] == [] and len(d["excluidos"]) == 2 and d["total"] == 0
    assert d["mensaje"] == "Ningún producto cabe en el presupuesto." and d["prioridad_total"] == 0


def test_cp14_5_carrito_vacio_se_avisa_sin_error(client, u):
    _, d = _optimizar(client, u, 500, [])
    assert d["incluidos"] == [] and d["excluidos"] == [] and "vacío" in d["mensaje"]


def test_cp14_6_presupuesto_exactamente_igual_a_la_suma_si_cabe(client, u):
    _, d = _optimizar(client, u, 300, [(100, 2), (200, 3)])
    assert len(d["incluidos"]) == 2 and d["sobrante"] == 0


def test_cp14_6b_un_peso_menos_y_ya_no_cabe_el_par(client, u):
    _, d = _optimizar(client, u, 299, [(100, 2), (200, 3)])
    assert [i["precio_total"] for i in d["incluidos"]] == [200]


def test_cp14_7_el_envio_cuenta_para_el_presupuesto(client, u):
    c = crear_carrito(client, u, 1_000)
    agregar_item_ok(client, u, c["id"], 600, 5, envio=500)         # cuesta 1.100: no cabe
    agregar_item_ok(client, u, c["id"], 400, 1)
    d = client.post(f"/carritos/{c['id']}/optimizar", headers=u).json()
    assert [i["precio_total"] for i in d["incluidos"]] == [400]
    assert [i["precio_total"] for i in d["excluidos"]] == [1_100]


def test_cp14_8_a_igual_prioridad_gana_el_de_menor_costo(client, u):
    _, d = _optimizar(client, u, 500, [(500, 3), (200, 3)])
    assert [i["precio_total"] for i in d["incluidos"]] == [200]


def test_cp14_9_prioridad_baja_y_barata_no_desplaza_a_prioridad_alta(client, u):
    _, d = _optimizar(client, u, 400, [(400, 5), (100, 1), (100, 1), (100, 1), (100, 1)])
    assert d["prioridad_total"] == 5 and len(d["incluidos"]) == 1


def test_cp14_10_centavos_se_calculan_sin_error_de_decimales(client, u):
    """0.1 + 0.2 no debe dar 0.30000000000000004 y pasarse del presupuesto de 0.30."""
    _, d = _optimizar(client, u, 0.30, [(0.10, 3), (0.20, 3)])
    assert len(d["incluidos"]) == 2 and d["total"] == pytest.approx(0.30, abs=1e-9) and d["sobrante"] == 0


# ----------------------------------------------------------------------------- coherencia de la respuesta
def test_cp14_11_la_respuesta_es_coherente_consigo_misma_y_con_el_carrito(client, u):
    cid, d = _optimizar(client, u, 700, [(300, 5), (250, 3), (200, 4), (150, 2), (400, 1)])
    ids_dentro, ids_fuera = {i["id"] for i in d["incluidos"]}, {i["id"] for i in d["excluidos"]}
    assert ids_dentro.isdisjoint(ids_fuera) and len(ids_dentro | ids_fuera) == 5
    assert d["total"] == sum(i["precio_total"] for i in d["incluidos"]) <= 700
    assert d["prioridad_total"] == sum(i["prioridad"] for i in d["incluidos"])
    assert d["sobrante"] == pytest.approx(700 - d["total"])
    assert d["presupuesto"] == 700
    # y el carrito guardado dice lo mismo
    ver = client.get(f"/carritos/{cid}", headers=u).json()
    assert ver["optimizado"] is True and ver["total"] == d["total"] and ver["prioridad_total"] == d["prioridad_total"]
    assert {i["id"] for i in ver["items"] if i["incluido"]} == ids_dentro


def test_cp14_12_optimizar_dos_veces_da_el_mismo_resultado(client, u):
    cid, primero = _optimizar(client, u, 500, [(300, 5), (200, 4), (250, 3), (100, 1)])
    segundo = client.post(f"/carritos/{cid}/optimizar", headers=u).json()
    assert {i["id"] for i in primero["incluidos"]} == {i["id"] for i in segundo["incluidos"]}


def test_cp14_13_optimizar_cambia_el_total_del_carrito_solo_a_lo_incluido(client, u):
    c = crear_carrito(client, u, 500)
    for p, pr in [(300, 5), (200, 4), (250, 3)]:
        agregar_item_ok(client, u, c["id"], p, pr)
    antes = client.get(f"/carritos/{c['id']}", headers=u).json()
    assert antes["optimizado"] is False and antes["total"] == 750, "Sin optimizar, el total cuenta todos los productos"
    client.post(f"/carritos/{c['id']}/optimizar", headers=u)
    despues = client.get(f"/carritos/{c['id']}", headers=u).json()
    assert despues["total"] == 500


def test_cp14_14_sin_sesion_da_401(client):
    assert client.post("/carritos/1/optimizar").status_code == 401


# ----------------------------------------------------------------------------- contra el oráculo
def _caso_al_azar(azar):
    n = azar.randint(1, 9)
    items = [(azar.randint(1, 60) * 10, azar.randint(1, 5)) for _ in range(n)]
    presupuesto = azar.randint(1, 15) * 50
    return items, presupuesto


def test_cp14_15_coincide_con_el_oraculo_de_fuerza_bruta_en_60_casos_al_azar(client, u):
    azar = random.Random(20261107)                       # semilla fija: siempre los mismos casos
    for numero in range(60):
        items, presupuesto = _caso_al_azar(azar)
        d = _optimizar_y_borrar(client, u, presupuesto, items)
        prioridad, costo, _indices = fuerza_bruta(items, presupuesto)
        obtenido = (d["prioridad_total"], d["total"])
        assert obtenido == (prioridad, costo), (
            f"Caso {numero}: items (costo, prioridad)={items}, presupuesto={presupuesto}. "
            f"API={obtenido}, oráculo={(prioridad, costo)}")


def test_cp14_16_el_total_nunca_supera_el_presupuesto_en_100_casos_al_azar(client, u):
    azar = random.Random(7)
    for _ in range(100):
        items, presupuesto = _caso_al_azar(azar)
        c = crear_carrito(client, u, presupuesto)
        for precio, prio in items:
            agregar_item_ok(client, u, c["id"], precio, prio)
        d = client.post(f"/carritos/{c['id']}/optimizar", headers=u).json()
        assert d["total"] <= presupuesto and d["sobrante"] >= 0
        client.delete(f"/carritos/{c['id']}", headers=u)


def test_cp14_17_50_productos_y_presupuesto_gigante_responde_rapido(client, u):
    """Límite máximo del carrito (50) con el presupuesto máximo (mil millones): no debe tardar ni fallar."""
    azar = random.Random(3)
    c = crear_carrito(client, u, 1_000_000_000)
    for _ in range(50):
        agregar_item_ok(client, u, c["id"], azar.randint(1_000, 5_000_000), azar.randint(1, 5))
    inicio = time.perf_counter()
    r = client.post(f"/carritos/{c['id']}/optimizar", headers=u)
    assert r.status_code == 200 and time.perf_counter() - inicio < 5
    d = r.json()
    assert d["total"] <= 1_000_000_000 and d["prioridad_total"] > 0
