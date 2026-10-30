"""Historial de búsquedas: RF-15 (guarda fecha, producto, presupuesto y resultado)."""
from datetime import datetime

import pytest

from ayudas import buscar_ok, consulta_db, usuario_con_sesion
from mocks import producto

pytestmark = pytest.mark.req("RF-15")
PRESUPUESTO = 500_000


@pytest.fixture
def tv(tiendas):
    tiendas.poner("Éxito", producto("Éxito", "TV", 300_000))
    tiendas.poner("Alkosto", producto("Alkosto", "TV", 600_000))
    return tiendas


def test_cp15_1_la_busqueda_con_sesion_queda_con_fecha_producto_presupuesto_y_resultado(client, tv, termino):
    _, cab = usuario_con_sesion(client)
    buscar_ok(client, termino, PRESUPUESTO, cab)
    filas = client.get("/historial", headers=cab).json()
    assert len(filas) == 1
    fila = filas[0]
    assert fila["termino"] == termino and fila["presupuesto"] == PRESUPUESTO
    assert datetime.fromisoformat(fila["creado_en"])
    assert fila["resultado"]["viables"] == 1 and fila["resultado"]["descartadas"] == 1
    assert fila["resultado"]["mejor"]["tienda"] == "Éxito"


def test_cp15_1b_lo_mas_reciente_aparece_primero(client, tv, termino):
    _, cab = usuario_con_sesion(client)
    buscar_ok(client, termino + " a", PRESUPUESTO, cab)
    buscar_ok(client, termino + " b", PRESUPUESTO, cab)
    assert [f["termino"] for f in client.get("/historial", headers=cab).json()] == [termino + " b", termino + " a"]


def test_cp15_2_sin_sesion_no_se_guarda_nada(client, tv, termino):
    antes = consulta_db("SELECT COUNT(*) FROM historial_busquedas")[0][0]
    buscar_ok(client, termino, PRESUPUESTO)
    assert consulta_db("SELECT COUNT(*) FROM historial_busquedas")[0][0] == antes


def test_cp15_2b_token_invalido_busca_normal_y_no_guarda(client, tv, termino):
    antes = consulta_db("SELECT COUNT(*) FROM historial_busquedas")[0][0]
    buscar_ok(client, termino, PRESUPUESTO, {"Authorization": "Bearer token-falso"})
    assert consulta_db("SELECT COUNT(*) FROM historial_busquedas")[0][0] == antes


def test_cp15_3_cada_usuario_ve_solo_su_historial(client, tv, termino):
    _, a = usuario_con_sesion(client)
    _, b = usuario_con_sesion(client)
    buscar_ok(client, termino, PRESUPUESTO, a)
    assert len(client.get("/historial", headers=a).json()) == 1
    assert client.get("/historial", headers=b).json() == []


def test_cp15_3b_no_se_puede_borrar_el_historial_de_otro_usuario(client, tv, termino):
    _, a = usuario_con_sesion(client)
    _, b = usuario_con_sesion(client)
    buscar_ok(client, termino, PRESUPUESTO, a)
    id_de_a = client.get("/historial", headers=a).json()[0]["id"]
    assert client.delete(f"/historial/{id_de_a}", headers=b).status_code == 404
    assert len(client.get("/historial", headers=a).json()) == 1


def test_cp15_4_comportamiento_actual_misma_busqueda_en_un_minuto_se_guarda_una_vez(client, tv, termino):
    """COMPORTAMIENTO DOCUMENTADO en historial.py (evita duplicados por doble clic)."""
    _, cab = usuario_con_sesion(client)
    buscar_ok(client, termino, PRESUPUESTO, cab)
    buscar_ok(client, termino, PRESUPUESTO, cab)
    assert len(client.get("/historial", headers=cab).json()) == 1
    buscar_ok(client, termino, PRESUPUESTO + 1, cab)            # otro presupuesto = otra búsqueda
    assert len(client.get("/historial", headers=cab).json()) == 2


def test_cp15_5_borrar_una_y_borrar_todo(client, tv, termino):
    _, cab = usuario_con_sesion(client)
    buscar_ok(client, termino + " a", PRESUPUESTO, cab)
    buscar_ok(client, termino + " b", PRESUPUESTO, cab)
    primero = client.get("/historial", headers=cab).json()[0]["id"]
    assert client.delete(f"/historial/{primero}", headers=cab).status_code == 200
    assert len(client.get("/historial", headers=cab).json()) == 1
    assert client.delete("/historial", headers=cab).json()["borradas"] == 1
    assert client.get("/historial", headers=cab).json() == []
