"""
ROLES Y PANEL DE ADMINISTRADOR (RF-19, PROPUESTO por QA: el ERS no lo define). Nuevo en la v3.

Roles: 'usuario' (usa Picksy) y 'admin' (además lista y elimina usuarios y cambia roles).
Ninguna ruta pública permite que alguien se vuelva admin: el primero se crea con crear_admin.py en el servidor.
"""
import threading

import pytest

from ayudas import (CLAVE_OK, admin_con_sesion, buscar_ok, cab, codigo_totp, confirmar_registro, consulta_db,
                    correo_nuevo, crear_cuenta, crear_carrito, cuenta_con_sesion, id_de, usuario_con_sesion)
from mocks import producto

pytestmark = pytest.mark.req("RF-19")


# ----------------------------------------------------------------------------- quién puede entrar
def test_cp19_1_un_usuario_normal_recibe_403_en_todo_el_panel(client):
    c = cuenta_con_sesion(client)
    otro = crear_cuenta(client)
    uid = id_de(otro.correo)
    assert client.get("/admin/usuarios", headers=c.cab).status_code == 403
    assert client.delete(f"/admin/usuarios/{uid}", headers=c.cab).status_code == 403
    assert client.patch(f"/admin/usuarios/{uid}/rol", json={"rol": "admin"}, headers=c.cab).status_code == 403
    assert consulta_db("SELECT 1 FROM usuarios WHERE id = %s", (uid,)), "No se debe haber borrado nada"


def test_cp19_1b_un_usuario_normal_no_puede_ascenderse_a_si_mismo(client):
    c = cuenta_con_sesion(client)
    r = client.patch(f"/admin/usuarios/{id_de(c.correo)}/rol", json={"rol": "admin"}, headers=c.cab)
    assert r.status_code == 403
    assert client.get("/auth/me", headers=c.cab).json()["rol"] == "usuario"


def test_cp19_1c_sin_sesion_el_panel_da_401(client):
    assert client.get("/admin/usuarios").status_code == 401
    assert client.delete("/admin/usuarios/1").status_code == 401
    assert client.patch("/admin/usuarios/1/rol", json={"rol": "admin"}).status_code == 401


def test_cp19_2_toda_cuenta_nueva_nace_con_rol_usuario_aunque_intente_mandar_otro(client):
    """Asignación masiva (mass assignment): el cuerpo del registro no puede traer el rol."""
    correo = correo_nuevo()
    r = client.post("/auth/registro", json={"correo": correo, "contrasena": CLAVE_OK, "rol": "admin"})
    assert r.status_code == 201
    d = r.json()
    assert confirmar_registro(client, d["token_registro"], codigo_totp(d["secreto"])).status_code == 201
    assert consulta_db("SELECT rol FROM usuarios WHERE correo = %s", (correo,)) == [("usuario",)]


def test_cp19_2b_la_base_no_acepta_un_rol_inventado(client):
    c = crear_cuenta(client)
    with pytest.raises(Exception):
        consulta_db("UPDATE usuarios SET rol = 'superman' WHERE correo = %s", (c.correo,))


# ----------------------------------------------------------------------------- lo que hace el admin
def test_cp19_3_el_admin_lista_usuarios_sin_exponer_secretos(client):
    admin = admin_con_sesion(client)
    otro = crear_cuenta(client)
    r = client.get("/admin/usuarios", headers=admin.cab)
    assert r.status_code == 200
    filas = {f["correo"]: f for f in r.json()}
    assert filas[otro.correo]["rol"] == "usuario" and filas[otro.correo]["dos_factores"] is True
    assert filas[admin.correo]["rol"] == "admin"
    assert set(filas[otro.correo]) == {"id", "correo", "rol", "dos_factores", "creado_en"}
    for secreto in ("$2b$", otro.secreto, "gAAAA", "contrasena", "totp_secreto"):
        assert secreto not in r.text


def test_cp19_4_eliminar_usuario_borra_sus_datos_y_cierra_su_sesion(client, tiendas, termino):
    admin = admin_con_sesion(client)
    victima = cuenta_con_sesion(client)
    tiendas.poner("Éxito", producto("Éxito", "TV", 100_000))
    buscar_ok(client, termino, 500_000, victima.cab)                       # historial
    crear_carrito(client, victima.cab, 1000)                               # carrito
    uid = id_de(victima.correo)
    r = client.delete(f"/admin/usuarios/{uid}", headers=admin.cab)
    assert r.status_code == 200 and r.json() == {"eliminado": uid, "correo": victima.correo}
    assert client.get("/auth/me", headers=victima.cab).status_code == 401, "Su sesión debe dejar de servir"
    for tabla in ("historial_busquedas", "carritos", "sesiones", "codigos_recuperacion"):
        assert consulta_db(f"SELECT COUNT(*) FROM {tabla} WHERE usuario_id = %s", (uid,))[0][0] == 0, tabla


