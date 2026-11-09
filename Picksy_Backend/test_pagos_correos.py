"""
Pruebas de los correos (recuperación, aviso de inicio de sesión) y de la membresía y sus pagos.
Ubicación: Picksy_Backend/test_pagos_correos.py
Ejecutar:  pytest test_pagos_correos.py -v

No envía correos de verdad: se intercepta correos.enviar y se leen los mensajes que habría enviado.
Los usuarios de prueba (pagos_xxxx@test.com) se borran al terminar.
"""
import os
import uuid

import psycopg2
import pyotp
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

import correos
import limitador
import pagos
from main import app

load_dotenv()
client = TestClient(app)
CLAVE = "Prueba1234"
USUARIOS = []   # correos creados, para borrarlos al final


def _db(sql, params=None):
    con = psycopg2.connect(dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
                           host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"))
    try:
        with con, con.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else None
    finally:
        con.close()


@pytest.fixture(autouse=True)
def _limpio():
    limitador.reiniciar() if hasattr(limitador, "reiniciar") else None
    yield


@pytest.fixture(scope="module", autouse=True)
def _borrar_al_final():
    yield
    for correo in USUARIOS:
        _db("DELETE FROM usuarios WHERE correo = %s", (correo,))


@pytest.fixture
def correos_enviados(monkeypatch):
    enviados = []
    monkeypatch.setattr(correos, "enviar", lambda destino, asunto, texto, html_cuerpo=None:
                        enviados.append({"para": destino, "asunto": asunto, "texto": texto, "html": html_cuerpo or ""}))
    return enviados


def _crear_cuenta():
    correo = f"pagos_{uuid.uuid4().hex[:8]}@test.com"
    USUARIOS.append(correo)
    r1 = client.post("/auth/registro", json={"correo": correo, "contrasena": CLAVE})
    assert r1.status_code == 201, r1.text
    secreto = r1.json()["secreto"]
    r2 = client.post("/auth/registro/confirmar", json={"token_registro": r1.json()["token_registro"],
                                                       "codigo": pyotp.TOTP(secreto).now()})
    assert r2.status_code == 201, r2.text
    return correo, secreto


def _entrar(correo, secreto, **cabeceras):
    r = client.post("/auth/login", json={"correo": correo, "contrasena": CLAVE})
    assert r.status_code == 200, r.text
    _db("UPDATE usuarios SET totp_ultimo_paso = 0 WHERE correo = %s", (correo,))
    r2 = client.post("/auth/2fa/login", json={"token_2fa": r.json()["token_2fa"], "codigo": pyotp.TOTP(secreto).now()},
                     headers=cabeceras)
    assert r2.status_code == 200, r2.text
    return {"Authorization": f"Bearer {r2.json()['token']}"}


@pytest.fixture
def usuario(correos_enviados):
    correo, secreto = _crear_cuenta()
    cab = _entrar(correo, secreto)
    correos_enviados.clear()
    return {"correo": correo, "secreto": secreto, "cab": cab}


def _tarjeta(cab, tipo="tarjeta_credito", **extra):
    cuerpo = {"tipo": tipo, "alias": "Mi tarjeta", "marca": "Visa", "ultimos4": "4242", **extra}
    r = client.post("/pagos/metodos", json=cuerpo, headers=cab)
    assert r.status_code == 201, r.text
    return r.json()


# =========================================================== correo: aviso de inicio de sesión
def test_aviso_de_inicio_de_sesion(correos_enviados):
    correo, secreto = _crear_cuenta()
    correos_enviados.clear()
    _entrar(correo, secreto, **{"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120 Safari/537.36"})
    avisos = [c for c in correos_enviados if "inicio de sesión" in c["asunto"]]
    assert len(avisos) == 1
    assert avisos[0]["para"] == correo
    assert "Chrome en Windows" in avisos[0]["texto"]
    assert "No fui yo" in avisos[0]["html"] and "recuperar.html" in avisos[0]["texto"]


def test_login_con_contrasena_mala_no_envia_aviso(correos_enviados):
    correo, _ = _crear_cuenta()
    correos_enviados.clear()
    r = client.post("/auth/login", json={"correo": correo, "contrasena": "otra-mala-123"})
    assert r.status_code == 401
    assert correos_enviados == []


def test_el_aviso_escapa_el_navegador(correos_enviados):
    correo, secreto = _crear_cuenta()
    correos_enviados.clear()
    _entrar(correo, secreto, **{"User-Agent": "<script>alert(1)</script> Chrome Windows"})
    html = [c for c in correos_enviados if "inicio de sesión" in c["asunto"]][0]["html"]
    assert "<script>" not in html


# =========================================================== correo: recuperación
def test_recuperacion_envia_instrucciones_y_aviso_de_cambio(correos_enviados):
    correo, secreto = _crear_cuenta()
    correos_enviados.clear()
    r = client.post("/auth/recuperar", json={"correo": correo})
    assert r.status_code == 202
    mail = [c for c in correos_enviados if c["asunto"].startswith("Restablece")][0]
    assert mail["para"] == correo
    assert "Google Authenticator" in mail["texto"] and "restablecer.html?token=" in mail["texto"]
    token = mail["texto"].split("token=")[1].split()[0]

    _db("UPDATE usuarios SET totp_ultimo_paso = 0 WHERE correo = %s", (correo,))
    r = client.post("/auth/recuperar/restablecer", json={"token": token, "contrasena_nueva": "NuevaClave123",
                                                          "codigo": pyotp.TOTP(secreto).now()})
    assert r.status_code == 200, r.text
    assert any("fue cambiada" in c["asunto"] and c["para"] == correo for c in correos_enviados)


def test_recuperar_con_correo_inexistente_no_envia_nada(correos_enviados):
    r = client.post("/auth/recuperar", json={"correo": f"nadie_{uuid.uuid4().hex[:6]}@test.com"})
    assert r.status_code == 202
    assert correos_enviados == []


# =========================================================== métodos de pago
def test_metodo_rechaza_numero_completo_de_tarjeta(usuario):
    r = client.post("/pagos/metodos", headers=usuario["cab"], json={
        "tipo": "tarjeta_credito", "alias": "x", "marca": "Visa", "ultimos4": "4242424242424242"})
    assert r.status_code == 422


@pytest.mark.parametrize("cuerpo", [
    {"tipo": "tarjeta_credito", "alias": "x"},                       # sin marca ni últimos 4
    {"tipo": "pse", "alias": "x"},                                   # sin banco
    {"tipo": "nequi", "alias": "x"},                                 # sin celular
    {"tipo": "cheque", "alias": "x"},                                # tipo inventado
    {"tipo": "pse", "alias": "   ", "banco": "Bancolombia"},         # alias vacío
])
def test_metodo_datos_invalidos(usuario, cuerpo):
    assert client.post("/pagos/metodos", json=cuerpo, headers=usuario["cab"]).status_code == 422


def test_metodos_predeterminado_maximo_y_borrado(usuario):
    cab = usuario["cab"]
    a = _tarjeta(cab)
    assert a["predeterminado"] is True and a["descripcion"] == "Visa crédito ••••4242"
    b = _tarjeta(cab, tipo="tarjeta_debito", predeterminado=True)
    lista = client.get("/pagos/metodos", headers=cab).json()
    assert [m["id"] for m in lista if m["predeterminado"]] == [b["id"]]
    for _ in range(3):
        _tarjeta(cab)
    r = client.post("/pagos/metodos", headers=cab, json={"tipo": "pse", "alias": "x", "banco": "Davivienda"})
    assert r.status_code == 409                                   # máximo 5
    assert client.delete(f"/pagos/metodos/{b['id']}", headers=cab).status_code == 204
    lista = client.get("/pagos/metodos", headers=cab).json()
    assert len(lista) == 4 and sum(m["predeterminado"] for m in lista) == 1   # otro tomó su lugar


def test_metodos_son_privados(usuario, correos_enviados):
    a = _tarjeta(usuario["cab"])
    correo, secreto = _crear_cuenta()
    otro = _entrar(correo, secreto)
    assert client.get("/pagos/metodos", headers=otro).json() == []
    assert client.delete(f"/pagos/metodos/{a['id']}", headers=otro).status_code == 404


def test_pagos_exigen_sesion():
    for ruta in ("/pagos/metodos", "/pagos", "/pagos/planes", "/pagos/membresia"):
        assert client.get(ruta).status_code == 401


# =========================================================== planes y membresía
def _pagar(cab, plan="mensual", metodo=None):
    metodo = metodo or _tarjeta(cab)
    return client.post("/pagos", json={"plan": plan, "metodo_id": metodo["id"]}, headers=cab)


def test_planes_de_membresia(usuario):
    r = client.get("/pagos/planes", headers=usuario["cab"])
    assert r.status_code == 200
    por_codigo = {p["codigo"]: p for p in r.json()}
    assert set(por_codigo) == {"mensual", "semestral", "anual"}
    assert por_codigo["mensual"]["ahorro_porcentaje"] == 0
    assert por_codigo["anual"]["valor"] < 12 * por_codigo["mensual"]["valor"]       # el anual sale más barato
    assert por_codigo["anual"]["ahorro_porcentaje"] > por_codigo["semestral"]["ahorro_porcentaje"] > 0
    assert abs(por_codigo["anual"]["valor_por_mes"] * 12 - por_codigo["anual"]["valor"]) < 1


def test_sin_pagos_no_hay_membresia(usuario):
    m = client.get("/pagos/membresia", headers=usuario["cab"]).json()
    assert m["activa"] is False and m["dias_restantes"] == 0


# =========================================================== pagos
def test_pago_completo_con_correos(usuario, correos_enviados):
    cab = usuario["cab"]
    r = _pagar(cab, "anual")
    assert r.status_code == 201, r.text
    pago = r.json()
    assert pago["estado"] == "pendiente" and pago["valor"] == 99_900 and pago["meses"] == 12
    assert pago["simulado"] is True and "4242" in pago["metodo"] and pago["membresia_hasta"] is None
    assert client.get("/pagos/membresia", headers=cab).json()["activa"] is False        # pendiente: todavía no hay membresía
    iniciado = [c for c in correos_enviados if c["asunto"].startswith("Iniciaste un pago")]
    assert len(iniciado) == 1 and iniciado[0]["para"] == usuario["correo"] and pago["referencia"] in iniciado[0]["texto"]

    r = client.post(f"/pagos/{pago['id']}/confirmar", headers=cab)
    assert r.status_code == 200 and r.json()["estado"] == "pagado" and r.json()["membresia_hasta"]
    m = client.get("/pagos/membresia", headers=cab).json()
    assert m["activa"] is True and m["plan"] == "anual" and 360 <= m["dias_restantes"] <= 366
    confirmado = [c for c in correos_enviados if c["asunto"].startswith("Pago confirmado")]
    assert len(confirmado) == 1 and "Activa hasta" in confirmado[0]["texto"]
    assert client.post(f"/pagos/{pago['id']}/confirmar", headers=cab).status_code == 409     # no se paga dos veces
    assert client.post(f"/pagos/{pago['id']}/cancelar", headers=cab).status_code == 409
    assert client.get("/pagos", headers=cab).json()[0]["estado"] == "pagado"


def test_un_plan_nuevo_se_suma_al_tiempo_que_queda(usuario):
    cab = usuario["cab"]
    m = _tarjeta(cab)
    p1 = _pagar(cab, "mensual", m).json()
    client.post(f"/pagos/{p1['id']}/confirmar", headers=cab)
    hasta1 = client.get("/pagos/membresia", headers=cab).json()["dias_restantes"]
    p2 = _pagar(cab, "semestral", m).json()
    client.post(f"/pagos/{p2['id']}/confirmar", headers=cab)
    despues = client.get("/pagos/membresia", headers=cab).json()
    assert despues["plan"] == "semestral"
    assert despues["dias_restantes"] >= hasta1 + 180          # se suma 1 mes + 6 meses (no se pierden días)


def test_membresia_vencida_se_reactiva_desde_hoy(usuario):
    cab = usuario["cab"]
    p = _pagar(cab, "mensual").json()
    client.post(f"/pagos/{p['id']}/confirmar", headers=cab)
    _db("UPDATE membresias SET vence_en = NOW() - INTERVAL '3 days' WHERE usuario_id = (SELECT id FROM usuarios WHERE correo = %s)", (usuario["correo"],))
    assert client.get("/pagos/membresia", headers=cab).json()["activa"] is False
    p2 = _pagar(cab, "mensual").json()
    client.post(f"/pagos/{p2['id']}/confirmar", headers=cab)
    m = client.get("/pagos/membresia", headers=cab).json()
    assert m["activa"] is True and 27 <= m["dias_restantes"] <= 31      # cuenta desde hoy, no desde la fecha vencida


def test_plan_inventado_y_ids_ajenos(usuario, correos_enviados):
    cab = usuario["cab"]
    m = _tarjeta(cab)
    assert client.post("/pagos", json={"plan": "gratis", "metodo_id": m["id"]}, headers=cab).status_code == 422
    assert client.post("/pagos", json={"plan": "mensual", "metodo_id": 99999999}, headers=cab).status_code == 404
    correo, secreto = _crear_cuenta()
    otro = _entrar(correo, secreto)
    # el otro usuario no puede usar mi método de pago ni ver o confirmar mi pago
    assert client.post("/pagos", json={"plan": "mensual", "metodo_id": m["id"]}, headers=otro).status_code == 404
    mio = _pagar(cab, "mensual", m).json()
    assert client.get(f"/pagos/{mio['id']}", headers=otro).status_code == 404
    assert client.post(f"/pagos/{mio['id']}/confirmar", headers=otro).status_code == 404
    assert client.get("/pagos", headers=otro).json() == [] and client.get("/pagos/membresia", headers=otro).json()["activa"] is False


def test_el_precio_no_cambia_si_cambian_los_planes(usuario, monkeypatch):
    cab = usuario["cab"]
    p = _pagar(cab, "mensual").json()
    monkeypatch.setitem(pagos.PLAN_POR_CODIGO["mensual"], "valor", pagos.Decimal("50000"))
    assert client.get(f"/pagos/{p['id']}", headers=cab).json()["valor"] == 12_900


def test_un_pago_nuevo_cancela_el_pendiente_anterior(usuario):
    cab = usuario["cab"]
    m = _tarjeta(cab)
    p1 = _pagar(cab, "mensual", m).json()
    p2 = _pagar(cab, "anual", m).json()
    assert client.get(f"/pagos/{p1['id']}", headers=cab).json()["estado"] == "cancelado"
    assert client.post(f"/pagos/{p1['id']}/confirmar", headers=cab).status_code == 409
    assert client.get(f"/pagos/{p2['id']}", headers=cab).json()["estado"] == "pendiente"


def test_cancelar_envia_correo(usuario, correos_enviados):
    cab = usuario["cab"]
    p = _pagar(cab).json()
    r = client.post(f"/pagos/{p['id']}/cancelar", headers=cab)
    assert r.status_code == 200 and r.json()["estado"] == "cancelado"
    assert any(c["asunto"].startswith("Pago cancelado") for c in correos_enviados)
    assert client.get("/pagos/membresia", headers=cab).json()["activa"] is False


def test_pago_vencido_no_se_confirma(usuario):
    cab = usuario["cab"]
    p = _pagar(cab).json()
    _db("UPDATE pagos_membresia SET expira_en = NOW() - INTERVAL '1 minute' WHERE id = %s", (p["id"],))
    assert client.get(f"/pagos/{p['id']}", headers=cab).json()["estado"] == "vencido"
    assert client.post(f"/pagos/{p['id']}/confirmar", headers=cab).status_code == 409
    assert client.get("/pagos/membresia", headers=cab).json()["activa"] is False


def test_quitar_el_metodo_cancela_el_pago_pendiente(usuario):
    cab = usuario["cab"]
    m = _tarjeta(cab)
    p = _pagar(cab, "mensual", m).json()
    assert client.delete(f"/pagos/metodos/{m['id']}", headers=cab).status_code == 204
    assert client.get(f"/pagos/{p['id']}", headers=cab).json()["estado"] == "cancelado"


def test_pago_pagado_sobrevive_si_se_borra_el_metodo(usuario):
    cab = usuario["cab"]
    m = _tarjeta(cab)
    p = _pagar(cab, "mensual", m).json()
    client.post(f"/pagos/{p['id']}/confirmar", headers=cab)
    assert client.delete(f"/pagos/metodos/{m['id']}", headers=cab).status_code == 204
    ver = client.get(f"/pagos/{p['id']}", headers=cab).json()
    assert ver["estado"] == "pagado" and "4242" in ver["metodo"]            # el comprobante conserva cómo se pagó


def test_limite_de_pagos_por_hora(usuario):
    cab = usuario["cab"]
    m = _tarjeta(cab)
    codigos = [_pagar(cab, "mensual", m).status_code for _ in range(pagos.MAX_PAGOS_HORA + 1)]
    assert codigos[:pagos.MAX_PAGOS_HORA] == [201] * pagos.MAX_PAGOS_HORA and codigos[-1] == 429
