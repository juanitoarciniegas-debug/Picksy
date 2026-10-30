"""RNF-01: la búsqueda con datos en caché responde en menos de 5 s (propuesta del ERS)."""
import statistics
import time

import pytest

from ayudas import buscar_ok
from mocks import producto

pytestmark = pytest.mark.req("RNF-01")
LIMITE_SEGUNDOS = 5.0
REPETICIONES = 10


def test_rnf01_1_busqueda_con_cache_responde_en_menos_de_5_segundos(client, tiendas, termino):
    for i, nombre in enumerate(tiendas.nombres):
        tiendas.poner(nombre, producto(nombre, "TV", 300_000 + i, 10_000))
    buscar_ok(client, termino, 500_000)                 # llena la caché (esta no se mide)
    tiempos = []
    for _ in range(REPETICIONES):
        inicio = time.perf_counter()
        buscar_ok(client, termino, 500_000)
        tiempos.append(time.perf_counter() - inicio)
    print(f"\nRNF-01 con caché: mediana {statistics.median(tiempos):.3f} s · máximo {max(tiempos):.3f} s")
    assert max(tiempos) < LIMITE_SEGUNDOS
