"""
CORREOS DE AVISO (RF-22, PROPUESTO por QA). Nuevo en la v4.

Picksy envía cuatro clases de correo (módulo correos.py):
  * Aviso de inicio de sesión: "¿Acabas de entrar a Picksy?" (con el navegador, la hora y un enlace "No fui yo").
  * Recuperar la contraseña: instrucciones + enlace; y un aviso cuando la clave se cambió.
  * Pago de la membresía: pago iniciado (hay que confirmarlo), pago confirmado y pago cancelado.

No sale ningún correo de verdad: se intercepta correos.enviar y se lee lo que habría enviado.
Los correos se mandan en segundo plano (BackgroundTasks): TestClient los ejecuta al terminar cada petición.

Se verifica QUIÉN recibe cada correo (solo el dueño), CUÁNDO no se envía (login fallido, correo inexistente)
y que ningún dato del usuario pueda inyectar HTML en el mensaje.
"""
import re

import pytest

import correos
from ayudas import (codigo_totp, consulta_db, correo_nuevo, crear_cuenta, cuenta_con_sesion, liberar_paso,
                    login_paso1)

pytestmark = pytest.mark.req("RF-22")
CHROME_WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"


@pytest.fixture
def enviados(monkeypatch):
    """Lista de correos 'enviados': dicts con para, asunto, texto y html."""
    lista = []
    monkeypatch.setattr(correos, "enviar", lambda destino, asunto, texto, html_cuerpo=None: lista.append(
        {"para": destino, "asunto": asunto, "texto": texto, "html": html_cuerpo or ""}))
    return lista


def _entrar(client, cuenta, user_agent=CHROME_WINDOWS):
    """Login completo de una cuenta ya creada, con el navegador indicado. Devuelve la respuesta del paso 2."""
    r = login_paso1(client, cuenta.correo, cuenta.clave)
    assert r.status_code == 200, r.text
    liberar_paso(cuenta.correo)
    return client.post("/auth/2fa/login", headers={"User-Agent": user_agent},
                       json={"token_2fa": r.json()["token_2fa"], "codigo": codigo_totp(cuenta.secreto)})


def _con(enviados, texto_asunto):
    return [c for c in enviados if texto_asunto.lower() in c["asunto"].lower()]


# --------------------------------------------------------------------------- aviso de inicio de sesión
def test_cp22_01_al_iniciar_sesion_llega_el_aviso_al_dueno(client, enviados):
    c = crear_cuenta(client)
    enviados.clear()
    assert _entrar(client, c).status_code == 200
    avisos = _con(enviados, "inicio de sesión")
    assert len(avisos) == 1
    assert avisos[0]["para"] == c.correo
    assert "Chrome en Windows" in avisos[0]["texto"], "Debe decir desde qué navegador se entró"


def test_cp22_02_el_aviso_trae_el_enlace_para_asegurar_la_cuenta(client, enviados):
    c = crear_cuenta(client)
    enviados.clear()
    _entrar(client, c)
    aviso = _con(enviados, "inicio de sesión")[0]
    assert "No fui yo" in aviso["html"]
    assert re.search(r"recuperar\.html", aviso["texto"]), "Debe llevar al flujo de recuperar la contraseña"


def test_cp22_03_una_contrasena_incorrecta_no_envia_aviso(client, enviados):
    c = crear_cuenta(client)
    enviados.clear()
    assert client.post("/auth/login", json={"correo": c.correo, "contrasena": "OtraClave000"}).status_code == 401
    assert enviados == []


def test_cp22_04_un_codigo_2fa_incorrecto_no_envia_aviso(client, enviados):
    c = crear_cuenta(client)
    enviados.clear()
    r = login_paso1(client, c.correo, c.clave)
    liberar_paso(c.correo)
    mal = client.post("/auth/2fa/login", json={"token_2fa": r.json()["token_2fa"], "codigo": "000000"})
    assert mal.status_code in (400, 401)
    assert _con(enviados, "inicio de sesión") == []


def test_cp22_05_el_aviso_escapa_el_navegador_y_no_inyecta_html(client, enviados):
    c = crear_cuenta(client)
    enviados.clear()
    _entrar(client, c, user_agent="<script>alert(1)</script> <img src=x onerror=alert(2)> Chrome Windows")
    aviso = _con(enviados, "inicio de sesión")[0]
    assert "<script>" not in aviso["html"] and "<img src=x" not in aviso["html"]


