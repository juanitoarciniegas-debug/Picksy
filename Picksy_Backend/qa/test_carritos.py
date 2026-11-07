"""
CARRITOS (RF-13): el usuario arma una lista de productos y le da una prioridad a cada uno.
Nuevo en la v3 (en la v1/v2 solo existían las tablas, sin rutas).

El ERS no define la escala de prioridad (ambigüedad A-03): la API usa 1 a 5 (5 = indispensable); eso se
verifica aquí como COMPORTAMIENTO ACTUAL. Si Requerimientos define otra escala, se ajustan los límites.
"""
import pytest

from ayudas import (agregar_item, agregar_item_ok, buscar_ok, consulta_db, crear_carrito,
                    usuario_con_sesion)
from mocks import producto

pytestmark = pytest.mark.req("RF-13")


@pytest.fixture
def u(client):
    """(cabeceras de un usuario nuevo)"""
    return usuario_con_sesion(client)[1]


# ----------------------------------------------------------------------------- crear / listar / ver
def test_cp13_1_crear_carrito_devuelve_el_resumen_vacio(client, u):
    c = crear_carrito(client, u, 800_000, "  Mi   cuarto  ")
    assert c["nombre"] == "Mi cuarto", "Los espacios sobrantes se limpian"
    assert c["presupuesto"] == 800_000 and c["productos"] == 0 and c["total"] == 0
    assert c["optimizado"] is False and c["prioridad_total"] == 0 and c["id"] > 0


def test_cp13_1b_el_nombre_es_opcional(client, u):
    assert crear_carrito(client, u, 1000)["nombre"] is None


@pytest.mark.parametrize("cuerpo", [
    {}, {"presupuesto": 0}, {"presupuesto": -1}, {"presupuesto": "abc"}, {"presupuesto": None},
    {"presupuesto": 1_000_000_001},                      # tope: mil millones
    {"presupuesto": 1000, "nombre": "x" * 101},
])
def test_cp13_1c_datos_invalidos_del_carrito_dan_422(client, u, cuerpo):
    assert client.post("/carritos", json=cuerpo, headers=u).status_code == 422


@pytest.mark.parametrize("presupuesto", [0.01, 1_000_000_000])
def test_cp13_1d_limites_validos_del_presupuesto(client, u, presupuesto):
    assert client.post("/carritos", json={"presupuesto": presupuesto}, headers=u).status_code == 201


def test_cp13_1e_presupuesto_infinito_o_nan_se_rechaza(client, u):
    for malo in ("Infinity", "NaN"):
        r = client.post("/carritos", content=f'{{"presupuesto": {malo}}}', headers={**u, "Content-Type": "application/json"})
        assert r.status_code == 422, malo


def test_cp13_2_listar_muestra_solo_los_carritos_propios_el_mas_reciente_primero(client):
    _, a = usuario_con_sesion(client)
    _, b = usuario_con_sesion(client)
    c1, c2 = crear_carrito(client, a, 1000, "uno"), crear_carrito(client, a, 2000, "dos")
    crear_carrito(client, b, 3000, "de otro")
    ids = [c["id"] for c in client.get("/carritos", headers=a).json()]
    assert ids == [c2["id"], c1["id"]]


def test_cp13_2b_ver_un_carrito_trae_sus_productos(client, u):
    c = crear_carrito(client, u, 1_000_000)
    agregar_item_ok(client, u, c["id"], 100_000, 4)
    d = client.get(f"/carritos/{c['id']}", headers=u).json()
    assert d["productos"] == 1 and len(d["items"]) == 1 and d["items"][0]["prioridad"] == 4


