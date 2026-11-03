"""
Verificación en dos pasos (2FA con TOTP) - llegó en la v2 SIN ID de requisito en el ERS.
QA la prueba como RF-18 PROPUESTO (ver requisitos.yml) porque es seguridad: un fallo aquí
puede dejar entrar a quien no debe, o dejar a un usuario fuera de su cuenta.

Se omite sola si la API no tiene 2FA (v1). Los códigos se calculan con pyotp igual que la app del celular.
"""
import time

import pytest

pyotp = pytest.importorskip("pyotp", reason="OMITIDA: pyotp no está instalado")

from main import app  # noqa: E402

from ayudas import (CLAVE_OK, consulta_db, correo_nuevo, iniciar_sesion, registrar,  # noqa: E402
                    usuario_con_sesion)

pytestmark = [
    pytest.mark.req("RF-18"),
    pytest.mark.skipif("/auth/2fa/configurar" not in app.openapi()["paths"],
                       reason="OMITIDA: esta versión de la API no tiene 2FA"),
]

PASO = 30


def _cab(token):
    return {"Authorization": f"Bearer {token}"}


def _codigo(secreto, desplazamiento=0):
    """Código de la app en el paso actual (+N pasos de 30 s)."""
    return pyotp.TOTP(secreto, interval=PASO).at(time.time() + desplazamiento * PASO)


def _codigo_incorrecto(secreto):
    validos = {_codigo(secreto, d) for d in range(-3, 4)}
    return next(c for c in ("000000", "111111", "222222", "333333") if c not in validos)


def _liberar_paso(correo):
    """La API rechaza reutilizar un paso de 30 s. Para encadenar varias pruebas se reinicia el contador."""
    consulta_db("UPDATE usuarios SET totp_ultimo_paso = 0 WHERE correo = %s", (correo,))


@pytest.fixture
def usuario_2fa(client):
    """Usuario con 2FA YA ACTIVADO. Devuelve (correo, secreto, token_de_sesion)."""
    correo, cab = usuario_con_sesion(client)
    r = client.post("/auth/2fa/configurar", headers=cab)
    assert r.status_code == 200, r.text
    secreto = r.json()["secreto"]
    r = client.post("/auth/2fa/activar", json={"codigo": _codigo(secreto)}, headers=cab)
    assert r.status_code == 200, r.text
    _liberar_paso(correo)
    return correo, secreto, cab["Authorization"].split()[1]


def _login_paso1(client, correo, clave=CLAVE_OK):
    return iniciar_sesion(client, correo, clave)


# ----------------------------------------------------------------------------- configurar y activar
def test_cp18_1_configurar_entrega_secreto_uri_y_qr(client):
    _, cab = usuario_con_sesion(client)
    r = client.post("/auth/2fa/configurar", headers=cab)
    assert r.status_code == 200
    d = r.json()
    assert d["secreto"] and d["uri"].startswith("otpauth://totp/") and "Picksy" in d["uri"]
    assert d["qr"].startswith("data:image/svg+xml;base64,")


def test_cp18_2_activar_con_codigo_correcto(client):
    correo, cab = usuario_con_sesion(client)
    secreto = client.post("/auth/2fa/configurar", headers=cab).json()["secreto"]
    assert client.post("/auth/2fa/activar", json={"codigo": _codigo(secreto)}, headers=cab).status_code == 200
    assert client.get("/auth/me", headers=cab).json()["dos_factores"] is True


def test_cp18_2b_activar_con_codigo_incorrecto_no_activa(client):
    _, cab = usuario_con_sesion(client)
    secreto = client.post("/auth/2fa/configurar", headers=cab).json()["secreto"]
    r = client.post("/auth/2fa/activar", json={"codigo": _codigo_incorrecto(secreto)}, headers=cab)
    assert r.status_code == 400
    assert client.get("/auth/me", headers=cab).json()["dos_factores"] is False


def test_cp18_2c_activar_sin_configurar_primero(client):
    _, cab = usuario_con_sesion(client)
    assert client.post("/auth/2fa/activar", json={"codigo": "123456"}, headers=cab).status_code == 400


def test_cp18_2d_no_se_puede_configurar_dos_veces_con_el_2fa_activo(client, usuario_2fa):
    _, _, token = usuario_2fa
    assert client.post("/auth/2fa/configurar", headers=_cab(token)).status_code == 409


