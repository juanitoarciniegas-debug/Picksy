"""
Caché: RF-05. Con tiendas simuladas se CUENTA cuántas veces se consultó una tienda:
si la caché funciona, la segunda búsqueda no genera llamadas nuevas.
La vigencia es de 24 h (propuesta A-04, ya implementada en cache.HORAS_CACHE).
"""
from datetime import datetime

import pytest

import cache
from ayudas import buscar_ok, consulta_db
from mocks import producto

pytestmark = pytest.mark.req("RF-05")
PRESUPUESTO = 500_000


@pytest.fixture
def una_tienda(tiendas):
    """(el nombre se conserva por comodidad) TODAS las tiendas devuelven un producto, para probar
    la caché sin mezclar el caso de las tiendas sin resultados (ver DEF-05 más abajo)."""
    for i, nombre in enumerate(tiendas.nombres):
        tiendas.poner(nombre, producto(nombre, "TV", 300_000 + i * 1_000, 10_000))
    return tiendas


def _envejecer(termino, horas):
    """Hace que la caché de este término parezca de hace `horas` horas."""
    consulta_db("UPDATE cache_busquedas SET consultado_en = NOW() - make_interval(hours => %s) "
                "WHERE termino = %s", (horas, cache.normalizar(termino)))


def test_cp05_0_la_vigencia_configurada_es_de_24_horas():
    assert cache.HORAS_CACHE == 24


def test_cp05_1_busqueda_repetida_no_vuelve_a_consultar_las_tiendas(client, una_tienda, termino):
    buscar_ok(client, termino, PRESUPUESTO)
    consultas_iniciales = len(una_tienda.llamadas)
    assert consultas_iniciales == len(una_tienda.nombres), "La primera búsqueda consulta todas las tiendas"
    segunda = buscar_ok(client, termino, PRESUPUESTO)
    assert len(una_tienda.llamadas) == consultas_iniciales, "La segunda debe salir de la caché"
    assert len(segunda["viables"]) == len(una_tienda.nombres)


def test_cp05_1b_mayusculas_acentos_y_espacios_cuentan_como_la_misma_busqueda(client, una_tienda, termino):
    buscar_ok(client, termino, PRESUPUESTO)
    n = len(una_tienda.llamadas)
    buscar_ok(client, "  " + termino.upper() + "  ", PRESUPUESTO)
    assert len(una_tienda.llamadas) == n


def test_cp05_2_con_la_cache_vencida_vuelve_a_extraer(client, una_tienda, termino):
    buscar_ok(client, termino, PRESUPUESTO)
    n = len(una_tienda.llamadas)
    _envejecer(termino, 25)
    buscar_ok(client, termino, PRESUPUESTO)
    assert len(una_tienda.llamadas) == 2 * n


def test_cp05_2b_a_las_23_horas_la_cache_sigue_vigente(client, una_tienda, termino):
    buscar_ok(client, termino, PRESUPUESTO)
    n = len(una_tienda.llamadas)
    _envejecer(termino, 23)
    buscar_ok(client, termino, PRESUPUESTO)
    assert len(una_tienda.llamadas) == n


def test_cp05_3_la_fecha_de_actualizacion_es_la_de_la_extraccion_original(client, una_tienda, termino):
    """Desde la caché se muestra CUÁNDO se obtuvo el dato, no la hora de la consulta."""
    primera = buscar_ok(client, termino, PRESUPUESTO)["viables"][0]["actualizado_en"]
    segunda = buscar_ok(client, termino, PRESUPUESTO)["viables"][0]["actualizado_en"]
    assert datetime.fromisoformat(primera) == datetime.fromisoformat(segunda)


def test_cp05_4_actualizar_true_ignora_la_cache(client, una_tienda, termino):
    buscar_ok(client, termino, PRESUPUESTO)
    n = len(una_tienda.llamadas)
    buscar_ok(client, termino, PRESUPUESTO, actualizar="true")
    assert len(una_tienda.llamadas) == 2 * n


