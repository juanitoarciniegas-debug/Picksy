"""
RNF-02 (consultas parametrizadas) y seguridad básica (Q-05): textos de inyección SQL/XSS en todas
las entradas. Se verifica que nunca haya error 500, que no se filtre información técnica y que la
base de datos quede intacta.
"""
import time

import pytest

from ayudas import buscar, consulta_db, correo_nuevo, iniciar_sesion, registrar
from mocks import producto

pytestmark = pytest.mark.req("RNF-02")

PAYLOADS = [
    "'; DROP TABLE usuarios;--",
    "' OR '1'='1",
    "1; SELECT pg_sleep(5)--",
    "\" OR \"\"=\"",
    "<script>alert(1)</script>",
    "ñandú 🚀 \u0000".replace("\u0000", ""),
    "%' UNION SELECT contrasena_hash FROM usuarios--",
]
# (no se busca "SELECT": la API devuelve el texto buscado, y el payload mismo lo contiene)
PISTAS_TECNICAS = ("Traceback", "psycopg2", "sqlalchemy", "File \"", "site-packages")


def _sin_pistas(texto):
    return not any(p in texto for p in PISTAS_TECNICAS)


@pytest.mark.parametrize("payload", PAYLOADS)
def test_rnf02_2_inyeccion_en_el_producto_no_rompe_ni_filtra(client, tiendas, payload):
    tiendas.poner("Éxito", producto("Éxito", "TV", 100_000))
    usuarios_antes = consulta_db("SELECT COUNT(*) FROM usuarios")[0][0]
    inicio = time.perf_counter()
    r = buscar(client, "qa " + payload, 500_000)
    assert r.status_code in (200, 422), f"{r.status_code}: {r.text[:120]}"
    assert time.perf_counter() - inicio < 4, "Posible inyección con pg_sleep"
    assert _sin_pistas(r.text)
    assert consulta_db("SELECT COUNT(*) FROM usuarios")[0][0] >= usuarios_antes   # la tabla existe y no se vació


@pytest.mark.parametrize("payload", PAYLOADS)
def test_rnf02_2b_inyeccion_en_el_correo_se_rechaza(client, payload):
    assert registrar(client, payload).status_code == 422
    assert iniciar_sesion(client, payload).status_code == 422


@pytest.mark.parametrize("payload", PAYLOADS)
def test_rnf02_2c_inyeccion_en_la_contrasena_no_da_acceso(client, payload):
    correo = correo_nuevo()
    registrar(client, correo)
    r = iniciar_sesion(client, correo, payload)
    assert r.status_code == 401 and "token" not in r.json()


@pytest.mark.parametrize("payload", [p for p in PAYLOADS if p.isascii()])   # un encabezado HTTP solo admite ASCII
def test_rnf02_2d_inyeccion_en_tiendas_y_en_el_token_no_da_error_500(client, tiendas, payload):
    assert buscar(client, "qa tv", 500_000, tiendas=payload).status_code == 400
    r = client.get("/auth/me", headers={"Authorization": "Bearer " + payload})
    assert r.status_code in (401, 422) and _sin_pistas(r.text)


def test_rnf02_2e_los_errores_de_validacion_no_muestran_detalles_internos(client):
    r = buscar(client, "x", "abc")
    assert r.status_code == 422 and _sin_pistas(r.text)
