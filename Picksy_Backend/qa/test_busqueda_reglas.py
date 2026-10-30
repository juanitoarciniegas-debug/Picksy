"""
Reglas de negocio de /buscar con tiendas SIMULADAS (ninguna petición a tiendas reales):
RF-04, RF-07, RF-08, RF-09, RF-10, RF-11, RF-12 y RNF-08.
Cada tienda simulada devuelve precios exactos, así que el resultado correcto se calcula a mano.
"""
from datetime import datetime

import pytest

from ayudas import buscar, buscar_ok
from mocks import producto

PRESUPUESTO = 500_000


# ----------------------------------------------------------------------------- RF-07
@pytest.mark.req("RF-07")
@pytest.mark.parametrize("prod,pres", [
    ("tv", None),              # presupuesto ausente
    (None, 500000),            # producto ausente
    ("", 500000), ("a", 500000), ("x" * 101, 500000),
    ("televisor", 0), ("televisor", -1), ("televisor", -0.01),
    ("televisor", "abc"), ("televisor", ""), ("televisor", "nan"),
])
def test_cp07_1_entradas_invalidas_dan_422_y_no_consultan_tiendas(client, tiendas, prod, pres):
    params = {}
    if prod is not None:
        params["producto"] = prod
    if pres is not None:
        params["presupuesto"] = pres
    assert client.get("/buscar", params=params).status_code == 422
    assert tiendas.llamadas == [], "Una entrada inválida no debe llegar a las tiendas"


@pytest.mark.req("RF-07")
@pytest.mark.parametrize("prod,pres", [("tv", 1), ("x" * 100, 1000), ("televisor", 0.01)])
def test_cp07_2_limites_validos_se_aceptan(client, tiendas, prod, pres):
    assert buscar(client, "qa " + prod[:90], pres).status_code == 200


@pytest.mark.req("RF-07")
@pytest.mark.xfail(strict=False, reason=(
    "DEF-03: un producto de solo espacios pasa la validación (min_length se mide antes de strip) "
    "y la API consulta las tiendas con término vacío."))
def test_cp07_3_producto_de_solo_espacios_se_rechaza(client, tiendas):
    r = buscar(client, "   ", 500000)
    assert r.status_code == 422
    assert tiendas.llamadas_a("") == []


@pytest.mark.req("RF-07")
@pytest.mark.xfail(strict=False, reason=(
    "DEF-04: presupuesto 'inf' provoca error 500 (la respuesta no se puede convertir a JSON); "
    "debería ser 422."))
def test_cp07_4_presupuesto_infinito_se_rechaza(client, tiendas, termino):
    assert buscar(client, termino, "inf").status_code == 422


# ----------------------------------------------------------------------------- RF-04
@pytest.mark.req("RF-04")
def test_cp04_1_cada_opcion_trae_precio_envio_y_tienda(client, tiendas, termino):
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000, 15_000))
    op = buscar_ok(client, termino, PRESUPUESTO)["viables"][0]
    for campo in ("tienda", "nombre", "precio", "envio", "envio_confirmado", "total", "url"):
        assert campo in op, f"Falta el campo {campo}"
    assert (op["tienda"], op["precio"], op["envio"]) == ("Éxito", 450_000, 15_000)


@pytest.mark.req("RF-04")
def test_cp04_1b_solo_aparecen_las_tiendas_que_tienen_el_producto(client, tiendas, termino):
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000))
    tiendas.poner("Alkosto", producto("Alkosto", "Nevera", 460_000))
    data = buscar_ok(client, termino, PRESUPUESTO)
    assert {o["tienda"] for o in data["viables"]} == {"Éxito", "Alkosto"}


@pytest.mark.req("RF-04")
def test_cp04_1c_filtro_por_tienda_solo_consulta_esa_tienda(client, tiendas, termino):
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000))
    tiendas.poner("Alkosto", producto("Alkosto", "Nevera", 460_000))
    data = buscar_ok(client, termino, PRESUPUESTO, tiendas="éxito")   # minúsculas a propósito
    assert {o["tienda"] for o in data["viables"]} == {"Éxito"}
    assert {t for t, _ in tiendas.llamadas} == {"Éxito"}