@pytest.mark.parametrize("ruta,cuerpo", [
    ("/auth/2fa/configurar", None), ("/auth/2fa/activar", {"codigo": "123456"}),
    ("/auth/2fa/desactivar", {"codigo": "123456", "contrasena": CLAVE_OK}),
])
def test_cp18_3_rutas_privadas_del_2fa_sin_sesion_dan_401(client, ruta, cuerpo):
    assert client.post(ruta, json=cuerpo).status_code == 401


# ----------------------------------------------------------------------------- login en dos pasos
def test_cp18_4_con_2fa_activo_la_contrasena_sola_NO_da_sesion(client, usuario_2fa):
    correo, _, _ = usuario_2fa
    d = _login_paso1(client, correo).json()
    assert d["requiere_2fa"] is True and d["token_2fa"]
    assert "token" not in d, "Con 2FA activo, la contraseña sola no debe entregar una sesión"


def test_cp18_4b_el_token_temporal_no_sirve_como_sesion(client, usuario_2fa):
    correo, _, _ = usuario_2fa
    token_2fa = _login_paso1(client, correo).json()["token_2fa"]
    assert client.get("/auth/me", headers=_cab(token_2fa)).status_code == 401
    assert client.get("/historial", headers=_cab(token_2fa)).status_code == 401


def test_cp18_5_login_completo_con_codigo_correcto(client, usuario_2fa):
    correo, secreto, _ = usuario_2fa
    token_2fa = _login_paso1(client, correo).json()["token_2fa"]
    r = client.post("/auth/2fa/login", json={"token_2fa": token_2fa, "codigo": _codigo(secreto)})
    assert r.status_code == 200
    sesion = r.json()
    assert sesion["token"] and sesion["tipo"] == "Bearer"
    assert client.get("/auth/me", headers=_cab(sesion["token"])).status_code == 200


def test_cp18_5b_el_codigo_acepta_el_espacio_que_muestra_la_app(client, usuario_2fa):
    correo, secreto, _ = usuario_2fa
    token_2fa = _login_paso1(client, correo).json()["token_2fa"]
    c = _codigo(secreto)
    assert client.post("/auth/2fa/login", json={"token_2fa": token_2fa, "codigo": f"{c[:3]} {c[3:]}"}).status_code == 200


def test_cp18_6_codigo_incorrecto_se_rechaza_y_descuenta_intentos(client, usuario_2fa):
    correo, secreto, _ = usuario_2fa
    token_2fa = _login_paso1(client, correo).json()["token_2fa"]
    r = client.post("/auth/2fa/login", json={"token_2fa": token_2fa, "codigo": _codigo_incorrecto(secreto)})
    assert r.status_code == 401 and "4 intentos" in r.json()["detail"]


def test_cp18_6b_codigo_con_letras_o_longitud_mala_se_rechaza(client, usuario_2fa):
    correo, _, _ = usuario_2fa
    token_2fa = _login_paso1(client, correo).json()["token_2fa"]
    for malo in ("abcdef", "12345a", "1234567"):
        assert client.post("/auth/2fa/login", json={"token_2fa": token_2fa, "codigo": malo}).status_code == 401
    assert client.post("/auth/2fa/login", json={"token_2fa": token_2fa, "codigo": "123"}).status_code == 422


def test_cp18_7_cinco_intentos_malos_invalidan_el_inicio_de_sesion_aunque_luego_acierte(client, usuario_2fa):
    correo, secreto, _ = usuario_2fa
    token_2fa = _login_paso1(client, correo).json()["token_2fa"]
    for _ in range(5):
        r = client.post("/auth/2fa/login", json={"token_2fa": token_2fa, "codigo": _codigo_incorrecto(secreto)})
        assert r.status_code == 401
    assert "intentos" in r.json()["detail"].lower()
    r = client.post("/auth/2fa/login", json={"token_2fa": token_2fa, "codigo": _codigo(secreto)})
    assert r.status_code == 401, "Tras 5 fallos, ni el código correcto debe servir con ese token"


