"""
Autenticación (VERSIÓN 3): RF-01 (registro), RF-02 (login/logout), RF-03 (sesión) y RNF-02 (hash y secretos).

Qué cambió respecto a la v2:
  - El registro es en DOS pasos: POST /auth/registro (guarda un registro pendiente y entrega el QR) y
    POST /auth/registro/confirmar (con el código del Authenticator se crea la cuenta de verdad).
  - El login es en DOS pasos: contraseña -> token_2fa -> código de 6 dígitos -> sesión. La contraseña sola NUNCA da sesión.
  - La sesión dura SESION_HORAS (2 h por defecto), ya no 24 h.
  - Hay límite de intentos (429).

Los resultados esperados salen del ERS y de los criterios de aceptación; los códigos HTTP exactos salen del contrato.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest

from ayudas import (CLAVE_OK, Cuenta, cab, codigo_incorrecto, codigo_totp, confirmar_registro,
                    consulta_db, correo_nuevo, crear_cuenta, cuenta_con_sesion, iniciar_sesion,
                    liberar_paso, login_paso1, login_paso2, registrar, usuario_con_sesion)

pytestmark = pytest.mark.req("RF-01")


# ----------------------------------------------------------------------------- RF-01 (paso 1)
def test_cp01_1_registro_valido_entrega_qr_y_todavia_no_crea_la_cuenta(client):
    correo = correo_nuevo()
    r = registrar(client, correo)
    assert r.status_code == 201
    d = r.json()
    assert d["token_registro"] and d["secreto"] and d["uri"].startswith("otpauth://totp/")
    assert d["qr"].startswith("data:image/svg+xml;base64,")
    assert CLAVE_OK not in r.text, "La respuesta no debe devolver la contraseña"
    assert not consulta_db("SELECT 1 FROM usuarios WHERE correo=%s", (correo,)), \
        "La cuenta NO debe existir hasta confirmar el código del Authenticator"
    assert consulta_db("SELECT 1 FROM registros_pendientes WHERE correo=%s", (correo,))


def test_cp01_1b_confirmar_con_el_codigo_correcto_crea_la_cuenta_y_entrega_8_codigos_de_recuperacion(client):
    correo = correo_nuevo()
    d = registrar(client, correo).json()
    r = confirmar_registro(client, d["token_registro"], codigo_totp(d["secreto"]))
    assert r.status_code == 201
    codigos = r.json()["codigos_recuperacion"]
    assert len(codigos) == 8 and len(set(codigos)) == 8
    assert consulta_db("SELECT rol, totp_activo FROM usuarios WHERE correo=%s", (correo,)) == [("usuario", True)]
    assert not consulta_db("SELECT 1 FROM registros_pendientes WHERE correo=%s", (correo,)), "El pendiente se limpia"


def test_cp01_1c_el_token_de_registro_sirve_una_sola_vez(client):
    d = registrar(client, correo_nuevo()).json()
    codigo = codigo_totp(d["secreto"])
    assert confirmar_registro(client, d["token_registro"], codigo).status_code == 201
    assert confirmar_registro(client, d["token_registro"], codigo).status_code == 400


def test_cp01_1d_codigo_incorrecto_no_crea_la_cuenta_y_descuenta_intentos(client):
    correo = correo_nuevo()
    d = registrar(client, correo).json()
    r = confirmar_registro(client, d["token_registro"], codigo_incorrecto(d["secreto"]))
    assert r.status_code == 400 and "4 intentos" in r.json()["detail"]
    assert not consulta_db("SELECT 1 FROM usuarios WHERE correo=%s", (correo,))


def test_cp01_1e_cinco_codigos_malos_anulan_el_registro_aunque_luego_acierte(client):
    correo = correo_nuevo()
    d = registrar(client, correo).json()
    for _ in range(5):
        r = confirmar_registro(client, d["token_registro"], codigo_incorrecto(d["secreto"]))
        assert r.status_code == 400
    assert "intentos" in r.json()["detail"].lower()
    assert confirmar_registro(client, d["token_registro"], codigo_totp(d["secreto"])).status_code == 400
    assert not consulta_db("SELECT 1 FROM usuarios WHERE correo=%s", (correo,))


def test_cp01_1f_registro_vencido_o_inventado_se_rechaza(client):
    d = registrar(client, correo_nuevo()).json()
    consulta_db("UPDATE registros_pendientes SET expira_en = NOW() - INTERVAL '1 second' WHERE token = %s",
                (d["token_registro"],))
    assert confirmar_registro(client, d["token_registro"], codigo_totp(d["secreto"])).status_code == 400
    assert confirmar_registro(client, "token-que-no-existe", "123456").status_code == 400


def test_cp01_1g_volver_a_registrarse_antes_de_confirmar_reemplaza_el_intento_anterior(client):
    correo = correo_nuevo()
    primero = registrar(client, correo).json()
    segundo = registrar(client, correo).json()
    assert primero["secreto"] != segundo["secreto"]
    assert confirmar_registro(client, primero["token_registro"], codigo_totp(primero["secreto"])).status_code == 400
    assert confirmar_registro(client, segundo["token_registro"], codigo_totp(segundo["secreto"])).status_code == 201


def test_cp01_2_correo_repetido_se_rechaza_con_mensaje_claro(client):
    cuenta = crear_cuenta(client)
    r = registrar(client, cuenta.correo)
    assert r.status_code == 409
    assert "correo" in r.json()["detail"].lower()
    assert consulta_db("SELECT COUNT(*) FROM usuarios WHERE correo=%s", (cuenta.correo,))[0][0] == 1


def test_cp01_2b_correo_repetido_con_otras_mayusculas(client):
    cuenta = crear_cuenta(client)
    assert registrar(client, cuenta.correo.upper().replace("@TEST.COM", "@test.com")).status_code == 409


@pytest.mark.parametrize("correo", ["abc", "abc@", "@test.com", "sin arroba.com", ""])
def test_cp01_3_correo_invalido(client, correo):
    assert registrar(client, correo).status_code == 422


@pytest.mark.parametrize("clave,esperado", [
    ("1234567", 422),        # 7 caracteres: límite inferior inválido
    ("12345678", 201),       # 8 caracteres: límite inferior válido
    ("x" * 50, 201),         # 50: límite superior válido
    ("x" * 51, 422),         # 51: la API rechaza (OBS: el ERS no define máximo)
])
def test_cp01_4_limites_de_la_contrasena(client, clave, esperado):
    assert registrar(client, correo_nuevo(), clave).status_code == esperado


@pytest.mark.req("RNF-09")
def test_cp01_5_limite_de_registros_por_hora_responde_429_con_retry_after(client):
    """Anti-abuso: máximo 10 registros por hora desde la misma conexión."""
    for _ in range(10):
        assert registrar(client, correo_nuevo()).status_code == 201
    r = registrar(client, correo_nuevo())
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


# ----------------------------------------------------------------------------- RF-02
@pytest.mark.req("RF-02")
def test_cp02_1_la_contrasena_sola_no_da_sesion_pide_el_codigo(client):
    cuenta = crear_cuenta(client)
    d = login_paso1(client, cuenta.correo).json()
    assert d["requiere_2fa"] is True and d["token_2fa"]
    assert "token" not in d, "La contrasena sola NO debe entregar una sesión"
    assert datetime.fromisoformat(d["expira_en"]) > datetime.now(timezone.utc)


@pytest.mark.req("RF-02")
def test_cp02_1b_login_completo_devuelve_token_con_expiracion(client):
    cuenta = crear_cuenta(client)
    r = iniciar_sesion(client, cuenta.correo, cuenta.clave, cuenta.secreto)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["token"] and cuerpo["tipo"] == "Bearer"
    assert datetime.fromisoformat(cuerpo["expira_en"]) > datetime.now(timezone.utc)


@pytest.mark.req("RF-02")
def test_cp02_2_error_no_revela_que_dato_fallo(client):
    """Criterio de aceptación: contraseña mala y correo inexistente dan EXACTAMENTE el mismo error."""
    cuenta = crear_cuenta(client)
    mala_clave = iniciar_sesion(client, cuenta.correo, "ClaveIncorrecta99")
    sin_cuenta = iniciar_sesion(client, correo_nuevo())
    assert mala_clave.status_code == sin_cuenta.status_code == 401
    assert mala_clave.json() == sin_cuenta.json()
    assert "token" not in mala_clave.json() and "token_2fa" not in mala_clave.json()


@pytest.mark.req("RF-02")
def test_cp02_3_login_con_cuenta_antigua_sin_authenticator_pide_configurarlo(client):
    """Cuentas creadas en la v1/v2 (sin Authenticator): en su primer login v3 lo configuran y entran en el mismo paso."""
    c = crear_cuenta(client)
    consulta_db("UPDATE usuarios SET totp_activo = FALSE, totp_secreto = NULL WHERE correo = %s", (c.correo,))
    d = login_paso1(client, c.correo, c.clave).json()
    assert d["requiere_configuracion_2fa"] is True and d["token_2fa"] and "token" not in d
    cfg = client.post("/auth/2fa/pendiente/configurar", json={"token_2fa": d["token_2fa"]})
    assert cfg.status_code == 200 and cfg.json()["qr"].startswith("data:image/svg+xml;base64,")
    secreto = cfg.json()["secreto"]
    ok = client.post("/auth/2fa/pendiente/activar", json={"token_2fa": d["token_2fa"], "codigo": codigo_totp(secreto)})
    assert ok.status_code == 200
    assert ok.json()["token"] and len(ok.json()["codigos_recuperacion"]) == 8
    assert client.get("/auth/me", headers=cab(ok.json()["token"])).status_code == 200
    assert consulta_db("SELECT totp_activo FROM usuarios WHERE correo=%s", (c.correo,))[0][0] is True


@pytest.mark.req("RF-02")
def test_cp02_3b_cuenta_antigua_codigo_incorrecto_no_activa_el_2fa_ni_da_sesion(client):
    c = crear_cuenta(client)
    consulta_db("UPDATE usuarios SET totp_activo = FALSE, totp_secreto = NULL WHERE correo = %s", (c.correo,))
    d = login_paso1(client, c.correo, c.clave).json()
    secreto = client.post("/auth/2fa/pendiente/configurar", json={"token_2fa": d["token_2fa"]}).json()["secreto"]
    r = client.post("/auth/2fa/pendiente/activar", json={"token_2fa": d["token_2fa"], "codigo": codigo_incorrecto(secreto)})
    assert r.status_code == 401 and "token" not in r.json()
    assert consulta_db("SELECT totp_activo FROM usuarios WHERE correo=%s", (c.correo,))[0][0] is False


@pytest.mark.req("RF-02")
def test_cp02_3c_activar_sin_generar_el_qr_primero_se_rechaza(client):
    c = crear_cuenta(client)
    consulta_db("UPDATE usuarios SET totp_activo = FALSE, totp_secreto = NULL WHERE correo = %s", (c.correo,))
    d = login_paso1(client, c.correo, c.clave).json()
    r = client.post("/auth/2fa/pendiente/activar", json={"token_2fa": d["token_2fa"], "codigo": "123456"})
    assert r.status_code == 401


@pytest.mark.req("RF-02")
def test_cp02_3d_cuenta_con_authenticator_no_puede_regenerar_su_secreto_por_la_ruta_de_cuentas_antiguas(client):
    """Si no, quien solo conoce la contraseña podría cambiar el secreto y saltarse el 2FA."""
    c = crear_cuenta(client)
    d = login_paso1(client, c.correo, c.clave).json()
    r = client.post("/auth/2fa/pendiente/configurar", json={"token_2fa": d["token_2fa"]})
    assert r.status_code == 409


@pytest.mark.req("RF-02")
def test_cp02_4_cerrar_sesion_invalida_el_token(client):
    _, h = usuario_con_sesion(client)
    assert client.get("/auth/me", headers=h).status_code == 200
    assert client.post("/auth/logout", headers=h).status_code == 200
    # Criterio de aceptación: tras cerrar sesión no se accede a datos privados
    assert client.get("/auth/me", headers=h).status_code == 401
    assert client.get("/historial", headers=h).status_code == 401
    assert client.get("/buscar", params={"producto": "tv", "presupuesto": 1000}, headers=h).status_code == 401


@pytest.mark.req("RF-02")
@pytest.mark.parametrize("ruta,metodo", [
    ("/auth/me", "get"), ("/auth/logout", "post"), ("/historial", "get"), ("/historial", "delete"),
    ("/buscar?producto=tv&presupuesto=1000", "get"), ("/tiendas", "get"),     # v3: buscar exige sesión
    ("/carritos", "get"), ("/carritos", "post"), ("/carritos/comparar?a=1&b=2", "get"),
    ("/productos/precios?url=https://qa.test/x", "get"),
    ("/admin/usuarios", "get"),
])
def test_cp02_5_rutas_privadas_sin_token_dan_401(client, ruta, metodo):
    assert getattr(client, metodo)(ruta).status_code == 401


@pytest.mark.req("RF-02")
def test_cp02_5b_token_inventado_da_401(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer token-que-no-existe"})
    assert r.status_code == 401


@pytest.mark.req("RF-02")
def test_cp02_6_la_ruta_publica_de_inicio_y_la_documentacion_siguen_abiertas(client):
    assert client.get("/").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/api/v1/salud").json() == {"estado": "ok"}


@pytest.mark.req("RF-02")
@pytest.mark.req("RNF-09")
def test_cp02_7_cinco_contrasenas_malas_bloquean_al_correo_con_429(client):
    """Anti fuerza bruta: tras LOGIN_MAX_FALLOS (5) fallos, ni la contraseña correcta entra hasta que pase la ventana."""
    c = crear_cuenta(client)
    for _ in range(5):
        assert login_paso1(client, c.correo, "ClaveIncorrecta99").status_code == 401
    r = login_paso1(client, c.correo, c.clave)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    assert "token" not in r.json() and "token_2fa" not in r.json()


@pytest.mark.req("RF-02")
@pytest.mark.req("RNF-09")
def test_cp02_7b_el_bloqueo_de_un_correo_no_afecta_a_otro(client):
    a, b = crear_cuenta(client), crear_cuenta(client)
    for _ in range(5):
        login_paso1(client, a.correo, "ClaveIncorrecta99")
    assert login_paso1(client, a.correo, a.clave).status_code == 429
    assert login_paso1(client, b.correo, b.clave).status_code == 200


@pytest.mark.req("RF-02")
def test_cp02_7c_un_login_correcto_borra_el_conteo_de_fallos(client):
    c = crear_cuenta(client)
    for _ in range(4):
        login_paso1(client, c.correo, "ClaveIncorrecta99")
    assert login_paso1(client, c.correo, c.clave).status_code == 200
    for _ in range(4):
        assert login_paso1(client, c.correo, "ClaveIncorrecta99").status_code == 401


# ----------------------------------------------------------------------------- RF-03
@pytest.mark.req("RF-03")
def test_cp03_1_sesion_vigente_da_acceso_y_muestra_rol(client):
    correo, h = usuario_con_sesion(client)
    r = client.get("/auth/me", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["correo"] == correo and d["rol"] == "usuario" and d["dos_factores"] is True


@pytest.mark.req("RF-03")
def test_cp03_1b_la_sesion_dura_lo_configurado_en_SESION_HORAS(client):
    """A-04/ERS: 'persiste durante el tiempo definido'. La v3 la define en el .env (SESION_HORAS, 2 h por defecto)
    y el profesor pidió tokens de corta duración: nunca más de 24 h."""
    horas_config = float(os.getenv("SESION_HORAS", "2"))
    c = crear_cuenta(client)
    expira = datetime.fromisoformat(iniciar_sesion(client, c.correo, c.clave, c.secreto).json()["expira_en"])
    horas = (expira - datetime.now(timezone.utc)) / timedelta(hours=1)
    assert horas_config - 0.1 < horas <= horas_config
    assert horas <= 24


@pytest.mark.req("RF-03")
def test_cp03_2_sesion_vencida_se_rechaza_de_forma_controlada(client):
    _, h = usuario_con_sesion(client)
    token = h["Authorization"].split()[1]
    # Se fuerza el vencimiento en la base de PRUEBA (no hay que esperar horas)
    consulta_db("UPDATE sesiones SET expira_en = NOW() - INTERVAL '1 second' WHERE token = %s", (token,))
    r = client.get("/auth/me", headers=h)
    assert r.status_code == 401
    assert "expirada" in r.json()["detail"].lower() or "inválida" in r.json()["detail"].lower()


@pytest.mark.req("RF-03")
def test_cp03_3_iniciar_sesion_dos_veces_da_dos_sesiones_independientes(client):
    c = crear_cuenta(client)
    t1 = iniciar_sesion(client, c.correo, c.clave, c.secreto).json()["token"]
    t2 = iniciar_sesion(client, c.correo, c.clave, c.secreto).json()["token"]
    assert t1 != t2
    client.post("/auth/logout", headers=cab(t1))
    assert client.get("/auth/me", headers=cab(t1)).status_code == 401
    assert client.get("/auth/me", headers=cab(t2)).status_code == 200


# ----------------------------------------------------------------------------- RNF-02
@pytest.mark.req("RNF-02")
def test_rnf02_1_contrasena_guardada_como_hash_bcrypt(client):
    c = crear_cuenta(client)
    guardado = consulta_db("SELECT contrasena_hash FROM usuarios WHERE correo=%s", (c.correo,))[0][0]
    assert guardado != CLAVE_OK
    assert guardado.startswith("$2b$"), "Debe ser bcrypt"


@pytest.mark.req("RNF-02")
def test_rnf02_1a_tampoco_se_guarda_en_claro_mientras_el_registro_esta_pendiente(client):
    correo = correo_nuevo()
    registrar(client, correo)
    guardado = consulta_db("SELECT contrasena_hash FROM registros_pendientes WHERE correo=%s", (correo,))[0][0]
    assert guardado.startswith("$2b$") and CLAVE_OK not in guardado


@pytest.mark.req("RNF-02")
def test_rnf02_1b_dos_usuarios_con_la_misma_clave_tienen_hash_distinto(client):
    """Prueba que bcrypt usa 'sal' aleatoria: no se puede comparar hashes para adivinar claves."""
    a, b = crear_cuenta(client), crear_cuenta(client)
    hashes = [consulta_db("SELECT contrasena_hash FROM usuarios WHERE correo=%s", (c.correo,))[0][0] for c in (a, b)]
    assert hashes[0] != hashes[1]


@pytest.mark.req("RNF-02")
def test_rnf02_1c_las_respuestas_nunca_exponen_el_hash(client):
    c = crear_cuenta(client)
    textos = [login_paso1(client, c.correo).text]
    sesion = iniciar_sesion(client, c.correo, c.clave, c.secreto)
    textos += [sesion.text, client.get("/auth/me", headers=cab(sesion.json()["token"])).text]
    for t in textos:
        assert "$2b$" not in t and "hash" not in t.lower()


@pytest.mark.req("RNF-02")
def test_rnf02_1d_el_secreto_del_authenticator_se_guarda_cifrado(client):
    """Si alguien copia la base de datos no puede generar los códigos de los usuarios."""
    if not os.getenv("TOTP_CLAVE"):
        pytest.skip("OMITIDA: este entorno no tiene TOTP_CLAVE (el secreto queda sin cifrar por diseño)")
    c = crear_cuenta(client)
    guardado = consulta_db("SELECT totp_secreto FROM usuarios WHERE correo=%s", (c.correo,))[0][0]
    assert guardado != c.secreto and c.secreto not in guardado
    assert guardado.startswith("gAAAA"), "Debe ser un token Fernet"


@pytest.mark.req("RNF-02")
def test_rnf02_1e_los_codigos_de_recuperacion_se_guardan_como_hash(client):
    c = crear_cuenta(client)
    guardados = [f[0] for f in consulta_db(
        "SELECT codigo_hash FROM codigos_recuperacion WHERE usuario_id = (SELECT id FROM usuarios WHERE correo=%s)",
        (c.correo,))]
    assert len(guardados) == 8
    for original in c.codigos_recuperacion:
        assert original not in guardados and original.replace("-", "") not in guardados
        assert all(len(g) == 64 for g in guardados), "sha256 en hexadecimal"
