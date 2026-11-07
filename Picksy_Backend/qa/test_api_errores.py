"""
API VERSIONADA, ERRORES UNIFICADOS Y CORS (RNF-10, PROPUESTO por QA; lo pidió el profesor). Nuevo en la v3.

  - La API oficial vive en /api/v1/...; las rutas sin versión siguen funcionando (compatibilidad) pero ocultas de /docs.
  - Todo error responde JSON con la misma forma: {"detail": ..., "error": {"codigo", "mensaje", "detalles"}}.
  - Un error 500 también sale como JSON y con las cabeceras de CORS (si no, el navegador lo muestra como 'sin conexión').
"""
import pytest

import busqueda
from ayudas import SIN_SESION, buscar, cab, correo_nuevo, crear_cuenta, login_paso1, usuario_con_sesion
from main import app

pytestmark = pytest.mark.req("RNF-10")
ORIGEN_OK = "http://127.0.0.1:5500"
ORIGEN_MALO = "http://sitio-malicioso.example"


def _forma_ok(r):
    d = r.json()
    assert set(d) == {"detail", "error"}, d
    assert set(d["error"]) == {"codigo", "mensaje", "detalles"}, d
    assert isinstance(d["error"]["codigo"], str) and d["error"]["codigo"].isupper()
    return d


# ----------------------------------------------------------------------------- versionado
def test_cp21_1_todas_las_rutas_documentadas_viven_bajo_api_v1():
    rutas = [r for r in app.openapi()["paths"] if r not in ("/", )]
    assert rutas and all(r.startswith("/api/v1/") for r in rutas), [r for r in rutas if not r.startswith("/api/v1/")]


def test_cp21_1b_las_rutas_sin_version_siguen_funcionando_pero_no_salen_en_la_documentacion(client):
    assert "/buscar" not in app.openapi()["paths"] and "/auth/login" not in app.openapi()["paths"]
    assert client.post("/auth/login", json={"correo": correo_nuevo(), "contrasena": "x"}).status_code == 401


def test_cp21_2_el_flujo_completo_funciona_igual_por_api_v1(client, tiendas, termino):
    """Registro, login en dos pasos, búsqueda, historial y carrito, todo por /api/v1."""
    from ayudas import codigo_totp
    from mocks import producto
    tiendas.poner("Éxito", producto("Éxito", "TV", 100_000))
    correo = correo_nuevo()
    r1 = client.post("/api/v1/auth/registro", json={"correo": correo, "contrasena": "Prueba1234"})
    assert r1.status_code == 201
    secreto = r1.json()["secreto"]
    r2 = client.post("/api/v1/auth/registro/confirmar", json={"token_registro": r1.json()["token_registro"], "codigo": codigo_totp(secreto)})
    assert r2.status_code == 201
    paso1 = client.post("/api/v1/auth/login", json={"correo": correo, "contrasena": "Prueba1234"}).json()
    sesion = client.post("/api/v1/auth/2fa/login", json={"token_2fa": paso1["token_2fa"], "codigo": codigo_totp(secreto)}).json()
    h = cab(sesion["token"])
    assert client.get("/api/v1/buscar", params={"producto": termino, "presupuesto": 500_000}, headers=h).status_code == 200
    assert len(client.get("/api/v1/historial", headers=h).json()) == 1
    assert client.post("/api/v1/carritos", json={"presupuesto": 1000}, headers=h).status_code == 201
    assert client.get("/api/v1/tiendas", headers=h).status_code == 200


def test_cp21_3_salud_responde_ok_y_no_pide_sesion(client):
    r = client.get("/api/v1/salud")
    assert r.status_code == 200 and r.json() == {"estado": "ok"}


# ----------------------------------------------------------------------------- forma de los errores
@pytest.mark.parametrize("peticion,estado,codigo", [
    (lambda c: c.get("/api/v1/auth/me"), 401, "NO_AUTENTICADO"),
    (lambda c: c.get("/ruta/que/no/existe"), 404, "NO_ENCONTRADO"),
    (lambda c: c.put("/api/v1/auth/me"), 405, "METODO_NO_PERMITIDO"),
    (lambda c: c.post("/api/v1/auth/registro", json={}), 422, "DATOS_INVALIDOS"),
])
def test_cp21_4_todo_error_tiene_la_misma_forma(client, peticion, estado, codigo):
    r = peticion(client)
    assert r.status_code == estado
    assert _forma_ok(r)["error"]["codigo"] == codigo