@pytest.mark.req("RF-04")
def test_cp04_1d_producto_agotado_se_excluye_y_se_cuenta(client, tiendas, termino):
    """A-05: los agotados se excluyen del cálculo."""
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 100_000, disponible=False))
    tiendas.poner("Alkosto", producto("Alkosto", "Nevera", 200_000))
    data = buscar_ok(client, termino, PRESUPUESTO)
    assert [o["tienda"] for o in data["viables"]] == ["Alkosto"]
    assert data["descartadas"] == [] and data["agotados"] == 1


# ----------------------------------------------------------------------------- RF-08
@pytest.mark.req("RF-08")
def test_cp08_1_total_es_precio_mas_envio(client, tiendas, termino):
    """Ejemplo exacto del ERS: $450.000 + $15.000 = $465.000."""
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000, 15_000))
    assert buscar_ok(client, termino, PRESUPUESTO)["viables"][0]["total"] == 465_000


@pytest.mark.req("RF-08")
def test_cp08_2_envio_gratis_total_igual_al_precio(client, tiendas, termino):
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000, 0))
    assert buscar_ok(client, termino, PRESUPUESTO)["viables"][0]["total"] == 450_000


@pytest.mark.req("RF-08")
def test_cp08_3_envio_desconocido_cuenta_como_cero_y_se_marca(client, tiendas, termino):
    """COMPORTAMIENTO ACTUAL (A-06 sin decidir): sin envío informado, el total no lo incluye
    pero la opción queda marcada con envio_confirmado=False."""
    tiendas.poner("Éxito", producto("Éxito", "Nevera", 450_000, envio=None))
    op = buscar_ok(client, termino, PRESUPUESTO)["viables"][0]
    assert op["total"] == 450_000 and op["envio"] is None and op["envio_confirmado"] is False


# ----------------------------------------------------------------------------- RF-09
@pytest.fixture
def cinco_casos(tiendas):
    """Presupuesto 500.000. Total por tienda: Éxito 502.000 | Alkosto 500.000 (igual) |
    Falabella 505.000 (el precio solo cabe, el total no) | Ktronix 400.000 | Olímpica 500.001."""
    tiendas.poner("Éxito", producto("Éxito", "TV", 502_000, 0))
    tiendas.poner("Alkosto", producto("Alkosto", "TV", 485_000, 15_000))
    tiendas.poner("Falabella", producto("Falabella", "TV", 490_000, 15_000))
    tiendas.poner("Ktronix", producto("Ktronix", "TV", 400_000, 0))
    tiendas.poner("Olímpica", producto("Olímpica", "TV", 500_001, 0))
    return tiendas


@pytest.mark.req("RF-09")
def test_cp09_1_opcion_sobre_el_presupuesto_aparece_como_descartada(client, cinco_casos, termino):
    data = buscar_ok(client, termino, PRESUPUESTO)
    assert "Éxito" in {o["tienda"] for o in data["descartadas"]}      # 502.000 > 500.000
    assert "Éxito" not in {o["tienda"] for o in data["viables"]}


@pytest.mark.req("RF-09")
def test_cp09_2_total_exactamente_igual_al_presupuesto_es_viable(client, cinco_casos, termino):
    data = buscar_ok(client, termino, PRESUPUESTO)
    assert "Alkosto" in {o["tienda"] for o in data["viables"]}


@pytest.mark.req("RF-09")
def test_cp09_3_total_un_peso_sobre_el_presupuesto_se_descarta(client, cinco_casos, termino):
    data = buscar_ok(client, termino, PRESUPUESTO)
    assert "Olímpica" in {o["tienda"] for o in data["descartadas"]}


@pytest.mark.req("RF-09")
def test_cp09_3b_se_descarta_por_el_total_no_por_el_precio(client, cinco_casos, termino):
    """Falabella: el precio (490.000) cabe, pero con envío (505.000) no."""
    data = buscar_ok(client, termino, PRESUPUESTO)
    assert "Falabella" in {o["tienda"] for o in data["descartadas"]}


@pytest.mark.req("RF-09")
def test_cp09_3c_viables_y_descartadas_son_conjuntos_disjuntos_y_completos(client, cinco_casos, termino):
    data = buscar_ok(client, termino, PRESUPUESTO)
    assert all(o["total"] <= PRESUPUESTO for o in data["viables"])
    assert all(o["total"] > PRESUPUESTO for o in data["descartadas"])
    assert len(data["viables"]) + len(data["descartadas"]) == 5