def test_cp13_3_el_carrito_de_otro_usuario_es_invisible_y_da_el_mismo_404_que_uno_inexistente(client):
    _, a = usuario_con_sesion(client)
    _, b = usuario_con_sesion(client)
    c = crear_carrito(client, a, 1000)
    item = agregar_item_ok(client, a, c["id"], 100)
    ajeno = client.get(f"/carritos/{c['id']}", headers=b)
    inexistente = client.get("/carritos/999999999", headers=b)
    assert ajeno.status_code == inexistente.status_code == 404
    assert ajeno.json() == inexistente.json(), "No debe revelar si el carrito existe"
    # y tampoco se puede tocar de ninguna forma
    assert client.patch(f"/carritos/{c['id']}", json={"nombre": "mío"}, headers=b).status_code == 404
    assert client.delete(f"/carritos/{c['id']}", headers=b).status_code == 404
    assert agregar_item(client, b, c["id"], 50).status_code == 404
    assert client.patch(f"/carritos/{c['id']}/items/{item['id']}", json={"prioridad": 1}, headers=b).status_code == 404
    assert client.delete(f"/carritos/{c['id']}/items/{item['id']}", headers=b).status_code == 404
    assert client.post(f"/carritos/{c['id']}/optimizar", headers=b).status_code == 404
    # el dueño sigue viendo todo intacto
    d = client.get(f"/carritos/{c['id']}", headers=a).json()
    assert d["nombre"] is None and d["items"][0]["prioridad"] == 3


def test_cp13_3b_el_id_no_numerico_da_422(client, u):
    assert client.get("/carritos/abc", headers=u).status_code == 422


# ----------------------------------------------------------------------------- editar / eliminar
def test_cp13_4_editar_nombre_y_presupuesto(client, u):
    c = crear_carrito(client, u, 1000, "viejo")
    d = client.patch(f"/carritos/{c['id']}", json={"nombre": "nuevo", "presupuesto": 5000}, headers=u).json()
    assert (d["nombre"], d["presupuesto"]) == ("nuevo", 5000)
    solo_nombre = client.patch(f"/carritos/{c['id']}", json={"nombre": "otro"}, headers=u).json()
    assert (solo_nombre["nombre"], solo_nombre["presupuesto"]) == ("otro", 5000), "Lo que no se manda no cambia"


@pytest.mark.parametrize("cuerpo", [{"presupuesto": 0}, {"presupuesto": -5}, {"nombre": "x" * 101}])
def test_cp13_4b_edicion_invalida_da_422_y_no_cambia_nada(client, u, cuerpo):
    c = crear_carrito(client, u, 1000, "intacto")
    assert client.patch(f"/carritos/{c['id']}", json=cuerpo, headers=u).status_code == 422
    d = client.get(f"/carritos/{c['id']}", headers=u).json()
    assert (d["nombre"], d["presupuesto"]) == ("intacto", 1000)


def test_cp13_5_eliminar_carrito_borra_tambien_sus_productos(client, u):
    c = crear_carrito(client, u, 1000)
    item = agregar_item_ok(client, u, c["id"], 100)
    assert client.delete(f"/carritos/{c['id']}", headers=u).status_code == 204
    assert client.get(f"/carritos/{c['id']}", headers=u).status_code == 404
    assert client.delete(f"/carritos/{c['id']}", headers=u).status_code == 404
    assert consulta_db("SELECT COUNT(*) FROM carrito_items WHERE id = %s", (item["id"],))[0][0] == 0


def test_cp13_5b_eliminar_un_carrito_no_borra_el_producto_del_catalogo(client, u):
    c = crear_carrito(client, u, 1000)
    item = agregar_item_ok(client, u, c["id"], 100)
    client.delete(f"/carritos/{c['id']}", headers=u)
    assert consulta_db("SELECT COUNT(*) FROM productos WHERE url = %s", (item["url"],))[0][0] == 1


def test_cp13_6_maximo_30_carritos_por_usuario(client, u):
    for _ in range(30):
        crear_carrito(client, u, 1000)
    r = client.post("/carritos", json={"presupuesto": 1000}, headers=u)
    assert r.status_code == 409 and "30" in r.json()["detail"]


# ----------------------------------------------------------------------------- productos del carrito
def test_cp13_7_agregar_producto_con_prioridad(client, u):
    c = crear_carrito(client, u, 1_000_000)
    item = agregar_item_ok(client, u, c["id"], 250_000, 5, envio=15_000, nombre="Nevera", tienda="Alkosto")
    assert item["tienda"] == "Alkosto" and item["nombre"] == "Nevera" and item["prioridad"] == 5
    assert item["precio_total"] == 265_000, "El total del producto es precio + envío"
    assert item["incluido"] is False and item["id"] > 0


