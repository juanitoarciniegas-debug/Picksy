"""
ALARMA DE CAMBIOS (capa 2 del bot): compara el contrato actual de la API con la copia APROBADA
por QA (qa/referencia/openapi.snapshot.json).

Si un desarrollador agrega, quita o modifica una ruta o parámetro, esta prueba falla y el correo
dice "CAMBIÓ EL CONTRATO" con la lista exacta de diferencias. No es un defecto: es un aviso para que
QA decida si el cambio es intencional. Si lo es, QA actualiza la copia a propósito con:
    python qa/actualizar_contrato.py --motivo "agregan la ruta /mochila (RF-14)"
El bot NUNCA actualiza esa copia por su cuenta.
"""
import json
from pathlib import Path

import pytest

from contrato import comparar, normalizar
from main import app

SNAPSHOT = Path(__file__).parent / "referencia" / "openapi.snapshot.json"

pytestmark = pytest.mark.contrato


def test_el_contrato_de_la_api_no_cambio():
    assert SNAPSHOT.exists(), (
        "No existe la copia aprobada del contrato. QA debe crearla una vez: "
        "python qa/actualizar_contrato.py --motivo 'línea base v1'")
    referencia = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    diferencias = comparar(referencia, normalizar(app.openapi()))
    assert not diferencias, (
        "CAMBIÓ EL CONTRATO DE LA API:\n  - " + "\n  - ".join(diferencias) +
        "\nSi es intencional, QA actualiza la referencia: python qa/actualizar_contrato.py --motivo '...'")