def test_cp22_06_una_cuenta_antigua_que_activa_el_2fa_tambien_recibe_el_aviso(client, enviados):
    """Segundo punto de entrada: cuentas de la v1/v2 sin Authenticator entran y configuran el 2FA en el mismo paso."""
    c = crear_cuenta(client)
    consulta_db("UPDATE usuarios SET totp_activo = FALSE, totp_secreto = NULL WHERE correo = %s", (c.correo,))
    d = login_paso1(client, c.correo, c.clave).json()
    secreto = client.post("/auth/2fa/pendiente/configurar", json={"token_2fa": d["token_2fa"]}).json()["secreto"]
    enviados.clear()
    ok = client.post("/auth/2fa/pendiente/activar", json={"token_2fa": d["token_2fa"], "codigo": codigo_totp(secreto)})
    assert ok.status_code == 200, ok.text
    avisos = _con(enviados, "inicio de sesión")
    assert len(avisos) == 1 and avisos[0]["para"] == c.correo


# --------------------------------------------------------------------------- recuperar la contraseña
def _pedir_recuperacion(client, correo):
    return client.post("/auth/recuperar", json={"correo": correo})


def test_cp22_10_recuperar_envia_las_instrucciones_con_el_enlace(client, enviados):
    c = crear_cuenta(client)
    enviados.clear()
    assert _pedir_recuperacion(client, c.correo).status_code == 202
    mail = _con(enviados, "restablece tu contrase")[0]
    assert mail["para"] == c.correo
    assert "Google Authenticator" in mail["texto"], "Debe explicar que se necesita el código del Authenticator"
    assert re.search(r"restablecer\.html\?token=[\w\-]{20,}", mail["texto"])
    assert "30 minutos" in mail["texto"] or "minutos" in mail["texto"], "Debe decir cuánto dura el enlace"


def test_cp22_11_un_correo_inexistente_no_recibe_nada_y_la_respuesta_es_igual(client, enviados):
    """Anti enumeración de usuarios: no se debe poder averiguar quién tiene cuenta, ni por la respuesta ni por el correo."""
    c = crear_cuenta(client)
    enviados.clear()
    existe = _pedir_recuperacion(client, c.correo)
    no_existe = _pedir_recuperacion(client, correo_nuevo())
    assert existe.status_code == no_existe.status_code == 202 and existe.json() == no_existe.json()
    assert [m["para"] for m in enviados] == [c.correo], "Solo la cuenta real recibe correo"


def test_cp22_12_al_cambiar_la_contrasena_llega_el_aviso_de_cambio(client, enviados):
    c = crear_cuenta(client)
    _pedir_recuperacion(client, c.correo)
    token = re.search(r"token=([\w\-]+)", _con(enviados, "restablece tu contrase")[0]["texto"]).group(1)
    enviados.clear()
    liberar_paso(c.correo)
    r = client.post("/auth/recuperar/restablecer", json={
        "token": token, "contrasena_nueva": "OtraClave9999", "codigo": codigo_totp(c.secreto)})
    assert r.status_code == 200, r.text
    aviso = _con(enviados, "fue cambiada")
    assert len(aviso) == 1 and aviso[0]["para"] == c.correo
    assert "cerramos todas tus sesiones" in aviso[0]["texto"]


def test_cp22_13_si_el_cambio_falla_no_se_envia_el_aviso_de_cambio(client, enviados):
    c = crear_cuenta(client)
    _pedir_recuperacion(client, c.correo)
    token = re.search(r"token=([\w\-]+)", _con(enviados, "restablece tu contrase")[0]["texto"]).group(1)
    enviados.clear()
    r = client.post("/auth/recuperar/restablecer", json={
        "token": token, "contrasena_nueva": "OtraClave9999", "codigo": "000000"})
    assert r.status_code in (400, 401)
    assert _con(enviados, "fue cambiada") == []


