"""
RNF-02 (consultas parametrizadas) y seguridad básica (Q-05): textos de inyección SQL/XSS en todas
las entradas. Se verifica que nunca haya error 500, que no se filtre información técnica y que la
base de datos quede intacta.
"""
import time

import pytest

from ayudas import (buscar, cab, codigo_totp, consulta_db, correo_nuevo, crear_carrito, crear_cuenta,
                    cuenta_con_sesion, iniciar_sesion, login_paso1, registrar)
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
    cuenta = crear_cuenta(client)                     # cuenta REAL: si el login "pasara", sería por la inyección
    r = iniciar_sesion(client, cuenta.correo, payload)
    assert r.status_code in (401, 422) and "token" not in r.json() and "token_2fa" not in r.json()
    assert _sin_pistas(r.text)


@pytest.mark.parametrize("payload", PAYLOADS)
def test_rnf02_2f_inyeccion_en_los_campos_del_2fa_no_da_acceso_ni_error_500(client, payload):
    cuenta = crear_cuenta(client)
    token_2fa = login_paso1(client, cuenta.correo).json()["token_2fa"]
    for cuerpo in ({"token_2fa": payload, "codigo": "123456"}, {"token_2fa": token_2fa, "codigo": payload.ljust(6, "x")}):
        r = client.post("/auth/2fa/login", json=cuerpo)
        assert r.status_code in (401, 422) and "token" not in r.json() and _sin_pistas(r.text)
    assert client.post("/auth/registro/confirmar", json={"token_registro": payload, "codigo": "123456"}).status_code in (400, 422)
    assert client.post("/auth/recuperar/restablecer", json={"token": payload, "contrasena_nueva": "Prueba1234", "codigo": "123456"}).status_code in (400, 422)


@pytest.mark.parametrize("payload", PAYLOADS)
def test_rnf02_2g_inyeccion_en_carritos_se_guarda_como_texto_y_no_rompe_nada(client, payload):
    from ayudas import agregar_item
    c = cuenta_con_sesion(client)
    usuarios_antes = consulta_db("SELECT COUNT(*) FROM usuarios")[0][0]
    carrito = crear_carrito(client, c.cab, 100_000, payload[:100])
    assert carrito["nombre"] is not None or payload.strip() == ""
    r = agregar_item(client, c.cab, carrito["id"], 1000, nombre=payload[:200])
    assert r.status_code == 201 and _sin_pistas(r.text)
    assert client.get(f"/carritos/{carrito['id']}", headers=c.cab).status_code == 200
    assert consulta_db("SELECT COUNT(*) FROM usuarios")[0][0] >= usuarios_antes


@pytest.mark.parametrize("payload", PAYLOADS)
def test_rnf02_2h_inyeccion_en_la_url_de_precios_y_en_las_rutas_no_da_500(client, payload):
    c = cuenta_con_sesion(client)
    for r in (client.get("/productos/precios", params={"url": payload.ljust(10, "x")}, headers=c.cab),
              client.get(f"/carritos/{payload}", headers=c.cab),
              client.get("/historial", params={"pagina": payload}, headers=c.cab)):
        assert r.status_code in (404, 422) and _sin_pistas(r.text)


def test_rnf02_2i_la_base_guarda_las_contrasenas_y_secretos_sin_texto_plano(client):
    """Ningún dato sensible de ninguna cuenta de prueba aparece en claro en ninguna tabla."""
    c = crear_cuenta(client)
    for tabla, col in (("usuarios", "contrasena_hash"), ("usuarios", "totp_secreto"), ("codigos_recuperacion", "codigo_hash")):
        valores = " ".join(str(f[0]) for f in consulta_db(f"SELECT {col} FROM {tabla}") if f[0])
        assert "Prueba1234" not in valores
        assert c.secreto not in valores or not __import__("os").getenv("TOTP_CLAVE")


@pytest.mark.parametrize("payload", [p for p in PAYLOADS if p.isascii()])   # un encabezado HTTP solo admite ASCII
def test_rnf02_2d_inyeccion_en_tiendas_y_en_el_token_no_da_error_500(client, tiendas, payload):
    assert buscar(client, "qa tv", 500_000, tiendas=payload).status_code == 400
    r = client.get("/auth/me", headers={"Authorization": "Bearer " + payload})
    assert r.status_code in (401, 422) and _sin_pistas(r.text)


def test_rnf02_2e_los_errores_de_validacion_no_muestran_detalles_internos(client):
    r = buscar(client, "x", "abc")
    assert r.status_code == 422 and _sin_pistas(r.text)
