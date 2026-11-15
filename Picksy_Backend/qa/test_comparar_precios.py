"""
COMPARAR CARRITOS (RF-17) y VARIACIÓN DE PRECIOS (RF-16). Ambos son nuevos en la v3.
"""
import pytest

from ayudas import agregar_item_ok, buscar_ok, crear_carrito, usuario_con_sesion
from mocks import producto


@pytest.fixture
def u(client):
    return usuario_con_sesion(client)[1]


def _comparar(client, u, a, b):
    return client.get("/carritos/comparar", params={"a": a, "b": b}, headers=u)


# ----------------------------------------------------------------------------- RF-17
@pytest.mark.req("RF-17")
def test_cp17_1_dice_cual_es_mas_barato_y_por_cuanto(client, u):
    a, b = crear_carrito(client, u, 1_000_000, "Opción A"), crear_carrito(client, u, 1_000_000, "Opción B")
    agregar_item_ok(client, u, a["id"], 300_000)
    agregar_item_ok(client, u, a["id"], 200_000)
    agregar_item_ok(client, u, b["id"], 350_000)
    d = _comparar(client, u, a["id"], b["id"]).json()
    assert d["a"]["total"] == 500_000 and d["b"]["total"] == 350_000
    assert d["diferencia"] == 150_000 and d["mas_barato"] == "b"
    assert "Opción B" in d["mensaje"] and "150.000" in d["mensaje"]


@pytest.mark.req("RF-17")
def test_cp17_2_el_orden_de_a_y_b_cambia_quien_es_mas_barato_pero_no_la_diferencia(client, u):
    a, b = crear_carrito(client, u, 1_000_000), crear_carrito(client, u, 1_000_000)
    agregar_item_ok(client, u, a["id"], 100)
    agregar_item_ok(client, u, b["id"], 900)
    ab, ba = _comparar(client, u, a["id"], b["id"]).json(), _comparar(client, u, b["id"], a["id"]).json()
    assert (ab["mas_barato"], ba["mas_barato"]) == ("a", "b") and ab["diferencia"] == ba["diferencia"] == 800


@pytest.mark.req("RF-17")
def test_cp17_3_totales_iguales(client, u):
    a, b = crear_carrito(client, u, 1000), crear_carrito(client, u, 1000)
    agregar_item_ok(client, u, a["id"], 400)
    agregar_item_ok(client, u, b["id"], 400)
    d = _comparar(client, u, a["id"], b["id"]).json()
    assert d["mas_barato"] == "igual" and d["diferencia"] == 0


@pytest.mark.req("RF-17")
def test_cp17_4_un_carrito_optimizado_se_compara_por_lo_que_quedo_dentro(client, u):
    a, b = crear_carrito(client, u, 500), crear_carrito(client, u, 1_000_000)
    for p, pr in [(300, 5), (200, 4), (250, 3)]:
        agregar_item_ok(client, u, a["id"], p, pr)
    agregar_item_ok(client, u, b["id"], 600)
    client.post(f"/carritos/{a['id']}/optimizar", headers=u)      # queda 300 + 200 = 500
    d = _comparar(client, u, a["id"], b["id"]).json()
    assert d["a"]["total"] == 500 and d["a"]["optimizado"] is True and d["mas_barato"] == "a" and d["diferencia"] == 100


@pytest.mark.req("RF-17")
def test_cp17_5_el_mismo_carrito_contra_si_mismo_da_400(client, u):
    a = crear_carrito(client, u, 1000)
    assert _comparar(client, u, a["id"], a["id"]).status_code == 400


@pytest.mark.req("RF-17")
def test_cp17_6_carritos_ajenos_o_inexistentes_dan_404(client):
    _, mio = usuario_con_sesion(client)
    _, otro = usuario_con_sesion(client)
    a, ajeno = crear_carrito(client, mio, 1000), crear_carrito(client, otro, 1000)
    assert _comparar(client, mio, a["id"], ajeno["id"]).status_code == 404
    assert _comparar(client, mio, a["id"], 999999999).status_code == 404
    assert _comparar(client, mio, 999999999, a["id"]).status_code == 404


@pytest.mark.req("RF-17")
@pytest.mark.parametrize("params", [{}, {"a": 1}, {"b": 1}, {"a": "x", "b": 1}])
def test_cp17_7_parametros_faltantes_o_invalidos_dan_422(client, u, params):
    assert client.get("/carritos/comparar", params=params, headers=u).status_code == 422


