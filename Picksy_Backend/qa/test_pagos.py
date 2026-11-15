"""
MEMBRESÍA Y PAGOS (RF-21, PROPUESTO por QA). Nuevo en la v4.

Picksy no vende productos: lo único que cobra es el uso de la página (membresía mensual, semestral o anual).
El pago es SIMULADO (modo demostración, no hay pasarela): nace "pendiente", se confirma o se cancela.

Qué se verifica:
  * Planes y precios (12.900 / 59.900 / 99.900).
  * Métodos de pago: nunca se guarda el número completo ni el CVV (RNF-11), máximo 5, uno predeterminado.
  * Pagos: pendiente -> pagado / cancelado / vencido; la membresía se suma o se reactiva según corresponda.
  * AISLAMIENTO ENTRE USUARIOS: nadie ve, paga, confirma, cancela ni borra lo de otro (siempre 404).
  * Un pago no se confirma ni se cancela dos veces (409) y el precio queda fijo al crearlo.
  * Límite de pagos por hora (429, RNF-09).

Los correos que envían los pagos se prueban en test_correos.py.
"""
import re

import pytest

import pagos
from ayudas import consulta_db, correo_nuevo, crear_cuenta, cuenta_con_sesion, iniciar_sesion

pytestmark = pytest.mark.req("RF-21")


# --------------------------------------------------------------------------- ayudas de este archivo
@pytest.fixture(autouse=True)
def sin_correos_reales(monkeypatch):
    """Aquí no se mira el contenido de los correos (eso es test_correos.py), pero tampoco deben salir de verdad."""
    import correos
    monkeypatch.setattr(correos, "enviar", lambda *a, **k: None)


def _tarjeta(client, cab, tipo="tarjeta_credito", **extra):
    cuerpo = {"tipo": tipo, "alias": "Mi tarjeta", "marca": "Visa", "ultimos4": "4242", **extra}
    r = client.post("/pagos/metodos", json=cuerpo, headers=cab)
    assert r.status_code == 201, f"{r.status_code}: {r.text[:200]}"
    return r.json()


def _pagar(client, cab, plan="mensual", metodo=None):
    metodo = metodo or _tarjeta(client, cab)
    return client.post("/pagos", json={"plan": plan, "metodo_id": metodo["id"]}, headers=cab)


def _pagar_ok(client, cab, plan="mensual", metodo=None):
    r = _pagar(client, cab, plan, metodo)
    assert r.status_code == 201, f"{r.status_code}: {r.text[:200]}"
    return r.json()


