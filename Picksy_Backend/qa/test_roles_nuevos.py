"""
ROLES NUEVOS (RF-19, PROPUESTO por QA): premium, soporte, analista y moderador de tiendas.

No existe el rol 'invitado': el profesor exigió que nadie entre sin registrarse (ver roles.py).

  premium            sin límite diario de búsquedas (también quien tiene una membresía vigente)
  soporte            ve datos básicos, desbloquea cuentas y cierra sesiones; NO toca administradores
  analista           estadísticas agregadas, sin datos personales
  moderador_tiendas  activa o desactiva tiendas (una tienda desactivada no se consulta)
"""
import typing

import pytest

import config
from ayudas import (buscar, consulta_db, crear_cuenta, cuenta_con_sesion, id_de,
                    iniciar_sesion, login_paso1)
from mocks import producto

pytestmark = pytest.mark.req("RF-19")

NUEVOS = ["premium", "soporte", "analista", "moderador_tiendas"]
TODOS = ["usuario"] + NUEVOS + ["admin"]


def cuenta_con_rol(client, rol):
    """Cuenta con sesión y el rol pedido. El rol se asigna en la base de PRUEBA (como crear_admin.py)."""
    c = crear_cuenta(client)
    consulta_db("UPDATE usuarios SET rol = %s WHERE correo = %s", (rol, c.correo))
    r = iniciar_sesion(client, c.correo, c.clave, c.secreto)
    assert r.status_code == 200, r.text
    c.token = r.json()["token"]
    return c


@pytest.fixture
def limite(monkeypatch):
    """Fija el límite diario de las cuentas normales (el resto de las pruebas corre sin límite: ver conftest)."""
    def poner(n):
        monkeypatch.setattr(config, "BUSQUEDAS_DIARIAS_USUARIO", n)
    return poner


@pytest.fixture
def tiendas_activas():
    """Deja todas las tiendas activas al terminar, pase lo que pase en la prueba."""
    yield
    consulta_db("UPDATE tiendas SET activa = TRUE")


# ----------------------------------------------------------------------------- el esquema y el panel de admin
def test_cp19_20_los_roles_del_panel_coinciden_con_los_del_codigo():
    import admin
    import roles
    permitidos = typing.get_args(admin.RolEntrada.model_fields["rol"].annotation)
    assert set(permitidos) == set(roles.ROLES) and len(roles.ROLES) == 6
    assert "invitado" not in roles.ROLES, "Nadie entra sin registrarse: no existe el rol invitado"


def test_cp19_21_el_admin_puede_asignar_los_seis_roles_y_me_lo_refleja(client):
    from ayudas import admin_con_sesion
    admin = admin_con_sesion(client)
    otra = cuenta_con_sesion(client)
    for rol in TODOS:
        if rol == "admin":
            continue
        r = client.patch(f"/admin/usuarios/{id_de(otra.correo)}/rol", json={"rol": rol}, headers=admin.cab)
        assert r.status_code == 200, r.text
        assert client.get("/auth/me", headers=otra.cab).json()["rol"] == rol


def test_cp19_22_un_rol_inventado_se_rechaza_en_la_api_y_en_la_base(client):
    from ayudas import admin_con_sesion
    admin = admin_con_sesion(client)
    otra = cuenta_con_sesion(client)
    r = client.patch(f"/admin/usuarios/{id_de(otra.correo)}/rol", json={"rol": "invitado"}, headers=admin.cab)
    assert r.status_code == 422
    with pytest.raises(Exception):
        consulta_db("UPDATE usuarios SET rol = 'invitado' WHERE correo = %s", (otra.correo,))
    assert consulta_db("SELECT rol FROM usuarios WHERE correo = %s", (otra.correo,)) == [("usuario",)]


# ----------------------------------------------------------------------------- quién puede entrar a qué
RUTAS = [
    ("/soporte/usuarios", {"soporte", "admin"}),
    ("/analista/resumen", {"analista", "admin"}),
    ("/moderacion/tiendas", {"moderador_tiendas", "admin"}),
    ("/admin/usuarios", {"admin"}),
]