def test_cp13_7b_la_tienda_no_distingue_mayusculas(client, u):
    c = crear_carrito(client, u, 1000)
    assert agregar_item(client, u, c["id"], 100, tienda="éxito").status_code == 201
    assert agregar_item(client, u, c["id"], 100, tienda="ALKOSTO").status_code == 201


def test_cp13_7c_sin_envio_el_total_es_el_precio(client, u):
    c = crear_carrito(client, u, 1000)
    assert agregar_item_ok(client, u, c["id"], 123.45)["precio_total"] == 123.45


@pytest.mark.parametrize("cambio", [
    {"prioridad": 0}, {"prioridad": 6}, {"prioridad": -1}, {"prioridad": 2.5}, {"prioridad": "alta"}, {"prioridad": None},
    {"precio": -1}, {"precio": "gratis"}, {"envio": -1},
    {"url": "ftp://qa.test/x"}, {"url": "no es un enlace"}, {"url": "http://"},
    {"nombre": ""}, {"tienda": ""}, {"nombre": "x" * 501},
])
def test_cp13_8_producto_con_datos_invalidos_da_422(client, u, cambio):
    c = crear_carrito(client, u, 1000)
    cuerpo = {"tienda": "Éxito", "nombre": "Prod", "url": "https://qa.test/valido", "precio": 100, "prioridad": 3, **cambio}
    assert client.post(f"/carritos/{c['id']}/items", json=cuerpo, headers=u).status_code == 422, cambio


@pytest.mark.parametrize("prioridad", [1, 5])
def test_cp13_8b_prioridades_en_los_limites_se_aceptan(client, u, prioridad):
    c = crear_carrito(client, u, 1000)
    assert agregar_item(client, u, c["id"], 100, prioridad).status_code == 201


def test_cp13_9_tienda_desconocida_da_400(client, u):
    c = crear_carrito(client, u, 1000)
    r = agregar_item(client, u, c["id"], 100, tienda="Tienda Que No Existe")
    assert r.status_code == 400


def test_cp13_9b_el_mismo_producto_dos_veces_da_409(client, u):
    c = crear_carrito(client, u, 1000)
    url = "https://qa.test/carrito/repetido"
    assert agregar_item(client, u, c["id"], 100, url=url).status_code == 201
    assert agregar_item(client, u, c["id"], 100, url=url).status_code == 409


def test_cp13_9c_el_mismo_producto_si_puede_estar_en_dos_carritos_distintos(client, u):
    a, b = crear_carrito(client, u, 1000), crear_carrito(client, u, 1000)
    url = "https://qa.test/carrito/compartido"
    assert agregar_item(client, u, a["id"], 100, url=url).status_code == 201
    assert agregar_item(client, u, b["id"], 100, url=url).status_code == 201


def test_cp13_10_maximo_50_productos_por_carrito(client, u):
    c = crear_carrito(client, u, 1_000_000)
    for _ in range(50):
        assert agregar_item(client, u, c["id"], 10).status_code == 201
    r = agregar_item(client, u, c["id"], 10)
    assert r.status_code == 409 and "50" in r.json()["detail"]


def test_cp13_11_el_precio_sale_de_la_base_no_de_lo_que_manda_el_navegador(client, u, tiendas, termino):
    """Seguridad de negocio: nadie puede meter un producto de $1 si la tienda lo vende a $300.000."""
    tiendas.poner("Éxito", producto("Éxito", "TV", 300_000, 10_000))
    url = buscar_ok(client, termino, 1_000_000)["viables"][0]["url"]
    c = crear_carrito(client, u, 1_000_000)
    item = agregar_item_ok(client, u, c["id"], precio=1, envio=0, url=url, tienda="Éxito")
    assert item["precio_total"] == 310_000


def test_cp13_11b_tomar_el_producto_de_otro_no_cambia_su_nombre_en_el_catalogo(client, tiendas, termino):
    """Dos usuarios agregan el mismo enlace: el segundo no puede 'renombrar' el producto del primero."""
    _, a = usuario_con_sesion(client)
    _, b = usuario_con_sesion(client)
    url = "https://qa.test/carrito/catalogo-compartido"
    ca, cb = crear_carrito(client, a, 1000), crear_carrito(client, b, 1000)
    agregar_item_ok(client, a, ca["id"], 100, nombre="Nombre original", url=url)
    agregar_item_ok(client, b, cb["id"], 100, nombre="Nombre falso", url=url)
    assert consulta_db("SELECT nombre FROM productos WHERE url = %s", (url,)) == [("Nombre original",)]


