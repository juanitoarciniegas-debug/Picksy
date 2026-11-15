"""
RECUPERAR LA CONTRASEÑA (RF-20, PROPUESTO por QA). Nuevo en la v3.

Flujo: POST /auth/recuperar {correo} -> correo con enlace (30 min) -> POST /auth/recuperar/restablecer
{token, contrasena_nueva, codigo}. Como el 2FA es obligatorio, también se pide un código del Authenticator
(o uno de recuperación): quien solo tiene el correo no puede apoderarse de la cuenta.

El correo real no se envía en las pruebas: se intercepta recuperacion.enviar_correo para leer el enlace.
"""
import re

import pytest

import recuperacion
from ayudas import (CLAVE_OK, cab, codigo_incorrecto, codigo_totp, consulta_db, correo_nuevo, crear_cuenta,
                    cuenta_con_sesion, iniciar_sesion, liberar_paso, login_paso1)

pytestmark = pytest.mark.req("RF-20")
NUEVA = "OtraClave9999"


@pytest.fixture
def correos(monkeypatch):
    """Captura los 'correos enviados': lista de (destino, enlace)."""
    enviados = []
    monkeypatch.setattr(recuperacion, "enviar_correo", lambda destino, enlace: enviados.append((destino, enlace)))
    return enviados


def _pedir(client, correo):
    return client.post("/auth/recuperar", json={"correo": correo})


def _token(correos):
    return re.search(r"token=([\w\-]+)", correos[-1][1]).group(1)


def _restablecer(client, token, clave=NUEVA, codigo="000000"):
    return client.post("/auth/recuperar/restablecer", json={"token": token, "contrasena_nueva": clave, "codigo": codigo})


def test_cp20_10_la_respuesta_es_identica_exista_o_no_el_correo(client, correos):
    """Anti enumeración de usuarios: no se puede averiguar quién tiene cuenta."""
    c = crear_cuenta(client)
    existe, no_existe = _pedir(client, c.correo), _pedir(client, correo_nuevo())
    assert existe.status_code == no_existe.status_code == 202
    assert existe.json() == no_existe.json()
    assert [d for d, _ in correos] == [c.correo], "Solo la cuenta real recibe correo"


def test_cp20_11_el_enlace_apunta_al_frontend_y_lleva_un_token(client, correos):
    c = crear_cuenta(client)
    _pedir(client, c.correo)
    assert re.fullmatch(r".+/restablecer\.html\?token=[\w\-]{20,}", correos[0][1])


def test_cp20_12_el_token_se_guarda_como_hash(client, correos):
    c = crear_cuenta(client)
    _pedir(client, c.correo)
    token = _token(correos)
    guardados = [f[0] for f in consulta_db("SELECT token_hash FROM recuperaciones_clave")]
    assert token not in guardados and len(guardados) >= 1 and all(len(g) == 64 for g in guardados)


def test_cp20_13_restablecer_con_el_codigo_de_la_app_cambia_la_contrasena(client, correos):
    c = crear_cuenta(client)
    _pedir(client, c.correo)
    r = _restablecer(client, _token(correos), codigo=codigo_totp(c.secreto))
    assert r.status_code == 200
    assert login_paso1(client, c.correo, c.clave).status_code == 401, "La contraseña vieja ya no sirve"
    assert iniciar_sesion(client, c.correo, NUEVA, c.secreto).status_code == 200


def test_cp20_13b_tambien_sirve_un_codigo_de_recuperacion_y_se_gasta(client, correos):
    c = crear_cuenta(client)
    _pedir(client, c.correo)
    assert _restablecer(client, _token(correos), codigo=c.codigos_recuperacion[0]).status_code == 200
    restantes = consulta_db("SELECT COUNT(*) FROM codigos_recuperacion WHERE usuario_id = (SELECT id FROM usuarios WHERE correo=%s) AND usado_en IS NULL", (c.correo,))
    assert restantes[0][0] == 7


def test_cp20_14_sin_el_codigo_correcto_no_cambia_nada(client, correos):
    """El punto de seguridad: tener solo el correo NO alcanza."""
    c = crear_cuenta(client)
    _pedir(client, c.correo)
    r = _restablecer(client, _token(correos), codigo=codigo_incorrecto(c.secreto))
    assert r.status_code == 400
    assert login_paso1(client, c.correo, c.clave).status_code == 200, "La contraseña original sigue valiendo"


def test_cp20_15_el_enlace_sirve_una_sola_vez(client, correos):
    c = crear_cuenta(client)
    _pedir(client, c.correo)
    token = _token(correos)
    assert _restablecer(client, token, codigo=codigo_totp(c.secreto)).status_code == 200
    liberar_paso(c.correo)
    assert _restablecer(client, token, "TercerClave123", codigo_totp(c.secreto)).status_code == 400


def test_cp20_16_pedir_otro_enlace_anula_el_anterior(client, correos):
    c = crear_cuenta(client)
    _pedir(client, c.correo)
    viejo = _token(correos)
    _pedir(client, c.correo)
    assert _restablecer(client, viejo, codigo=codigo_totp(c.secreto)).status_code == 400
    assert _restablecer(client, _token(correos), codigo=codigo_totp(c.secreto)).status_code == 200


def test_cp20_17_enlace_vencido_o_inventado_da_400(client, correos):
    c = crear_cuenta(client)
    _pedir(client, c.correo)
    consulta_db("UPDATE recuperaciones_clave SET expira_en = NOW() - INTERVAL '1 second' "
                "WHERE usuario_id = (SELECT id FROM usuarios WHERE correo = %s)", (c.correo,))
    assert _restablecer(client, _token(correos), codigo=codigo_totp(c.secreto)).status_code == 400
    assert _restablecer(client, "token-inventado", codigo=codigo_totp(c.secreto)).status_code == 400


def test_cp20_18_al_restablecer_se_cierran_las_sesiones_abiertas(client, correos):
    """Si alguien más tenía la cuenta abierta, deja de tenerla."""
    c = cuenta_con_sesion(client)
    _pedir(client, c.correo)
    liberar_paso(c.correo)
    assert _restablecer(client, _token(correos), codigo=codigo_totp(c.secreto)).status_code == 200
    assert client.get("/auth/me", headers=c.cab).status_code == 401


def test_cp20_19_la_contrasena_nueva_respeta_los_limites(client, correos):
    c = crear_cuenta(client)
    _pedir(client, c.correo)
    token = _token(correos)
    for mala in ("corta", "x" * 51, ""):
        assert _restablecer(client, token, mala, codigo_totp(c.secreto)).status_code == 422
    assert _restablecer(client, token, "x" * 50, codigo_totp(c.secreto)).status_code == 200


def test_cp20_20_correo_invalido_da_422(client, correos):
    assert _pedir(client, "no-es-correo").status_code == 422
    assert correos == []


@pytest.mark.req("RNF-09")
def test_cp20_21_maximo_3_solicitudes_por_hora_por_correo(client, correos):
    c = crear_cuenta(client)
    for _ in range(3):
        assert _pedir(client, c.correo).status_code == 202
    r = _pedir(client, c.correo)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


@pytest.mark.req("RNF-09")
def test_cp20_22_adivinar_codigos_al_restablecer_se_frena_con_429(client, correos):
    c = crear_cuenta(client)
    _pedir(client, c.correo)
    token = _token(correos)
    estados = [_restablecer(client, token, codigo=codigo_incorrecto(c.secreto)).status_code for _ in range(12)]
    assert 429 in estados, f"Nunca se frenó el intento de adivinar el código: {estados}"
    assert estados.index(429) <= 10