@pytest.mark.parametrize("ruta,permitidos", RUTAS)
def test_cp19_23_cada_rol_solo_entra_a_lo_suyo_y_el_admin_a_todo(client, ruta, permitidos):
    for rol in TODOS:
        c = cuenta_con_rol(client, rol)
        esperado = 200 if rol in permitidos else 403
        r = client.get(ruta, headers=c.cab)
        assert r.status_code == esperado, f"{rol} en {ruta}: {r.status_code} {r.text[:120]}"


@pytest.mark.parametrize("ruta", [r for r, _ in RUTAS])
def test_cp19_24_sin_sesion_todas_las_rutas_de_roles_dan_401(client, ruta):
    assert client.get(ruta).status_code == 401


def test_cp19_25_soporte_no_puede_borrar_ni_cambiar_roles(client):
    s = cuenta_con_rol(client, "soporte")
    otra = cuenta_con_sesion(client)
    uid = id_de(otra.correo)
    assert client.delete(f"/admin/usuarios/{uid}", headers=s.cab).status_code == 403
    assert client.patch(f"/admin/usuarios/{uid}/rol", json={"rol": "admin"}, headers=s.cab).status_code == 403
    assert client.patch(f"/admin/usuarios/{id_de(s.correo)}/rol", json={"rol": "admin"}, headers=s.cab).status_code == 403
    assert consulta_db("SELECT 1 FROM usuarios WHERE id = %s", (uid,))


# ----------------------------------------------------------------------------- premium y el límite diario
def test_cp19_30_un_usuario_normal_se_topa_con_el_limite_y_recibe_429(client, tiendas, limite, termino):
    limite(3)
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000))
    c = cuenta_con_sesion(client)
    for _ in range(3):
        assert buscar(client, termino, 900_000, c.cab).status_code == 200
    r = buscar(client, termino, 900_000, c.cab)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    assert "límite" in r.json()["error"]["mensaje"].lower() or "límite" in str(r.json()).lower()
    me = client.get("/auth/me", headers=c.cab).json()
    assert (me["premium"], me["limite_diario"], me["busquedas_hoy"], me["busquedas_restantes"]) == (False, 3, 3, 0)


def test_cp19_31_un_premium_y_el_personal_no_tienen_limite(client, tiendas, limite, termino):
    limite(2)
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000))
    for rol in ["premium", "soporte", "analista", "moderador_tiendas", "admin"]:
        c = cuenta_con_rol(client, rol)
        for _ in range(4):
            assert buscar(client, termino, 900_000, c.cab).status_code == 200, rol
        me = client.get("/auth/me", headers=c.cab).json()
        assert me["limite_diario"] is None and me["busquedas_restantes"] is None
        assert me["premium"] is (rol == "premium")


def test_cp19_32_una_membresia_vigente_quita_el_limite_y_una_vencida_no(client, tiendas, limite, termino):
    limite(2)
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000))
    vigente, vencida = cuenta_con_sesion(client), cuenta_con_sesion(client)
    consulta_db("INSERT INTO membresias (usuario_id, plan, vence_en) VALUES (%s, 'mensual', NOW() + INTERVAL '30 days')",
                (id_de(vigente.correo),))
    consulta_db("INSERT INTO membresias (usuario_id, plan, vence_en) VALUES (%s, 'mensual', NOW() - INTERVAL '1 day')",
                (id_de(vencida.correo),))
    for _ in range(4):
        assert buscar(client, termino, 900_000, vigente.cab).status_code == 200
    assert client.get("/auth/me", headers=vigente.cab).json()["premium"] is True
    assert buscar(client, termino, 900_000, vencida.cab).status_code == 200
    assert buscar(client, termino, 900_000, vencida.cab).status_code == 200
    assert buscar(client, termino, 900_000, vencida.cab).status_code == 429
    assert client.get("/auth/me", headers=vencida.cab).json()["premium"] is False


