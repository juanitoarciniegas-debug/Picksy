"""
Verificación en dos pasos (2FA con TOTP) - VERSIÓN 3: ahora es OBLIGATORIA.
QA la prueba como RF-18 PROPUESTO (ver requisitos.yml; el ERS aún no tiene un ID para ella) y los códigos de
recuperación como RF-20 PROPUESTO. Es seguridad: un fallo aquí puede dejar entrar a quien no debe, o dejar a
un usuario fuera de su cuenta.

Cambios frente a la v2: ya no existe configurar/activar/desactivar con sesión. El Authenticator se configura al
REGISTRARSE (o en el primer login de una cuenta antigua) y no se puede apagar.
Los códigos se calculan con pyotp igual que la app del celular.
"""
import pytest

from ayudas import (CLAVE_OK, cab, codigo_incorrecto, codigo_totp, consulta_db, correo_nuevo,
                    crear_cuenta, cuenta_con_sesion, iniciar_sesion, liberar_paso, login_paso1, login_paso2)

pytestmark = pytest.mark.req("RF-18")


@pytest.fixture
def cuenta(client):
    """Cuenta con el 2FA activo (como queda toda cuenta nueva en la v3), SIN sesión abierta."""
    return crear_cuenta(client)


# ----------------------------------------------------------------------------- el 2FA es obligatorio
def test_cp18_1_las_rutas_de_la_v2_para_apagar_o_configurar_el_2fa_con_sesion_ya_no_existen(client):
    """La v3 elimina 'desactivar': nadie puede entrar sin el código. Si alguien las vuelve a agregar, esta prueba avisa."""
    c = cuenta_con_sesion(client)
    for ruta in ("/auth/2fa/configurar", "/auth/2fa/activar", "/auth/2fa/desactivar"):
        r = client.post(ruta, json={"codigo": "123456", "contrasena": CLAVE_OK}, headers=c.cab)
        assert r.status_code in (404, 405), f"{ruta} respondió {r.status_code}: el 2FA no debe poder apagarse"
    assert client.get("/auth/me", headers=c.cab).json()["dos_factores"] is True


def test_cp18_2_la_cuenta_nueva_queda_con_el_2fa_activo_y_el_secreto_no_vuelve_a_mostrarse(client):
    c = crear_cuenta(client)
    assert consulta_db("SELECT totp_activo FROM usuarios WHERE correo=%s", (c.correo,))[0][0] is True
    sesion = iniciar_sesion(client, c.correo, c.clave, c.secreto)
    h = cab(sesion.json()["token"])
    textos = [login_paso1(client, c.correo).text, sesion.text, client.get("/auth/me", headers=h).text,
              client.get("/historial", headers=h).text]
    assert all(c.secreto not in t for t in textos)


def test_cp18_2b_el_codigo_del_registro_sirve_para_el_primer_login(client):
    """Diseño documentado en auth.py: totp_ultimo_paso queda en 0 al crear la cuenta para no hacer esperar 30 s."""
    correo = correo_nuevo()
    d = client.post("/auth/registro", json={"correo": correo, "contrasena": CLAVE_OK}).json()
    codigo = codigo_totp(d["secreto"])
    assert client.post("/auth/registro/confirmar", json={"token_registro": d["token_registro"], "codigo": codigo}).status_code == 201
    paso1 = login_paso1(client, correo).json()
    assert login_paso2(client, paso1["token_2fa"], codigo).status_code == 200


# ----------------------------------------------------------------------------- segundo paso del login
def test_cp18_4b_el_token_temporal_no_sirve_como_sesion(client, cuenta):
    token_2fa = login_paso1(client, cuenta.correo).json()["token_2fa"]
    assert client.get("/auth/me", headers=cab(token_2fa)).status_code == 401
    assert client.get("/historial", headers=cab(token_2fa)).status_code == 401
    assert client.get("/carritos", headers=cab(token_2fa)).status_code == 401


def test_cp18_5_login_completo_con_codigo_correcto(client, cuenta):
    token_2fa = login_paso1(client, cuenta.correo).json()["token_2fa"]
    r = login_paso2(client, token_2fa, codigo_totp(cuenta.secreto))
    assert r.status_code == 200
    sesion = r.json()
    assert sesion["token"] and sesion["tipo"] == "Bearer"
    assert "uso_codigo_recuperacion" not in sesion
    assert client.get("/auth/me", headers=cab(sesion["token"])).status_code == 200


def test_cp18_5b_el_codigo_acepta_el_espacio_que_muestra_la_app(client, cuenta):
    token_2fa = login_paso1(client, cuenta.correo).json()["token_2fa"]
    c = codigo_totp(cuenta.secreto)
    assert login_paso2(client, token_2fa, f"{c[:3]} {c[3:]}").status_code == 200