def _membresia(client, cab):
    r = client.get("/pagos/membresia", headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- sesión obligatoria
RUTAS_GET = ["/pagos/planes", "/pagos/membresia", "/pagos/metodos", "/pagos", "/pagos/1"]


@pytest.mark.parametrize("ruta", RUTAS_GET)
def test_cp21_01_las_consultas_de_pagos_exigen_sesion(client, ruta):
    assert client.get(ruta).status_code == 401


def test_cp21_02_las_acciones_de_pagos_exigen_sesion(client):
    assert client.post("/pagos", json={"plan": "mensual", "metodo_id": 1}).status_code == 401
    assert client.post("/pagos/metodos", json={"tipo": "pse", "alias": "x", "banco": "Nu"}).status_code == 401
    assert client.post("/pagos/1/confirmar").status_code == 401
    assert client.post("/pagos/1/cancelar").status_code == 401
    assert client.delete("/pagos/metodos/1").status_code == 401


# --------------------------------------------------------------------------- planes
def test_cp21_03_los_tres_planes_y_sus_precios(client):
    cab = cuenta_con_sesion(client).cab
    r = client.get("/pagos/planes", headers=cab)
    assert r.status_code == 200
    por_codigo = {p["codigo"]: p for p in r.json()}
    assert set(por_codigo) == {"mensual", "semestral", "anual"}
    assert (por_codigo["mensual"]["valor"], por_codigo["semestral"]["valor"], por_codigo["anual"]["valor"]) == (12_900, 59_900, 99_900)
    assert (por_codigo["mensual"]["meses"], por_codigo["semestral"]["meses"], por_codigo["anual"]["meses"]) == (1, 6, 12)


def test_cp21_04_el_plan_largo_sale_mas_barato_por_mes(client):
    cab = cuenta_con_sesion(client).cab
    p = {x["codigo"]: x for x in client.get("/pagos/planes", headers=cab).json()}
    assert p["mensual"]["ahorro_porcentaje"] == 0
    assert p["anual"]["ahorro_porcentaje"] > p["semestral"]["ahorro_porcentaje"] > 0
    assert p["anual"]["valor"] < 12 * p["mensual"]["valor"]
    assert abs(p["anual"]["valor_por_mes"] * 12 - p["anual"]["valor"]) < 1


def test_cp21_05_sin_pagos_no_hay_membresia(client):
    m = _membresia(client, cuenta_con_sesion(client).cab)
    assert m["activa"] is False and m["dias_restantes"] == 0


# --------------------------------------------------------------------------- métodos de pago
def test_cp21_10_metodos_de_los_cuatro_tipos(client):
    cab = cuenta_con_sesion(client).cab
    credito = _tarjeta(client, cab)
    assert credito["descripcion"] == "Visa crédito ••••4242" and credito["predeterminado"] is True
    debito = _tarjeta(client, cab, tipo="tarjeta_debito", marca="Mastercard", ultimos4="1111")
    assert "débito" in debito["descripcion"] and debito["predeterminado"] is False
    pse = client.post("/pagos/metodos", json={"tipo": "pse", "alias": "Mi banco", "banco": "Bancolombia"}, headers=cab)
    nequi = client.post("/pagos/metodos", json={"tipo": "nequi", "alias": "Mi Nequi", "ultimos4": "1234"}, headers=cab)
    assert pse.status_code == 201 and nequi.status_code == 201, (pse.text, nequi.text)


@pytest.mark.parametrize("cuerpo", [
    {"tipo": "tarjeta_credito", "alias": "x"},                      # sin marca ni últimos 4
    {"tipo": "pse", "alias": "x"},                                  # PSE sin banco
    {"tipo": "nequi", "alias": "x"},                                # Nequi sin celular
    {"tipo": "cheque", "alias": "x"},                               # tipo inventado
    {"tipo": "pse", "alias": "   ", "banco": "Bancolombia"},        # alias vacío
])
def test_cp21_11_metodo_con_datos_invalidos_da_422(client, cuerpo):
    cab = cuenta_con_sesion(client).cab
    assert client.post("/pagos/metodos", json=cuerpo, headers=cab).status_code == 422


@pytest.mark.req("RNF-11")
def test_cp21_12_nunca_se_acepta_el_numero_completo_de_la_tarjeta(client):
    cab = cuenta_con_sesion(client).cab
    for numero in ("4242424242424242", "424242424242", "42424", "abcd"):
        r = client.post("/pagos/metodos", headers=cab, json={
            "tipo": "tarjeta_credito", "alias": "x", "marca": "Visa", "ultimos4": numero})
        assert r.status_code == 422, f"'{numero}' debió rechazarse: {r.status_code}"
    assert client.get("/pagos/metodos", headers=cab).json() == [], "No debe quedar ningún método guardado"


@pytest.mark.req("RNF-11")
def test_cp21_13_el_numero_completo_y_el_cvv_no_se_guardan_ni_se_devuelven(client):
    cab = cuenta_con_sesion(client).cab
    r = client.post("/pagos/metodos", headers=cab, json={
        "tipo": "tarjeta_credito", "alias": "Mi tarjeta", "marca": "Visa", "ultimos4": "4242",
        "numero": "4242424242424242", "cvv": "123", "cvc": "123", "vencimiento": "12/30"})
    assert r.status_code == 201, r.text
    texto = r.text + client.get("/pagos/metodos", headers=cab).text
    assert "4242424242424242" not in texto and '"cvv"' not in texto and '"cvc"' not in texto
    columnas = {c[0] for c in consulta_db(
        "SELECT column_name FROM information_schema.columns WHERE table_name IN ('metodos_pago', 'pagos_membresia')")}
    prohibidas = {c for c in columnas if re.search(r"numero|cvv|cvc|pan$|vencimiento|expir.*tarjeta", c)}
    assert not prohibidas, f"La base guarda datos sensibles de la tarjeta: {prohibidas}"


def test_cp21_14_el_primer_metodo_es_el_predeterminado_y_solo_hay_uno(client):
    cab = cuenta_con_sesion(client).cab
    a = _tarjeta(client, cab)
    assert a["predeterminado"] is True
    b = _tarjeta(client, cab, tipo="tarjeta_debito", predeterminado=True)
    lista = client.get("/pagos/metodos", headers=cab).json()
    assert [m["id"] for m in lista if m["predeterminado"]] == [b["id"]]


def test_cp21_15_maximo_cinco_metodos_por_usuario(client):
    cab = cuenta_con_sesion(client).cab
    for _ in range(5):
        _tarjeta(client, cab)
    r = client.post("/pagos/metodos", headers=cab, json={"tipo": "pse", "alias": "x", "banco": "Davivienda"})
    assert r.status_code == 409


def test_cp21_16_al_borrar_el_predeterminado_otro_toma_su_lugar(client):
    cab = cuenta_con_sesion(client).cab
    a = _tarjeta(client, cab)
    _tarjeta(client, cab)
    assert client.delete(f"/pagos/metodos/{a['id']}", headers=cab).status_code == 204
    lista = client.get("/pagos/metodos", headers=cab).json()
    assert len(lista) == 1 and lista[0]["predeterminado"] is True


# --------------------------------------------------------------------------- aislamiento entre usuarios
def test_cp21_20_un_usuario_no_ve_ni_borra_los_metodos_de_otro(client):
    dueno, otro = cuenta_con_sesion(client), cuenta_con_sesion(client)
    m = _tarjeta(client, dueno.cab)
    assert client.get("/pagos/metodos", headers=otro.cab).json() == []
    assert client.delete(f"/pagos/metodos/{m['id']}", headers=otro.cab).status_code == 404
    assert len(client.get("/pagos/metodos", headers=dueno.cab).json()) == 1, "El método del dueño debe seguir ahí"


def test_cp21_21_no_se_puede_pagar_con_el_metodo_de_otro(client):
    dueno, otro = cuenta_con_sesion(client), cuenta_con_sesion(client)
    m = _tarjeta(client, dueno.cab)
    r = client.post("/pagos", json={"plan": "mensual", "metodo_id": m["id"]}, headers=otro.cab)
    assert r.status_code == 404
    assert client.get("/pagos", headers=otro.cab).json() == []


def test_cp21_22_un_usuario_no_ve_confirma_ni_cancela_el_pago_de_otro(client):
    dueno, otro = cuenta_con_sesion(client), cuenta_con_sesion(client)
    mio = _pagar_ok(client, dueno.cab)
    assert client.get(f"/pagos/{mio['id']}", headers=otro.cab).status_code == 404
    assert client.post(f"/pagos/{mio['id']}/confirmar", headers=otro.cab).status_code == 404
    assert client.post(f"/pagos/{mio['id']}/cancelar", headers=otro.cab).status_code == 404
    assert client.get("/pagos", headers=otro.cab).json() == []
    assert _membresia(client, otro.cab)["activa"] is False
    assert client.get(f"/pagos/{mio['id']}", headers=dueno.cab).json()["estado"] == "pendiente", \
        "El intento ajeno no debe haber cambiado el pago del dueño"


def test_cp21_23_la_membresia_es_individual(client):
    dueno, otro = cuenta_con_sesion(client), cuenta_con_sesion(client)
    p = _pagar_ok(client, dueno.cab, "anual")
    client.post(f"/pagos/{p['id']}/confirmar", headers=dueno.cab)
    assert _membresia(client, dueno.cab)["activa"] is True
    assert _membresia(client, otro.cab)["activa"] is False


# --------------------------------------------------------------------------- flujo del pago
def test_cp21_30_un_pago_nace_pendiente_y_no_da_membresia_hasta_confirmarlo(client):
    cab = cuenta_con_sesion(client).cab
    pago = _pagar_ok(client, cab, "anual")
    assert pago["estado"] == "pendiente" and pago["valor"] == 99_900 and pago["meses"] == 12
    assert pago["simulado"] is True, "El pago es de demostración: debe decirlo"
    assert pago["membresia_hasta"] is None and re.fullmatch(r"[A-Z0-9\-]{6,20}", pago["referencia"])
    assert _membresia(client, cab)["activa"] is False


def test_cp21_31_confirmar_activa_la_membresia_por_los_meses_del_plan(client):
    cab = cuenta_con_sesion(client).cab
    pago = _pagar_ok(client, cab, "anual")
    r = client.post(f"/pagos/{pago['id']}/confirmar", headers=cab)
    assert r.status_code == 200 and r.json()["estado"] == "pagado" and r.json()["membresia_hasta"]
    m = _membresia(client, cab)
    assert m["activa"] is True and m["plan"] == "anual" and 360 <= m["dias_restantes"] <= 366
    assert client.get("/pagos", headers=cab).json()[0]["estado"] == "pagado"


def test_cp21_32_un_pago_no_se_confirma_ni_se_cancela_dos_veces(client):
    cab = cuenta_con_sesion(client).cab
    pago = _pagar_ok(client, cab, "mensual")
    assert client.post(f"/pagos/{pago['id']}/confirmar", headers=cab).status_code == 200
    assert client.post(f"/pagos/{pago['id']}/confirmar", headers=cab).status_code == 409
    assert client.post(f"/pagos/{pago['id']}/cancelar", headers=cab).status_code == 409
    assert 27 <= _membresia(client, cab)["dias_restantes"] <= 31, "Confirmar dos veces NO debe sumar otro mes"


def test_cp21_33_cancelar_un_pago_pendiente(client):
    cab = cuenta_con_sesion(client).cab
    pago = _pagar_ok(client, cab)
    r = client.post(f"/pagos/{pago['id']}/cancelar", headers=cab)
    assert r.status_code == 200 and r.json()["estado"] == "cancelado"
    assert client.post(f"/pagos/{pago['id']}/confirmar", headers=cab).status_code == 409
    assert _membresia(client, cab)["activa"] is False


def test_cp21_34_un_pago_nuevo_cancela_el_pendiente_anterior(client):
    cab = cuenta_con_sesion(client).cab
    m = _tarjeta(client, cab)
    p1, p2 = _pagar_ok(client, cab, "mensual", m), _pagar_ok(client, cab, "anual", m)
    assert client.get(f"/pagos/{p1['id']}", headers=cab).json()["estado"] == "cancelado"
    assert client.post(f"/pagos/{p1['id']}/confirmar", headers=cab).status_code == 409
    assert client.get(f"/pagos/{p2['id']}", headers=cab).json()["estado"] == "pendiente"


def test_cp21_35_un_pago_pendiente_vence_a_los_30_minutos(client):
    c = cuenta_con_sesion(client)
    pago = _pagar_ok(client, c.cab)
    consulta_db("UPDATE pagos_membresia SET expira_en = NOW() - INTERVAL '1 minute' WHERE id = %s", (pago["id"],))
    assert client.get(f"/pagos/{pago['id']}", headers=c.cab).json()["estado"] == "vencido"
    assert client.post(f"/pagos/{pago['id']}/confirmar", headers=c.cab).status_code == 409
    assert _membresia(client, c.cab)["activa"] is False


def test_cp21_36_plan_inventado_o_metodo_inexistente(client):
    cab = cuenta_con_sesion(client).cab
    m = _tarjeta(client, cab)
    assert client.post("/pagos", json={"plan": "gratis", "metodo_id": m["id"]}, headers=cab).status_code == 422
    assert client.post("/pagos", json={"plan": "mensual", "metodo_id": 99999999}, headers=cab).status_code == 404
    assert client.post("/pagos", json={"plan": "mensual"}, headers=cab).status_code == 422


def test_cp21_37_el_pago_conserva_el_precio_aunque_cambien_los_planes(client, monkeypatch):
    cab = cuenta_con_sesion(client).cab
    pago = _pagar_ok(client, cab, "mensual")
    monkeypatch.setitem(pagos.PLAN_POR_CODIGO["mensual"], "valor", pagos.Decimal("50000"))
    assert client.get(f"/pagos/{pago['id']}", headers=cab).json()["valor"] == 12_900


# --------------------------------------------------------------------------- membresía: suma y reactivación
def test_cp21_40_un_plan_nuevo_se_suma_al_tiempo_que_queda(client):
    cab = cuenta_con_sesion(client).cab
    m = _tarjeta(client, cab)
    p1 = _pagar_ok(client, cab, "mensual", m)
    client.post(f"/pagos/{p1['id']}/confirmar", headers=cab)
    antes = _membresia(client, cab)["dias_restantes"]
    p2 = _pagar_ok(client, cab, "semestral", m)
    client.post(f"/pagos/{p2['id']}/confirmar", headers=cab)
    despues = _membresia(client, cab)
    assert despues["plan"] == "semestral"
    assert despues["dias_restantes"] >= antes + 180, "No se deben perder los días que ya estaban pagados"


def test_cp21_41_una_membresia_vencida_se_reactiva_desde_hoy(client):
    c = cuenta_con_sesion(client)
    p = _pagar_ok(client, c.cab)
    client.post(f"/pagos/{p['id']}/confirmar", headers=c.cab)
    consulta_db("UPDATE membresias SET vence_en = NOW() - INTERVAL '3 days' WHERE usuario_id = (SELECT id FROM usuarios WHERE correo = %s)", (c.correo,))
    assert _membresia(client, c.cab)["activa"] is False
    p2 = _pagar_ok(client, c.cab)
    client.post(f"/pagos/{p2['id']}/confirmar", headers=c.cab)
    m = _membresia(client, c.cab)
    assert m["activa"] is True and 27 <= m["dias_restantes"] <= 31, "Debe contar desde hoy, no desde la fecha vencida"


# --------------------------------------------------------------------------- borrar un método de pago
def test_cp21_50_quitar_el_metodo_cancela_el_pago_pendiente_que_lo_usaba(client):
    cab = cuenta_con_sesion(client).cab
    m = _tarjeta(client, cab)
    p = _pagar_ok(client, cab, "mensual", m)
    assert client.delete(f"/pagos/metodos/{m['id']}", headers=cab).status_code == 204
    assert client.get(f"/pagos/{p['id']}", headers=cab).json()["estado"] == "cancelado"


def test_cp21_51_un_pago_pagado_conserva_como_se_pago_aunque_se_borre_el_metodo(client):
    cab = cuenta_con_sesion(client).cab
    m = _tarjeta(client, cab)
    p = _pagar_ok(client, cab, "mensual", m)
    client.post(f"/pagos/{p['id']}/confirmar", headers=cab)
    assert client.delete(f"/pagos/metodos/{m['id']}", headers=cab).status_code == 204
    ver = client.get(f"/pagos/{p['id']}", headers=cab).json()
    assert ver["estado"] == "pagado" and "4242" in ver["metodo"]


def test_cp21_52_al_borrar_al_usuario_se_borran_sus_pagos_y_metodos(client):
    """Derecho de supresión de datos (Ley 1581): nada de pagos queda huérfano."""
    c = cuenta_con_sesion(client)
    p = _pagar_ok(client, c.cab)
    client.post(f"/pagos/{p['id']}/confirmar", headers=c.cab)
    uid = consulta_db("SELECT id FROM usuarios WHERE correo = %s", (c.correo,))[0][0]
    consulta_db("DELETE FROM usuarios WHERE id = %s", (uid,))
    for tabla in ("metodos_pago", "membresias", "pagos_membresia"):
        assert consulta_db(f"SELECT COUNT(*) FROM {tabla} WHERE usuario_id = %s", (uid,))[0][0] == 0, tabla


# --------------------------------------------------------------------------- abuso
@pytest.mark.req("RNF-09")
def test_cp21_60_limite_de_pagos_por_hora(client):
    cab = cuenta_con_sesion(client).cab
    m = _tarjeta(client, cab)
    codigos = [_pagar(client, cab, "mensual", m).status_code for _ in range(pagos.MAX_PAGOS_HORA + 1)]
    assert codigos[:pagos.MAX_PAGOS_HORA] == [201] * pagos.MAX_PAGOS_HORA
    assert codigos[-1] == 429