# ----------------------------------------------------------------------------- RF-16
URL = "https://qa.test/precios/{}"


def _consultar(client, tiendas, termino, precio, envio=0.0):
    """Una 'consulta a la tienda': busca ignorando la caché para que se guarde una foto de precio nueva."""
    tiendas.poner("Éxito", producto("Éxito", f"Cafetera {termino}", precio, envio))   # nombre único = URL única = historial propio
    return buscar_ok(client, termino, 5_000_000, actualizar="true")["viables"][0]["url"]


@pytest.mark.req("RF-16")
def test_cp16_1_producto_sin_consultas_da_404(client, u):
    r = client.get("/productos/precios", params={"url": "https://qa.test/no/existe/nunca"}, headers=u)
    assert r.status_code == 404


@pytest.mark.req("RF-16")
def test_cp16_2_con_una_sola_consulta_no_hay_variacion(client, u, tiendas, termino):
    url = _consultar(client, tiendas, termino, 100_000)
    d = client.get("/productos/precios", params={"url": url}, headers=u).json()
    assert d["variacion"]["consultas"] == 1 and d["variacion"]["cambio"] is None
    assert d["producto"]["url"] == url and len(d["consultas"]) == 1 and "una consulta" in d["mensaje"]


@pytest.mark.req("RF-16")
def test_cp16_3_si_el_precio_sube_se_calcula_el_cambio(client, u, tiendas, termino):
    _consultar(client, tiendas, termino, 100_000)
    url = _consultar(client, tiendas, termino, 125_000)
    v = client.get("/productos/precios", params={"url": url}, headers=u).json()["variacion"]
    assert v["consultas"] == 2 and v["cambio"] == 25_000 and v["cambio_porcentaje"] == 25.0
    assert (v["minimo"], v["maximo"]) == (100_000, 125_000)
    assert v["primera"]["precio"] == 100_000 and v["ultima"]["precio"] == 125_000


@pytest.mark.req("RF-16")
def test_cp16_4_si_el_precio_baja_el_cambio_es_negativo(client, u, tiendas, termino):
    _consultar(client, tiendas, termino, 200_000)
    url = _consultar(client, tiendas, termino, 150_000)
    d = client.get("/productos/precios", params={"url": url}, headers=u).json()
    assert d["variacion"]["cambio"] == -50_000 and d["variacion"]["cambio_porcentaje"] == -25.0
    assert "bajó" in d["mensaje"] and "50.000" in d["mensaje"]


@pytest.mark.req("RF-16")
def test_cp16_5_las_consultas_salen_de_la_mas_vieja_a_la_mas_nueva(client, u, tiendas, termino):
    for precio in (300, 200, 400):
        url = _consultar(client, tiendas, termino, precio)
    filas = client.get("/productos/precios", params={"url": url}, headers=u).json()["consultas"]
    assert [f["precio"] for f in filas] == [300, 200, 400]
    fechas = [f["consultado_en"] for f in filas]
    assert fechas == sorted(fechas)


@pytest.mark.req("RF-16")
def test_cp16_6_precio_igual_dice_que_no_cambio(client, u, tiendas, termino):
    _consultar(client, tiendas, termino, 100)
    url = _consultar(client, tiendas, termino, 100)
    d = client.get("/productos/precios", params={"url": url}, headers=u).json()
    assert d["variacion"]["cambio"] == 0 and d["mensaje"] == "El precio no ha cambiado."


@pytest.mark.req("RF-16")
@pytest.mark.parametrize("params", [{}, {"url": ""}, {"url": "x"}, {"url": "u" * 2001}])
def test_cp16_7_url_faltante_o_fuera_de_limites_da_422(client, u, params):
    assert client.get("/productos/precios", params=params, headers=u).status_code == 422


@pytest.mark.req("RF-16")
def test_cp16_8_el_precio_del_carrito_usa_la_ultima_consulta(client, u, tiendas, termino):
    """Une RF-13 y RF-16: al agregar al carrito se toma el precio MÁS RECIENTE guardado."""
    _consultar(client, tiendas, termino, 100_000)
    url = _consultar(client, tiendas, termino, 90_000)
    c = crear_carrito(client, u, 1_000_000)
    assert agregar_item_ok(client, u, c["id"], 1, url=url)["precio_total"] == 90_000