@pytest.mark.xfail(strict=False, reason=(
    "DEF-05: las tiendas que NO devuelven resultados no se guardan en caché (cache.py solo guarda "
    "'si hubo resultados'), así que una búsqueda repetida las vuelve a consultar. Contradice el criterio "
    "de aceptación de RF-05 y multiplica el tráfico hacia tiendas reales."))
def test_cp05_5_tiendas_sin_resultados_tampoco_se_vuelven_a_consultar(client, tiendas, termino):
    tiendas.poner("Éxito", producto("Éxito", "TV", 300_000))      # las otras 8 tiendas no tienen el producto
    buscar_ok(client, termino, PRESUPUESTO)
    n = len(tiendas.llamadas)
    buscar_ok(client, termino, PRESUPUESTO)
    assert len(tiendas.llamadas) == n, f"La repetición consultó {len(tiendas.llamadas) - n} tiendas de nuevo"


# ----------------------------------------------------------------------------- v2: caché de resultados vacíos
# (DEF-05 corregido: una tienda que responde "0 resultados" se guarda 30 min, no 24 h). Se omiten en la v1.
import cache as _cache  # noqa: E402

CON_VACIO = hasattr(_cache, "MINUTOS_CACHE_VACIO")
SOLO_V2 = pytest.mark.skipif(not CON_VACIO, reason="OMITIDA: esta versión aún no guarda resultados vacíos (DEF-05)")


def _envejecer_minutos(termino, minutos):
    consulta_db("UPDATE cache_busquedas SET consultado_en = NOW() - make_interval(mins => %s) "
                "WHERE termino = %s", (minutos, cache.normalizar(termino)))


@SOLO_V2
def test_cp05_6_vigencia_de_resultados_vacios_es_de_30_minutos():
    assert _cache.MINUTOS_CACHE_VACIO == 30


@SOLO_V2
def test_cp05_7_tienda_sin_resultados_no_se_reconsulta_dentro_de_30_minutos(client, tiendas, termino):
    tiendas.poner("Éxito", producto("Éxito", "TV", 300_000))          # las otras 8 no lo tienen
    buscar_ok(client, termino, PRESUPUESTO)
    n = len(tiendas.llamadas)
    _envejecer_minutos(termino, 29)
    buscar_ok(client, termino, PRESUPUESTO)
    assert len(tiendas.llamadas) == n


@SOLO_V2
def test_cp05_8_pasados_30_minutos_la_tienda_sin_resultados_se_vuelve_a_consultar(client, tiendas, termino):
    tiendas.poner("Éxito", producto("Éxito", "TV", 300_000))
    buscar_ok(client, termino, PRESUPUESTO)
    n = len(tiendas.llamadas)
    _envejecer_minutos(termino, 31)
    buscar_ok(client, termino, PRESUPUESTO)
    consultadas = [t for t, _ in tiendas.llamadas[n:]]
    assert len(consultadas) == len(tiendas.nombres) - 1, "Deben reconsultarse las 8 tiendas que no tenían el producto"
    assert "Éxito" not in consultadas, "Éxito sí tenía resultados: sigue vigente 24 h"


@SOLO_V2
def test_cp05_9_una_tienda_que_FALLA_no_se_guarda_como_vacia(client, tiendas, termino):
    """Un error de la tienda (caída, bloqueo) no debe quedar en caché como 'sin resultados' durante 30 minutos."""
    for i, nombre in enumerate(tiendas.nombres):
        tiendas.poner(nombre, producto(nombre, "TV", 300_000 + i))
    tiendas.hacer_fallar("Alkosto")
    buscar_ok(client, termino, PRESUPUESTO)
    buscar_ok(client, termino, PRESUPUESTO)
    veces = sum(1 for t, _ in tiendas.llamadas if t == "Alkosto")
    assert veces == 2, "Alkosto falló: la segunda búsqueda debe volver a intentarlo"