def test_cp18_8_el_codigo_no_se_puede_reutilizar(client, usuario_2fa):
    """Un código espiado no sirve una segunda vez (la API recuerda el último paso usado)."""
    correo, secreto, _ = usuario_2fa
    codigo = _codigo(secreto)
    t1 = _login_paso1(client, correo).json()["token_2fa"]
    assert client.post("/auth/2fa/login", json={"token_2fa": t1, "codigo": codigo}).status_code == 200
    t2 = _login_paso1(client, correo).json()["token_2fa"]
    r = client.post("/auth/2fa/login", json={"token_2fa": t2, "codigo": codigo})
    assert r.status_code == 401 and "ya se usó" in r.json()["detail"]


def test_cp18_9_el_token_temporal_es_de_un_solo_uso(client, usuario_2fa):
    correo, secreto, _ = usuario_2fa
    token_2fa = _login_paso1(client, correo).json()["token_2fa"]
    assert client.post("/auth/2fa/login", json={"token_2fa": token_2fa, "codigo": _codigo(secreto)}).status_code == 200
    _liberar_paso(correo)
    assert client.post("/auth/2fa/login", json={"token_2fa": token_2fa, "codigo": _codigo(secreto)}).status_code == 401


def test_cp18_10_token_temporal_vencido_o_inventado(client, usuario_2fa):
    correo, secreto, _ = usuario_2fa
    token_2fa = _login_paso1(client, correo).json()["token_2fa"]
    consulta_db("UPDATE login_pendientes SET expira_en = NOW() - INTERVAL '1 second' WHERE token = %s", (token_2fa,))
    assert client.post("/auth/2fa/login", json={"token_2fa": token_2fa, "codigo": _codigo(secreto)}).status_code == 401
    assert client.post("/auth/2fa/login", json={"token_2fa": "no-existe", "codigo": _codigo(secreto)}).status_code == 401


def test_cp18_11_con_2fa_activo_el_error_de_contrasena_no_revela_nada_distinto(client, usuario_2fa):
    """RF-02: error idéntico para contraseña mala, con o sin 2FA, y para correo inexistente."""
    correo, _, _ = usuario_2fa
    con_2fa = _login_paso1(client, correo, "ClaveIncorrecta99")
    sin_cuenta = _login_paso1(client, correo_nuevo())
    assert con_2fa.status_code == sin_cuenta.status_code == 401
    assert con_2fa.json() == sin_cuenta.json()


def test_cp18_12_la_sesion_ya_abierta_antes_de_activar_sigue_valida(client, usuario_2fa):
    """COMPORTAMIENTO ACTUAL: activar el 2FA no cierra las sesiones que ya estaban abiertas."""
    _, _, token = usuario_2fa
    assert client.get("/auth/me", headers=_cab(token)).status_code == 200


# ----------------------------------------------------------------------------- desactivar
def test_cp18_13_desactivar_exige_contrasena_y_codigo(client, usuario_2fa):
    correo, secreto, token = usuario_2fa
    cab = _cab(token)
    mala = client.post("/auth/2fa/desactivar", json={"codigo": _codigo(secreto), "contrasena": "ClaveIncorrecta99"}, headers=cab)
    assert mala.status_code == 401
    sin_codigo = client.post("/auth/2fa/desactivar", json={"codigo": _codigo_incorrecto(secreto), "contrasena": CLAVE_OK}, headers=cab)
    assert sin_codigo.status_code == 400
    assert client.get("/auth/me", headers=cab).json()["dos_factores"] is True
    ok = client.post("/auth/2fa/desactivar", json={"codigo": _codigo(secreto), "contrasena": CLAVE_OK}, headers=cab)
    assert ok.status_code == 200
    assert client.get("/auth/me", headers=cab).json()["dos_factores"] is False


def test_cp18_13b_tras_desactivar_el_login_vuelve_a_ser_de_un_paso(client, usuario_2fa):
    correo, secreto, token = usuario_2fa
    client.post("/auth/2fa/desactivar", json={"codigo": _codigo(secreto), "contrasena": CLAVE_OK}, headers=_cab(token))
    d = _login_paso1(client, correo).json()
    assert d.get("token") and "requiere_2fa" not in d


def test_cp18_14_el_secreto_nunca_aparece_fuera_de_configurar(client, usuario_2fa):
    correo, secreto, token = usuario_2fa
    textos = [client.get("/auth/me", headers=_cab(token)).text, _login_paso1(client, correo).text,
              client.get("/historial", headers=_cab(token)).text]
    assert all(secreto not in t for t in textos)