# --------------------------------------------------------------------------- pagos de la membresía
@pytest.fixture
def pagador(client, enviados):
    c = cuenta_con_sesion(client)
    m = client.post("/pagos/metodos", headers=c.cab, json={
        "tipo": "tarjeta_credito", "alias": "Mi tarjeta", "marca": "Visa", "ultimos4": "4242"}).json()
    enviados.clear()
    c.metodo = m
    return c


def _iniciar(client, c, plan="anual"):
    r = client.post("/pagos", json={"plan": plan, "metodo_id": c.metodo["id"]}, headers=c.cab)
    assert r.status_code == 201, r.text
    return r.json()


def test_cp22_20_al_iniciar_un_pago_llega_el_resumen_con_la_referencia(client, enviados, pagador):
    pago = _iniciar(client, pagador)
    mail = _con(enviados, "iniciaste un pago")
    assert len(mail) == 1 and mail[0]["para"] == pagador.correo
    assert pago["referencia"] in mail[0]["texto"]
    assert "99.900" in mail[0]["texto"] and "4242" in mail[0]["texto"]
    assert _con(enviados, "pago confirmado") == [], "Todavía no se ha pagado: no debe haber comprobante"


def test_cp22_21_al_confirmar_llega_el_comprobante_con_la_fecha_de_vencimiento(client, enviados, pagador):
    pago = _iniciar(client, pagador, "semestral")
    enviados.clear()
    assert client.post(f"/pagos/{pago['id']}/confirmar", headers=pagador.cab).status_code == 200
    mail = _con(enviados, "pago confirmado")
    assert len(mail) == 1 and mail[0]["para"] == pagador.correo
    assert pago["referencia"] in mail[0]["texto"] and "59.900" in mail[0]["texto"]
    assert "Activa hasta" in mail[0]["texto"]


def test_cp22_22_al_cancelar_llega_el_aviso_de_cancelacion(client, enviados, pagador):
    pago = _iniciar(client, pagador)
    enviados.clear()
    assert client.post(f"/pagos/{pago['id']}/cancelar", headers=pagador.cab).status_code == 200
    mail = _con(enviados, "pago cancelado")
    assert len(mail) == 1 and mail[0]["para"] == pagador.correo and pago["referencia"] in mail[0]["texto"]


def test_cp22_23_confirmar_dos_veces_no_envia_dos_comprobantes(client, enviados, pagador):
    pago = _iniciar(client, pagador)
    client.post(f"/pagos/{pago['id']}/confirmar", headers=pagador.cab)
    segunda = client.post(f"/pagos/{pago['id']}/confirmar", headers=pagador.cab)
    assert segunda.status_code == 409
    assert len(_con(enviados, "pago confirmado")) == 1


def test_cp22_24_un_intento_ajeno_no_envia_correos_a_nadie(client, enviados, pagador):
    pago = _iniciar(client, pagador)
    otro = cuenta_con_sesion(client)
    enviados.clear()
    assert client.post(f"/pagos/{pago['id']}/confirmar", headers=otro.cab).status_code == 404
    assert client.post(f"/pagos/{pago['id']}/cancelar", headers=otro.cab).status_code == 404
    assert enviados == []


def test_cp22_25_los_correos_de_pago_no_traen_el_numero_completo_ni_cvv(client, enviados, pagador):
    pago = _iniciar(client, pagador)
    client.post(f"/pagos/{pago['id']}/confirmar", headers=pagador.cab)
    for m in enviados:
        assert "4242424242424242" not in m["texto"] + m["html"]
        assert "cvv" not in (m["texto"] + m["html"]).lower()


# --------------------------------------------------------------------------- calidad del mensaje
def test_cp22_30_cada_correo_trae_texto_y_html_sin_scripts(client, enviados, pagador):
    pago = _iniciar(client, pagador)
    client.post(f"/pagos/{pago['id']}/confirmar", headers=pagador.cab)
    _pedir_recuperacion(client, pagador.correo)
    assert len(enviados) >= 3
    for m in enviados:
        assert m["texto"].strip(), "Falta la versión de texto plano"
        assert "<div" in m["html"] and "style=" in m["html"], "Falta la versión HTML (con estilos en línea)"
        assert "<script" not in m["html"].lower() and "javascript:" not in m["html"].lower()
        assert m["asunto"].strip() and "\n" not in m["asunto"], "El asunto debe ser una sola línea"