def test_cp18_6_codigo_incorrecto_se_rechaza_y_descuenta_intentos(client, cuenta):
    token_2fa = login_paso1(client, cuenta.correo).json()["token_2fa"]
    r = login_paso2(client, token_2fa, codigo_incorrecto(cuenta.secreto))
    assert r.status_code == 401 and "4 intentos" in r.json()["detail"]


def test_cp18_6b_codigo_con_letras_o_longitud_mala_se_rechaza(client, cuenta):
    token_2fa = login_paso1(client, cuenta.correo).json()["token_2fa"]
    for malo in ("abcdef", "12345a", "1234567"):
        assert login_paso2(client, token_2fa, malo).status_code == 401
    assert login_paso2(client, token_2fa, "123").status_code == 422


def test_cp18_7_cinco_intentos_malos_invalidan_el_inicio_de_sesion_aunque_luego_acierte(client, cuenta):
    token_2fa = login_paso1(client, cuenta.correo).json()["token_2fa"]
    for _ in range(5):
        r = login_paso2(client, token_2fa, codigo_incorrecto(cuenta.secreto))
        assert r.status_code == 401
    assert "intentos" in r.json()["detail"].lower()
    r = login_paso2(client, token_2fa, codigo_totp(cuenta.secreto))
    assert r.status_code == 401, "Tras 5 fallos, ni el código correcto debe servir con ese token"


@pytest.mark.req("RNF-09")
def test_cp18_7b_pedir_tokens_nuevos_no_reinicia_el_limite_de_codigos_por_usuario(client, cuenta):
    """Anti fuerza bruta: con tokens nuevos cada vez, igual se corta a los 10 códigos malos (429)."""
    ultimo = None
    for _ in range(12):
        token_2fa = login_paso1(client, cuenta.correo, cuenta.clave)
        if token_2fa.status_code != 200:      # el login mismo también se frena: igual de válido
            ultimo = token_2fa
            break
        ultimo = login_paso2(client, token_2fa.json()["token_2fa"], codigo_incorrecto(cuenta.secreto))
        if ultimo.status_code == 429:
            break
    assert ultimo.status_code == 429 and int(ultimo.headers["Retry-After"]) > 0


def test_cp18_8_el_codigo_no_se_puede_reutilizar(client, cuenta):
    """Un código espiado no sirve una segunda vez (la API recuerda el último paso usado)."""
    codigo = codigo_totp(cuenta.secreto)
    t1 = login_paso1(client, cuenta.correo).json()["token_2fa"]
    assert login_paso2(client, t1, codigo).status_code == 200
    t2 = login_paso1(client, cuenta.correo).json()["token_2fa"]
    r = login_paso2(client, t2, codigo)
    assert r.status_code == 401 and "ya se usó" in r.json()["detail"]


def test_cp18_8b_reusar_un_codigo_correcto_no_gasta_intentos(client, cuenta):
    """Decisión de diseño: el usuario legítimo que escribe dos veces el mismo código no se bloquea a sí mismo."""
    codigo = codigo_totp(cuenta.secreto)
    t1 = login_paso1(client, cuenta.correo).json()["token_2fa"]
    login_paso2(client, t1, codigo)
    t2 = login_paso1(client, cuenta.correo).json()["token_2fa"]
    for _ in range(6):
        assert "ya se usó" in login_paso2(client, t2, codigo).json()["detail"]
    liberar_paso(cuenta.correo)
    assert login_paso2(client, t2, codigo).status_code == 200      # el token sigue vivo: no se descontaron intentos


def test_cp18_9_el_token_temporal_es_de_un_solo_uso(client, cuenta):
    token_2fa = login_paso1(client, cuenta.correo).json()["token_2fa"]
    assert login_paso2(client, token_2fa, codigo_totp(cuenta.secreto)).status_code == 200
    liberar_paso(cuenta.correo)
    assert login_paso2(client, token_2fa, codigo_totp(cuenta.secreto)).status_code == 401


def test_cp18_9b_un_login_nuevo_invalida_el_token_temporal_anterior(client, cuenta):
    viejo = login_paso1(client, cuenta.correo).json()["token_2fa"]
    login_paso1(client, cuenta.correo)
    assert login_paso2(client, viejo, codigo_totp(cuenta.secreto)).status_code == 401


def test_cp18_10_token_temporal_vencido_o_inventado(client, cuenta):
    token_2fa = login_paso1(client, cuenta.correo).json()["token_2fa"]
    consulta_db("UPDATE login_pendientes SET expira_en = NOW() - INTERVAL '1 second' WHERE token = %s", (token_2fa,))
    assert login_paso2(client, token_2fa, codigo_totp(cuenta.secreto)).status_code == 401
    assert login_paso2(client, "no-existe", codigo_totp(cuenta.secreto)).status_code == 401