def test_cp19_33_borrar_el_historial_no_reinicia_el_contador(client, tiendas, limite, termino):
    limite(2)
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000))
    c = cuenta_con_sesion(client)
    assert buscar(client, termino, 900_000, c.cab).status_code == 200
    assert buscar(client, termino + " uno", 900_000, c.cab).status_code == 200
    assert client.delete("/historial", headers=c.cab).status_code in (200, 204)
    assert buscar(client, termino + " dos", 900_000, c.cab).status_code == 429


def test_cp19_34_una_peticion_invalida_no_gasta_una_busqueda(client, tiendas, limite, termino):
    limite(1)
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000))
    c = cuenta_con_sesion(client)
    assert buscar(client, "a", 900_000, c.cab).status_code == 422
    assert buscar(client, termino, -5, c.cab).status_code == 422
    assert buscar(client, termino, 900_000, c.cab, tiendas="TiendaQueNoExiste").status_code == 400
    assert buscar(client, termino, 900_000, c.cab).status_code == 200


def test_cp19_35_limite_cero_significa_sin_limite_para_todos(client, tiendas, limite, termino):
    limite(0)
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000))
    c = cuenta_con_sesion(client)
    for _ in range(5):
        assert buscar(client, termino, 900_000, c.cab).status_code == 200
    assert client.get("/auth/me", headers=c.cab).json()["limite_diario"] is None


def test_cp19_36_dos_busquedas_a_la_vez_no_pasan_del_tope(client, tiendas, limite, termino):
    import threading
    limite(3)
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000))
    c = cuenta_con_sesion(client)
    codigos = []

    def una():
        codigos.append(buscar(client, termino, 900_000, c.cab).status_code)

    hilos = [threading.Thread(target=una) for _ in range(8)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert codigos.count(200) == 3 and codigos.count(429) == 5, codigos


# ----------------------------------------------------------------------------- soporte
def test_cp19_40_soporte_busca_usuarios_por_correo_y_no_ve_secretos(client):
    s = cuenta_con_rol(client, "soporte")
    otra = cuenta_con_sesion(client)
    r = client.get("/soporte/usuarios", params={"q": otra.correo.upper()}, headers=s.cab)
    assert r.status_code == 200
    assert [u["correo"] for u in r.json()] == [otra.correo]
    assert r.headers["X-Total-Count"] == "1"
    texto = r.text.lower()
    for prohibido in ("contrasena", "hash", "totp_secreto", "secreto", "recuperacion"):
        assert prohibido not in texto
    ficha = client.get(f"/soporte/usuarios/{id_de(otra.correo)}", headers=s.cab)
    assert ficha.status_code == 200
    d = ficha.json()
    assert d["correo"] == otra.correo and d["membresia"]["activa"] is False and d["sesiones_abiertas"] >= 1
    for prohibido in ("contrasena", "hash", "totp_secreto", "secreto", "recuperacion", otra.clave):
        assert prohibido not in ficha.text.lower()
    assert client.get("/soporte/usuarios/99999999", headers=s.cab).status_code == 404


def test_cp19_41_soporte_desbloquea_una_cuenta_bloqueada_por_intentos(client):
    s = cuenta_con_rol(client, "soporte")
    victima = crear_cuenta(client)
    for _ in range(config.LOGIN_MAX_FALLOS):
        assert client.post("/auth/login", json={"correo": victima.correo, "contrasena": "Mala-clave-1"}).status_code == 401
    assert client.post("/auth/login", json={"correo": victima.correo, "contrasena": victima.clave}).status_code == 429
    r = client.post(f"/soporte/usuarios/{id_de(victima.correo)}/desbloquear", headers=s.cab)
    assert r.status_code == 200 and r.json()["desbloqueado"] is True
    assert login_paso1(client, victima.correo, victima.clave).status_code == 200


def test_cp19_42_soporte_cierra_las_sesiones_de_un_usuario(client):
    s = cuenta_con_rol(client, "soporte")
    victima = cuenta_con_sesion(client)
    assert client.get("/auth/me", headers=victima.cab).status_code == 200
    r = client.post(f"/soporte/usuarios/{id_de(victima.correo)}/cerrar-sesiones", headers=s.cab)
    assert r.status_code == 200 and r.json()["sesiones_cerradas"] >= 1
    assert client.get("/auth/me", headers=victima.cab).status_code == 401
    assert client.get("/auth/me", headers=s.cab).status_code == 200, "La sesión de soporte no se toca"


def test_cp19_43_soporte_no_puede_tocar_a_un_administrador_pero_otro_admin_si(client):
    s = cuenta_con_rol(client, "soporte")
    jefe = cuenta_con_rol(client, "admin")
    otro_admin = cuenta_con_rol(client, "admin")
    uid = id_de(jefe.correo)
    assert client.post(f"/soporte/usuarios/{uid}/desbloquear", headers=s.cab).status_code == 403
    assert client.post(f"/soporte/usuarios/{uid}/cerrar-sesiones", headers=s.cab).status_code == 403
    assert client.get("/auth/me", headers=jefe.cab).status_code == 200
    assert client.post(f"/soporte/usuarios/{uid}/desbloquear", headers=otro_admin.cab).status_code == 200


# ----------------------------------------------------------------------------- analista
def test_cp19_50_el_analista_ve_el_resumen_y_el_contador_de_busquedas_sube(client, tiendas, limite, termino):
    limite(0)
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000))
    a = cuenta_con_rol(client, "analista")
    antes = client.get("/analista/resumen", headers=a.cab).json()
    assert set(antes["usuarios_por_rol"]) == set(TODOS)
    assert len(antes["busquedas_por_dia"]) == 14
    assert antes["usuarios_total"] == sum(antes["usuarios_por_rol"].values())
    c = cuenta_con_sesion(client)
    assert buscar(client, termino, 900_000, c.cab).status_code == 200
    despues = client.get("/analista/resumen", headers=a.cab).json()
    assert despues["busquedas_hoy"] == antes["busquedas_hoy"] + 1
    assert despues["busquedas_por_dia"][-1]["busquedas"] == despues["busquedas_hoy"]


