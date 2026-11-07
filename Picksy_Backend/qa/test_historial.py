"""Historial de búsquedas: RF-15 (guarda fecha, producto, presupuesto y resultado)."""
from datetime import datetime

import pytest

from ayudas import SIN_SESION, buscar, buscar_ok, consulta_db, usuario_con_sesion
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


def test_cp15_2_sin_sesion_no_se_puede_buscar_ni_se_guarda_nada(client, tv, termino):
    """v3: /buscar exige sesión (antes buscaba sin guardar). Sin sesión: 401 y no se consulta ninguna tienda."""
    antes = consulta_db("SELECT COUNT(*) FROM historial_busquedas")[0][0]
    r = buscar(client, termino, PRESUPUESTO, SIN_SESION)
    assert r.status_code == 401
    assert tv.llamadas == [], "Sin sesión no debe llegar ninguna consulta a las tiendas"
    assert consulta_db("SELECT COUNT(*) FROM historial_busquedas")[0][0] == antes


def test_cp15_2b_token_invalido_da_401_y_no_guarda(client, tv, termino):
    antes = consulta_db("SELECT COUNT(*) FROM historial_busquedas")[0][0]
    r = buscar(client, termino, PRESUPUESTO, {"Authorization": "Bearer token-falso"})
    assert r.status_code == 401
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


# ----------------------------------------------------------------------------- v3: paginación
def _llenar(client, tv, cab, n):
    """Crea n búsquedas distintas con presupuestos distintos (así la regla anti-duplicados no las junta)."""
    for i in range(n):
        buscar_ok(client, f"qa pag {i:02d}", PRESUPUESTO + i, cab)


def test_cp15_6_la_cabecera_x_total_count_informa_el_total(client, tv):
    _, cab = usuario_con_sesion(client)
    _llenar(client, tv, cab, 5)
    r = client.get("/historial", headers=cab)
    assert r.status_code == 200 and r.headers["X-Total-Count"] == "5" and len(r.json()) == 5


def test_cp15_6b_paginas_sin_repetir_ni_perder_busquedas_y_mas_reciente_primero(client, tv):
    _, cab = usuario_con_sesion(client)
    _llenar(client, tv, cab, 5)
    p1 = client.get("/historial", params={"pagina": 1, "limite": 2}, headers=cab).json()
    p2 = client.get("/historial", params={"pagina": 2, "limite": 2}, headers=cab).json()
    p3 = client.get("/historial", params={"pagina": 3, "limite": 2}, headers=cab).json()
    p4 = client.get("/historial", params={"pagina": 4, "limite": 2}, headers=cab).json()
    assert [len(p) for p in (p1, p2, p3, p4)] == [2, 2, 1, 0]
    terminos = [f["termino"] for f in p1 + p2 + p3]
    assert terminos == [f"qa pag {i:02d}" for i in (4, 3, 2, 1, 0)]


@pytest.mark.parametrize("params", [{"pagina": 0}, {"pagina": -1}, {"limite": 0}, {"limite": 101}, {"pagina": "x"}])
def test_cp15_6c_paginacion_con_valores_invalidos_da_422(client, params):
    _, cab = usuario_con_sesion(client)
    assert client.get("/historial", params=params, headers=cab).status_code == 422


def test_cp15_6d_el_total_solo_cuenta_las_busquedas_del_propio_usuario(client, tv):
    _, a = usuario_con_sesion(client)
    _, b = usuario_con_sesion(client)
    _llenar(client, tv, a, 3)
    assert client.get("/historial", headers=b).headers["X-Total-Count"] == "0"
    assert client.get("/historial", headers=a).headers["X-Total-Count"] == "3"


def test_cp15_6e_el_limite_por_defecto_es_20(client, tv):
    _, cab = usuario_con_sesion(client)
    _llenar(client, tv, cab, 22)
    r = client.get("/historial", headers=cab)
    assert len(r.json()) == 20 and r.headers["X-Total-Count"] == "22"