def test_cp21_4b_403_404_y_409_de_la_logica_de_negocio_tambien(client):
    c = usuario_con_sesion(client)[1]
    assert _forma_ok(client.get("/admin/usuarios", headers=c))["error"]["codigo"] == "PROHIBIDO"
    assert _forma_ok(client.get("/carritos/999999999", headers=c))["error"]["codigo"] == "NO_ENCONTRADO"
    cuenta = crear_cuenta(client)
    dup = client.post("/auth/registro", json={"correo": cuenta.correo, "contrasena": "Prueba1234"})
    assert _forma_ok(dup)["error"]["codigo"] == "CONFLICTO"


def test_cp21_4c_el_429_trae_forma_unificada_y_retry_after(client):
    cuenta = crear_cuenta(client)
    for _ in range(5):
        login_paso1(client, cuenta.correo, "ClaveIncorrecta99")
    r = login_paso1(client, cuenta.correo, "ClaveIncorrecta99")
    assert r.status_code == 429 and _forma_ok(r)["error"]["codigo"] == "DEMASIADOS_INTENTOS"
    assert int(r.headers["Retry-After"]) > 0


def test_cp21_5_el_detail_sigue_siendo_texto_en_errores_de_negocio_y_lista_en_validacion(client):
    """El frontend ya lee 'detail': texto en 401/409/..., lista (estándar de FastAPI) en 422."""
    assert isinstance(client.get("/api/v1/auth/me").json()["detail"], str)
    detalle = client.post("/api/v1/auth/registro", json={"correo": "x"}).json()["detail"]
    assert isinstance(detalle, list) and detalle[0]["loc"]


@pytest.mark.parametrize("cuerpo", ['{"presupuesto": Infinity}', '{"presupuesto": NaN}', '{"presupuesto": -Infinity}'])
def test_cp21_6_nan_e_infinito_en_el_cuerpo_dan_422_y_no_500(client, cuerpo):
    """DEF-07 (hallado por el bot en la v3, corregido): un cuerpo JSON con NaN/Infinity rompía el armado del error de
    validación y la API respondía 500."""
    h = usuario_con_sesion(client)[1]
    r = client.post("/carritos", content=cuerpo, headers={**h, "Content-Type": "application/json"})
    assert r.status_code == 422 and _forma_ok(r)
    r = client.post("/auth/registro", content='{"correo": "a@test.com", "contrasena": NaN}', headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_cp21_7_un_error_inesperado_sale_como_500_en_json_sin_detalles_tecnicos(client, monkeypatch):
    def explota(*a, **k):
        raise RuntimeError("secreto interno: password=12345")
    monkeypatch.setattr(busqueda, "buscar_en_todas", explota)
    h = usuario_con_sesion(client)[1]
    r = client.get("/buscar", params={"producto": "tv", "presupuesto": 1000}, headers=h)
    assert r.status_code == 500
    assert _forma_ok(r)["error"]["codigo"] == "ERROR_INTERNO"
    assert "password" not in r.text and "RuntimeError" not in r.text and "Traceback" not in r.text


# ----------------------------------------------------------------------------- CORS
def test_cp22_1_un_origen_permitido_recibe_las_cabeceras_cors(client):
    r = client.get("/api/v1/salud", headers={"Origin": ORIGEN_OK})
    assert r.headers.get("access-control-allow-origin") == ORIGEN_OK


def test_cp22_2_un_origen_desconocido_no_recibe_permiso(client):
    r = client.get("/api/v1/salud", headers={"Origin": ORIGEN_MALO})
    assert "access-control-allow-origin" not in r.headers


def test_cp22_3_el_preflight_permite_authorization_y_los_metodos_usados(client):
    r = client.options("/api/v1/carritos/1", headers={
        "Origin": ORIGEN_OK, "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "authorization,content-type"})
    assert r.status_code == 200
    metodos = r.headers["access-control-allow-methods"]
    assert all(m in metodos for m in ("GET", "POST", "DELETE", "PATCH"))
    assert "authorization" in r.headers["access-control-allow-headers"].lower()


def test_cp22_4_el_navegador_puede_leer_x_total_count_y_retry_after(client):
    r = client.get("/api/v1/salud", headers={"Origin": ORIGEN_OK})
    expuestas = r.headers.get("access-control-expose-headers", "").lower()
    assert "x-total-count" in expuestas and "retry-after" in expuestas


def test_cp22_5_hasta_el_error_500_lleva_cors_para_que_el_navegador_lo_pueda_leer(client, monkeypatch):
    monkeypatch.setattr(busqueda, "buscar_en_todas", lambda *a, **k: 1 / 0)
    h = usuario_con_sesion(client)[1]
    r = client.get("/buscar", params={"producto": "tv", "presupuesto": 1000}, headers={**h, "Origin": ORIGEN_OK})
    assert r.status_code == 500 and r.headers.get("access-control-allow-origin") == ORIGEN_OK
