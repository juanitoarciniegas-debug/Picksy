"""
HUMO DIARIO con tiendas REALES. Una sola consulta por tienda, separadas por 3 segundos
(9 peticiones al día en total). Detecta que una tienda cambió su página y rompió su conector.

Solo corre con QA_TIENDAS_REALES=1 (el flujo diario lo activa). Los términos son una suposición
razonable de lo que vende cada tienda: si una tienda devuelve 0 resultados, primero revisa si el
término sigue siendo adecuado antes de reportar un defecto.
"""
import time

import pytest

import buscador

TERMINO_POR_TIENDA = {
    "Éxito": "televisor", "Olímpica": "arroz", "Homecenter": "taladro",
    "Falabella": "zapatos", "Alkosto": "televisor", "Ktronix": "portatil",
    "Alkomprar": "licuadora", "Buscalibre": "libro", "Farmatodo": "acetaminofen",
}
PAUSA_SEGUNDOS = 3

pytestmark = [pytest.mark.real, pytest.mark.req("RF-04")]


@pytest.mark.parametrize("conector", buscador.CONECTORES, ids=lambda c: c.nombre)
def test_humo_conector_responde_con_productos_validos(conector):
    termino = TERMINO_POR_TIENDA.get(conector.nombre)
    if termino is None:
        pytest.fail(f"Conector nuevo sin término de humo: agrega '{conector.nombre}' a TERMINO_POR_TIENDA")
    time.sleep(PAUSA_SEGUNDOS)
    productos = conector.buscar(termino, limite=5)
    assert productos, f"{conector.nombre} no devolvió productos para '{termino}'"
    for p in productos:
        assert p.tienda == conector.nombre
        assert p.precio > 0 and p.url.startswith("http")