def test_cp19_51_el_analista_nunca_recibe_datos_personales(client, tiendas, limite, termino):
    limite(0)
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000))
    a = cuenta_con_rol(client, "analista")
    c = cuenta_con_sesion(client)
    assert buscar(client, termino, 900_000, c.cab).status_code == 200
    for ruta in ("/analista/resumen", "/analista/busquedas-populares", "/analista/tiendas-ganadoras"):
        r = client.get(ruta, headers=a.cab)
        assert r.status_code == 200, ruta
        assert "@" not in r.text, f"{ruta} no debe mostrar correos"
        assert "usuario_id" not in r.text and "correo" not in r.text


def test_cp19_52_busquedas_populares_y_tiendas_ganadoras(client, tiendas, termino, limite):
    limite(0)
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000))
    a = cuenta_con_rol(client, "analista")
    c = cuenta_con_sesion(client)
    # Solo se borra el historial de las cuentas de QA (qa_*@test.com), para que el ranking no dependa de otras pruebas.
    consulta_db("DELETE FROM historial_busquedas WHERE usuario_id IN (SELECT id FROM usuarios WHERE correo LIKE %s)",
                ("qa\\_%@test.com",))
    for presupuesto in (900_000, 800_000, 700_000):      # 3 veces el mismo término (con distinto presupuesto)
        assert buscar(client, termino, presupuesto, c.cab).status_code == 200
    pop = client.get("/analista/busquedas-populares", params={"dias": 7, "limite": 50}, headers=a.cab).json()
    assert pop["busquedas"][0] == {"termino": termino.lower(), "veces": 3}
    gan = client.get("/analista/tiendas-ganadoras", params={"dias": 7, "limite": 50}, headers=a.cab).json()
    assert "Éxito" in {x["tienda"] for x in gan["tiendas"]}
    assert client.get("/analista/busquedas-populares", params={"dias": 0}, headers=a.cab).status_code == 422
    assert client.get("/analista/tiendas-ganadoras", params={"limite": 500}, headers=a.cab).status_code == 422