def test_cp19_4b_eliminar_a_alguien_que_no_existe_da_404(client):
    admin = admin_con_sesion(client)
    assert client.delete("/admin/usuarios/999999999", headers=admin.cab).status_code == 404


def test_cp19_5_el_admin_no_puede_eliminarse_ni_cambiarse_el_rol_a_si_mismo(client):
    admin = admin_con_sesion(client)
    uid = id_de(admin.correo)
    assert client.delete(f"/admin/usuarios/{uid}", headers=admin.cab).status_code == 400
    assert client.patch(f"/admin/usuarios/{uid}/rol", json={"rol": "usuario"}, headers=admin.cab).status_code == 400
    assert client.get("/auth/me", headers=admin.cab).json()["rol"] == "admin"


def test_cp19_6_cambiar_rol_ascender_y_degradar(client):
    admin = admin_con_sesion(client)
    otro = cuenta_con_sesion(client)
    uid = id_de(otro.correo)
    r = client.patch(f"/admin/usuarios/{uid}/rol", json={"rol": "admin"}, headers=admin.cab)
    assert r.status_code == 200 and r.json() == {"id": uid, "correo": otro.correo, "rol": "admin"}
    assert client.get("/auth/me", headers=otro.cab).json()["rol"] == "admin", "El rol se aplica a su sesión ya abierta"
    assert client.get("/admin/usuarios", headers=otro.cab).status_code == 200
    client.patch(f"/admin/usuarios/{uid}/rol", json={"rol": "usuario"}, headers=admin.cab)
    assert client.get("/admin/usuarios", headers=otro.cab).status_code == 403


@pytest.mark.parametrize("rol", ["root", "ADMIN", "", None, 1])
def test_cp19_6b_rol_invalido_da_422(client, rol):
    admin = admin_con_sesion(client)
    uid = id_de(crear_cuenta(client).correo)
    assert client.patch(f"/admin/usuarios/{uid}/rol", json={"rol": rol}, headers=admin.cab).status_code == 422


def test_cp19_6c_cambiar_el_rol_de_alguien_que_no_existe_da_404(client):
    admin = admin_con_sesion(client)
    assert client.patch("/admin/usuarios/999999999/rol", json={"rol": "admin"}, headers=admin.cab).status_code == 404


def test_cp19_7_dos_admins_que_se_eliminan_a_la_vez_nunca_dejan_el_sistema_sin_administradores(client):
    """Carrera: A elimina a B y B elimina a A en el mismo instante. La API bloquea las filas de admins:
    exactamente uno de los dos borrados debe funcionar y el otro recibir 409 ('último administrador')."""
    a, b = admin_con_sesion(client), admin_con_sesion(client)
    ida, idb = id_de(a.correo), id_de(b.correo)
    # Los administradores de OTRAS pruebas (qa_*) se degradan para que solo existan A y B; si hubiera administradores
    # reales (no qa_*) no se tocan y la prueba se omite: la regla "último admin" no se puede disparar con ellos.
    consulta_db("UPDATE usuarios SET rol = 'usuario' WHERE correo LIKE 'qa\\_%%@test.com' AND id NOT IN (%s, %s)", (ida, idb))
    if consulta_db("SELECT COUNT(*) FROM usuarios WHERE rol = 'admin' AND id NOT IN (%s, %s)", (ida, idb))[0][0]:
        pytest.skip("OMITIDA: hay administradores reales en la base; esta carrera solo se puede probar sin ellos")
    resultados, tope = {}, threading.Barrier(2)

    def borrar(nombre, quien, objetivo):
        tope.wait()
        resultados[nombre] = client.delete(f"/admin/usuarios/{objetivo}", headers=quien.cab).status_code

    hilos = [threading.Thread(target=borrar, args=("a_borra_b", a, idb)),
             threading.Thread(target=borrar, args=("b_borra_a", b, ida))]
    [h.start() for h in hilos]
    [h.join(30) for h in hilos]
    quedan = consulta_db("SELECT COUNT(*) FROM usuarios WHERE rol = 'admin'")[0][0]
    assert quedan == 1, f"Debe quedar exactamente 1 administrador, quedan {quedan}: {resultados}"
    # El que pierde la carrera recibe 409 (último admin) o 401 (su sesión ya no existe porque el otro lo borró primero).
    assert sorted(resultados.values()) in ([200, 401], [200, 409]), resultados