@pytest.mark.req("RF-09")
def test_cp09_4_todo_descartado_responde_200_con_listas_coherentes(client, cinco_casos, termino):
    data = buscar_ok(client, termino, 1000)
    assert data["viables"] == [] and data["mejor_opcion"] is None and data["ahorro"] is None
    assert len(data["descartadas"]) == 5


# ----------------------------------------------------------------------------- RF-10
@pytest.mark.req("RF-10")
def test_cp10_1_viables_ordenadas_de_menor_a_mayor_total(client, tiendas, termino):
    tiendas.poner("Éxito", producto("Éxito", "TV", 300_000))
    tiendas.poner("Alkosto", producto("Alkosto", "TV", 100_000))
    tiendas.poner("Ktronix", producto("Ktronix", "TV", 200_000))
    data = buscar_ok(client, termino, PRESUPUESTO)
    totales = [o["total"] for o in data["viables"]]
    assert totales == [100_000, 200_000, 300_000]
    assert data["viables"][0]["tienda"] == "Alkosto"


@pytest.mark.req("RF-10")
def test_cp10_1b_descartadas_tambien_ordenadas_ascendente(client, cinco_casos, termino):
    totales = [o["total"] for o in buscar_ok(client, termino, PRESUPUESTO)["descartadas"]]
    assert totales == sorted(totales)


@pytest.mark.req("RF-10")
def test_cp10_2_empate_de_totales_da_siempre_el_mismo_orden(client, tiendas, termino):
    tiendas.poner("Éxito", producto("Éxito", "TV", 100_000))
    tiendas.poner("Alkosto", producto("Alkosto", "TV", 100_000))
    tiendas.poner("Ktronix", producto("Ktronix", "TV", 100_000))
    primero = [o["tienda"] for o in buscar_ok(client, termino, PRESUPUESTO)["viables"]]
    segundo = [o["tienda"] for o in buscar_ok(client, termino, PRESUPUESTO)["viables"]]  # ahora desde caché
    assert primero == segundo and len(primero) == 3


# ----------------------------------------------------------------------------- RF-11
@pytest.mark.req("RF-11")
def test_cp11_1_mejor_opcion_es_la_primera_viable(client, tiendas, termino):
    tiendas.poner("Éxito", producto("Éxito", "TV", 300_000))
    tiendas.poner("Alkosto", producto("Alkosto", "TV", 100_000))
    data = buscar_ok(client, termino, PRESUPUESTO)
    assert data["mejor_opcion"] == data["viables"][0]
    for campo in ("tienda", "total", "url"):
        assert data["mejor_opcion"][campo]


@pytest.mark.req("RF-11")
def test_cp11_2_una_sola_opcion_viable_ahorro_cero(client, tiendas, termino):
    tiendas.poner("Éxito", producto("Éxito", "TV", 300_000))
    assert buscar_ok(client, termino, PRESUPUESTO)["ahorro"] == 0


@pytest.mark.req("RF-11")
@pytest.mark.skip(reason=(
    "BLOQUEADO A-02: el ERS no fija la regla del ahorro. El código usa 'más cara VIABLE menos la mejor'; "
    "la propuesta A-02 dice 'más cara CONSULTADA menos la mejor'. Se activa cuando Requerimientos decida."))
def test_cp11_3_ahorro_segun_la_propuesta_a02(client, cinco_casos, termino):
    data = buscar_ok(client, termino, PRESUPUESTO)
    todos = [o["total"] for o in data["viables"] + data["descartadas"]]
    assert data["ahorro"] == max(todos) - data["mejor_opcion"]["total"]


# ----------------------------------------------------------------------------- RF-12 y RNF-08
@pytest.mark.req("RF-12")
def test_cp12_1_cada_resultado_trae_enlace_https_a_la_tienda(client, cinco_casos, termino):
    data = buscar_ok(client, termino, PRESUPUESTO)
    for o in data["viables"] + data["descartadas"]:
        assert o["url"].startswith("https://"), o


@pytest.mark.req("RNF-08", "RF-05")
def test_rnf08_1_cada_precio_indica_fecha_y_hora_de_actualizacion(client, cinco_casos, termino):
    data = buscar_ok(client, termino, PRESUPUESTO)
    for o in data["viables"] + data["descartadas"]:
        fecha = datetime.fromisoformat(o["actualizado_en"])
        assert fecha.tzinfo is not None, "La fecha debe llevar zona horaria"