# ----------------------------------------------------------------------------- moderador de tiendas
def test_cp19_60_el_moderador_lista_solo_las_tiendas_que_picksy_consulta(client):
    import buscador
    m = cuenta_con_rol(client, "moderador_tiendas")
    r = client.get("/moderacion/tiendas", headers=m.cab)
    assert r.status_code == 200
    nombres = {t["nombre"] for t in r.json()}
    assert nombres == {n for n in buscador.NOMBRES if n in nombres} and len(nombres) >= 9
    assert all(t["activa"] is True for t in r.json())


def test_cp19_61_una_tienda_desactivada_no_se_consulta_ni_sale_en_resultados(client, tiendas, tiendas_activas, limite, termino):
    limite(0)
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000))
    tiendas.poner("Alkosto", producto("Alkosto", "Nevera", 460_000))
    m = cuenta_con_rol(client, "moderador_tiendas")
    c = cuenta_con_sesion(client)
    exito = next(t for t in client.get("/moderacion/tiendas", headers=m.cab).json() if t["nombre"] == "Éxito")

    r = client.patch(f"/moderacion/tiendas/{exito['id']}", json={"activa": False}, headers=m.cab)
    assert r.status_code == 200 and r.json()["activa"] is False
    assert "Éxito" not in {t["nombre"] for t in client.get("/tiendas", headers=c.cab).json()}
    r = buscar(client, termino, 900_000, c.cab)
    assert r.status_code == 200
    assert {o["tienda"] for o in r.json()["viables"]} == {"Alkosto"}
    assert "Éxito" not in {t for t, _ in tiendas.llamadas}, "Una tienda desactivada no debe consultarse"

    # pedirla expresamente tampoco la trae
    r = buscar(client, termino, 900_000, c.cab, tiendas="Éxito")
    assert r.status_code == 503

    # al activarla de nuevo vuelve
    assert client.patch(f"/moderacion/tiendas/{exito['id']}", json={"activa": True}, headers=m.cab).status_code == 200
    assert "Éxito" in {t["nombre"] for t in client.get("/tiendas", headers=c.cab).json()}


def test_cp19_62_si_la_respuesta_venia_de_la_cache_la_tienda_desactivada_tampoco_sale(client, tiendas, tiendas_activas, limite, termino):
    limite(0)
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000))
    tiendas.poner("Alkosto", producto("Alkosto", "Nevera", 460_000))
    m = cuenta_con_rol(client, "moderador_tiendas")
    c = cuenta_con_sesion(client)
    primera = buscar(client, termino, 900_000, c.cab).json()
    assert {o["tienda"] for o in primera["viables"]} == {"Éxito", "Alkosto"}
    exito = next(t for t in client.get("/moderacion/tiendas", headers=m.cab).json() if t["nombre"] == "Éxito")
    client.patch(f"/moderacion/tiendas/{exito['id']}", json={"activa": False}, headers=m.cab)
    segunda = buscar(client, termino, 900_000, c.cab).json()
    assert {o["tienda"] for o in segunda["viables"]} == {"Alkosto"}


def test_cp19_63_el_moderador_no_puede_tocar_tiendas_inexistentes_ni_sin_permiso(client):
    m = cuenta_con_rol(client, "moderador_tiendas")
    normal = cuenta_con_sesion(client)
    assert client.patch("/moderacion/tiendas/99999999", json={"activa": False}, headers=m.cab).status_code == 404
    assert client.patch("/moderacion/tiendas/1", json={"activa": False}, headers=normal.cab).status_code == 403
    assert client.patch("/moderacion/tiendas/1", json={"activa": False}).status_code == 401
    assert client.patch("/moderacion/tiendas/1", json={"activa": "quizas"}, headers=m.cab).status_code == 422
    assert consulta_db("SELECT COUNT(*) FROM tiendas WHERE NOT activa") == [(0,)]