def test_cp18_11_el_error_de_contrasena_no_revela_nada_distinto_con_2fa(client, cuenta):
    """RF-02: error idéntico para contraseña mala (cuenta con 2FA) y para correo inexistente."""
    con_2fa = login_paso1(client, cuenta.correo, "ClaveIncorrecta99")
    sin_cuenta = login_paso1(client, correo_nuevo())
    assert con_2fa.status_code == sin_cuenta.status_code == 401
    assert con_2fa.json() == sin_cuenta.json()


def test_cp18_12_un_codigo_de_otro_usuario_no_sirve(client, cuenta):
    otra = crear_cuenta(client)
    token_2fa = login_paso1(client, cuenta.correo).json()["token_2fa"]
    r = login_paso2(client, token_2fa, codigo_totp(otra.secreto))
    assert r.status_code == 401


# ----------------------------------------------------------------------------- códigos de recuperación (RF-20 propuesto)
@pytest.mark.req("RF-20")
def test_cp20_1_un_codigo_de_recuperacion_da_sesion_y_avisa_cuantos_quedan(client, cuenta):
    token_2fa = login_paso1(client, cuenta.correo).json()["token_2fa"]
    r = login_paso2(client, token_2fa, cuenta.codigos_recuperacion[0])
    assert r.status_code == 200
    d = r.json()
    assert d["token"] and d["uso_codigo_recuperacion"] is True and d["codigos_restantes"] == 7


@pytest.mark.req("RF-20")
def test_cp20_1b_el_codigo_de_recuperacion_funciona_en_minusculas_y_sin_guion(client, cuenta):
    token_2fa = login_paso1(client, cuenta.correo).json()["token_2fa"]
    escrito = cuenta.codigos_recuperacion[1].lower().replace("-", "")
    assert login_paso2(client, token_2fa, escrito).status_code == 200


@pytest.mark.req("RF-20")
def test_cp20_2_un_codigo_de_recuperacion_sirve_una_sola_vez(client, cuenta):
    codigo = cuenta.codigos_recuperacion[2]
    t1 = login_paso1(client, cuenta.correo).json()["token_2fa"]
    assert login_paso2(client, t1, codigo).status_code == 200
    t2 = login_paso1(client, cuenta.correo).json()["token_2fa"]
    assert login_paso2(client, t2, codigo).status_code == 401


@pytest.mark.req("RF-20")
def test_cp20_3_un_codigo_de_recuperacion_inventado_se_rechaza(client, cuenta):
    token_2fa = login_paso1(client, cuenta.correo).json()["token_2fa"]
    r = login_paso2(client, token_2fa, "AAAAA-BBBBB")
    assert r.status_code == 401 and "token" not in r.json()


@pytest.mark.req("RF-20")
def test_cp20_4_un_codigo_de_recuperacion_de_otra_cuenta_no_sirve(client, cuenta):
    otra = crear_cuenta(client)
    token_2fa = login_paso1(client, cuenta.correo).json()["token_2fa"]
    assert login_paso2(client, token_2fa, otra.codigos_recuperacion[0]).status_code == 401


@pytest.mark.req("RF-20")
def test_cp20_5_regenerar_codigos_exige_sesion_contrasena_y_codigo_de_la_app(client):
    c = cuenta_con_sesion(client)
    ruta = "/auth/2fa/codigos-recuperacion"
    assert client.post(ruta, json={"contrasena": c.clave, "codigo": codigo_totp(c.secreto)}).status_code == 401
    mala = client.post(ruta, json={"contrasena": "ClaveIncorrecta99", "codigo": codigo_totp(c.secreto)}, headers=c.cab)
    assert mala.status_code == 401
    sin_codigo = client.post(ruta, json={"contrasena": c.clave, "codigo": codigo_incorrecto(c.secreto)}, headers=c.cab)
    assert sin_codigo.status_code == 400
    # un código de recuperación NO sirve para generar más códigos (se pide el de la app)
    con_rec = client.post(ruta, json={"contrasena": c.clave, "codigo": c.codigos_recuperacion[0]}, headers=c.cab)
    assert con_rec.status_code == 400


@pytest.mark.req("RF-20")
def test_cp20_6_los_codigos_nuevos_reemplazan_a_los_anteriores(client):
    c = cuenta_con_sesion(client)
    liberar_paso(c.correo)
    r = client.post("/auth/2fa/codigos-recuperacion", json={"contrasena": c.clave, "codigo": codigo_totp(c.secreto)}, headers=c.cab)
    assert r.status_code == 200
    nuevos = r.json()["codigos_recuperacion"]
    assert len(nuevos) == 8 and not set(nuevos) & set(c.codigos_recuperacion)
    # los viejos ya no sirven; uno nuevo sí
    t1 = login_paso1(client, c.correo).json()["token_2fa"]
    assert login_paso2(client, t1, c.codigos_recuperacion[0]).status_code == 401
    t2 = login_paso1(client, c.correo).json()["token_2fa"]
    assert login_paso2(client, t2, nuevos[0]).status_code == 200
