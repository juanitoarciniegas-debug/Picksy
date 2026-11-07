"""
DEF-01 (corregido en la v3): /buscar descarta los resultados que no tienen que ver con lo buscado.
Las tiendas a veces devuelven sugerencias aunque no haya coincidencia ("asdfghjk" devolvía 39 productos sin relación).

Estas pruebas usan relevantes=False: la tienda simulada devuelve los nombres EXACTOS que define cada caso.
La definición de "relevante" no está en el ERS (era la pregunta abierta del DEF-01); aquí se verifica el comportamiento
documentado en relevancia.py: cada palabra importante de la búsqueda debe estar en el nombre del producto.
"""
import pytest

from ayudas import buscar_ok as _buscar_ok, consulta_db
from mocks import producto

pytestmark = pytest.mark.req("RF-04")
PRESUPUESTO = 5_000_000
_terminos = []


@pytest.fixture
def exactos(tiendas):
    """Tienda simulada que devuelve los nombres EXACTOS del caso. Estas pruebas buscan frases reales
    ('playstation 5'), no 'qa xxxxxx', así que se salta la caché y al final se borra lo que dejaron."""
    tiendas.relevantes = False
    _terminos.clear()
    yield tiendas
    for t in _terminos:
        consulta_db("DELETE FROM cache_busquedas WHERE termino = %s", (t.lower(),))


def buscar_ok(client, texto, presupuesto):          # noqa: F811 - versión local, sin caché
    _terminos.append(texto)
    return _buscar_ok(client, texto, presupuesto, actualizar="true")


def _nombres(datos):
    return sorted(o["nombre"] for o in datos["viables"] + datos["descartadas"])


def test_cp04_3_un_producto_inexistente_devuelve_lista_vacia(client, exactos):
    """El caso exacto del DEF-01: nada de lo que devuelve la tienda se parece a lo buscado."""
    exactos.poner("Falabella", producto("Falabella", "Sticker de gatito", 5_000), producto("Falabella", "Funda de celular", 12_000))
    d = buscar_ok(client, "asdfghjk", PRESUPUESTO)
    assert d["viables"] == [] and d["descartadas"] == [] and d["mejor_opcion"] is None
    assert d["irrelevantes"] == 2, "Debe informar cuántos resultados se ocultaron"


def test_cp04_3b_solo_quedan_los_que_contienen_todas_las_palabras(client, exactos):
    exactos.poner("Éxito",
                  producto("Éxito", "Televisor Samsung 55 pulgadas", 1_900_000),
                  producto("Éxito", "Cable HDMI para televisor Samsung", 30_000),
                  producto("Éxito", "Televisor LG 55 pulgadas", 1_800_000))
    d = buscar_ok(client, "televisor samsung 55", PRESUPUESTO)
    assert _nombres(d) == ["Televisor Samsung 55 pulgadas"]
    assert d["irrelevantes"] == 2


def test_cp04_3c_ignora_mayusculas_tildes_y_plurales(client, exactos):
    exactos.poner("Alkosto", producto("Alkosto", "AUDÍFONOS Bluetooth Sony", 150_000))
    assert len(buscar_ok(client, "audifono sony", PRESUPUESTO)["viables"]) == 1


def test_cp04_3d_las_palabras_de_relleno_no_cuentan(client, exactos):
    exactos.poner("Alkosto", producto("Alkosto", "Nevera Samsung", 2_500_000))
    assert len(buscar_ok(client, "nevera de samsung", PRESUPUESTO)["viables"]) == 1


def test_cp04_3e_los_numeros_si_cuentan(client, exactos):
    exactos.poner("Ktronix", producto("Ktronix", "Apple iPhone 14 128GB", 3_000_000),
                  producto("Ktronix", "Apple iPhone 15 128GB", 4_000_000))
    assert _nombres(buscar_ok(client, "iphone 15", PRESUPUESTO)) == ["Apple iPhone 15 128GB"]


@pytest.mark.parametrize("nombre_en_tienda", [
    "Consola PlayStation 5 Slim", "Consola PS5 Digital", "Consola Play Station 5", "Consola PS 5 Pro",
])
def test_cp04_3f_las_formas_de_escribir_playstation_5_son_la_misma_consola(client, exactos, nombre_en_tienda):
    """Bug reportado por el desarrollador: buscando 'playstation 5' no salía Ktronix, que escribe 'PS5'."""
    exactos.poner("Ktronix", producto("Ktronix", nombre_en_tienda, 2_500_000))
    assert len(buscar_ok(client, "playstation 5", PRESUPUESTO)["viables"]) == 1, nombre_en_tienda


def test_cp04_3g_playstation_5_no_acepta_playstation_4(client, exactos):
    exactos.poner("Ktronix", producto("Ktronix", "Consola PS4 Pro", 1_500_000))
    assert buscar_ok(client, "playstation 5", PRESUPUESTO)["viables"] == []


def test_cp04_3h_ps5_escrito_pegado_encuentra_playstation_5(client, exactos):
    exactos.poner("Alkosto", producto("Alkosto", "Consola Sony PlayStation 5", 2_600_000))
    assert len(buscar_ok(client, "ps5", PRESUPUESTO)["viables"]) == 1


def test_cp04_3i_tv_no_coincide_con_ventilador(client, exactos):
    """Una palabra corta (menos de 4 letras) solo coincide completa: 'tv' no está dentro de 'ventilador'."""
    exactos.poner("Éxito", producto("Éxito", "Ventilador de pie", 120_000), producto("Éxito", "Smart TV 43", 1_100_000))
    assert _nombres(buscar_ok(client, "tv", PRESUPUESTO)) == ["Smart TV 43"]


def test_cp04_3j_los_irrelevantes_no_cuentan_como_agotados_ni_como_descartados(client, exactos):
    exactos.poner("Éxito", producto("Éxito", "Cable USB", 10_000), producto("Éxito", "Televisor", 900_000))
    d = buscar_ok(client, "televisor", PRESUPUESTO)
    assert (d["irrelevantes"], d["agotados"], len(d["descartadas"]), len(d["viables"])) == (1, 0, 0, 1)


@pytest.mark.parametrize("busqueda,nombre,debe", [
    ("a5", "Samsung Galaxy A54", False),       # 'a5' NO es 'a54'
    ("a5", "Samsung Galaxy A 5", True),
    ("iphone15", "Apple iPhone 15 Pro", True),
    ("iphone15", "Apple iPhone 14", False),
    ("ps", "Consola PS5", True),
])
def test_cp04_3k_numeros_pegados_a_las_letras_no_coinciden_de_mas(client, exactos, busqueda, nombre, debe):
    exactos.poner("Ktronix", producto("Ktronix", nombre, 1_000_000))
    assert bool(buscar_ok(client, busqueda, PRESUPUESTO)["viables"]) is debe