# ----------------------------------------------------------------------------- cambiar prioridad y quitar
def test_cp13_12_cambiar_la_prioridad(client, u):
    c = crear_carrito(client, u, 1000)
    item = agregar_item_ok(client, u, c["id"], 100, 2)
    r = client.patch(f"/carritos/{c['id']}/items/{item['id']}", json={"prioridad": 5}, headers=u)
    assert r.status_code == 200 and r.json()["prioridad"] == 5
    assert client.get(f"/carritos/{c['id']}", headers=u).json()["items"][0]["prioridad"] == 5


@pytest.mark.parametrize("prioridad", [0, 6, "x", None])
def test_cp13_12b_prioridad_invalida_al_editar_da_422(client, u, prioridad):
    c = crear_carrito(client, u, 1000)
    item = agregar_item_ok(client, u, c["id"], 100, 2)
    assert client.patch(f"/carritos/{c['id']}/items/{item['id']}", json={"prioridad": prioridad}, headers=u).status_code == 422


def test_cp13_12c_un_producto_inexistente_da_404(client, u):
    c = crear_carrito(client, u, 1000)
    assert client.patch(f"/carritos/{c['id']}/items/999999999", json={"prioridad": 3}, headers=u).status_code == 404
    assert client.delete(f"/carritos/{c['id']}/items/999999999", headers=u).status_code == 404


def test_cp13_12d_un_producto_de_otro_carrito_mio_no_se_toca_por_el_carrito_equivocado(client, u):
    a, b = crear_carrito(client, u, 1000), crear_carrito(client, u, 1000)
    item = agregar_item_ok(client, u, a["id"], 100)
    assert client.patch(f"/carritos/{b['id']}/items/{item['id']}", json={"prioridad": 1}, headers=u).status_code == 404
    assert client.delete(f"/carritos/{b['id']}/items/{item['id']}", headers=u).status_code == 404


def test_cp13_13_quitar_un_producto(client, u):
    c = crear_carrito(client, u, 1000)
    item = agregar_item_ok(client, u, c["id"], 100)
    assert client.delete(f"/carritos/{c['id']}/items/{item['id']}", headers=u).status_code == 204
    assert client.get(f"/carritos/{c['id']}", headers=u).json()["items"] == []


def test_cp13_14_cualquier_cambio_invalida_el_calculo_de_la_mochila(client, u):
    """Si cambian los productos, la prioridad o el presupuesto, el resultado de optimizar ya no vale."""
    c = crear_carrito(client, u, 1000)
    i1 = agregar_item_ok(client, u, c["id"], 100, 3)

    def optimizado():
        client.post(f"/carritos/{c['id']}/optimizar", headers=u)
        assert client.get(f"/carritos/{c['id']}", headers=u).json()["optimizado"] is True

    def sin_optimizar():
        d = client.get(f"/carritos/{c['id']}", headers=u).json()
        assert d["optimizado"] is False and not any(i["incluido"] for i in d["items"]) and d["total"] == 100 * len(d["items"])

    optimizado()
    agregar_item_ok(client, u, c["id"], 100, 3)
    sin_optimizar()
    optimizado()
    client.patch(f"/carritos/{c['id']}/items/{i1['id']}", json={"prioridad": 1}, headers=u)
    sin_optimizar()
    optimizado()
    client.patch(f"/carritos/{c['id']}", json={"presupuesto": 5000}, headers=u)
    sin_optimizar()
    optimizado()
    client.patch(f"/carritos/{c['id']}", json={"nombre": "solo el nombre"}, headers=u)
    assert client.get(f"/carritos/{c['id']}", headers=u).json()["optimizado"] is True, "Cambiar solo el nombre NO invalida"
    client.delete(f"/carritos/{c['id']}/items/{i1['id']}", headers=u)
    assert client.get(f"/carritos/{c['id']}", headers=u).json()["optimizado"] is False
