"""Pruebas del propio bot: que requisitos.yml sea coherente (no llevan marcador de requisito)."""
import re

from conftest import REQ_POR_ID, REQUISITOS


def test_los_ids_son_unicos_y_tienen_formato_del_ers():
    ids = [r["id"] for r in REQUISITOS["requisitos"]]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"(RF|RNF)-\d{2}", i) for i in ids)


def test_cada_requisito_tiene_titulo_y_prioridad():
    for r in REQ_POR_ID.values():
        assert r.get("titulo") and "prioridad" in r, r["id"]


def test_el_ers_define_diez_tiendas():
    assert len(REQUISITOS["tiendas_ers"]) == 10


CLAVES_PERMITIDAS = {"id", "titulo", "prioridad", "implementado", "bloqueado_por", "metodo_manual", "nota", "pendiente", "propuesto"}


def test_ningun_requisito_tiene_claves_inesperadas():
    """Atrapa errores de formato del YAML (por ejemplo, una coma sin comillas que parte el título en dos)."""
    for r in REQUISITOS["requisitos"]:
        sobran = set(r) - CLAVES_PERMITIDAS
        assert not sobran, f"{r['id']} tiene claves inesperadas: {sobran}. Revisa comillas y comas en requisitos.yml"


def test_el_registro_de_cambios_del_contrato_no_recorta_las_diferencias():
    """Hallazgo de la v4: actualizar_contrato.py cortaba la línea de CAMBIOS.md a 300 caracteres y quedaban 3 de las
    10 rutas nuevas sin registrar. Ahora la línea lleva TODAS las diferencias y escapa '|' (no rompe la tabla)."""
    from contrato import fila_cambios
    dif = [f"RUTA NUEVA: GET /api/v1/pagos/ruta_{i}" for i in range(40)]
    fila = fila_cambios("2026-11-09", "motivo | con barra", dif)
    assert all(d in fila for d in dif), "Falta alguna diferencia: el registro quedó incompleto"
    assert fila.startswith("| 2026-11-09 |") and fila.endswith(" |\n") and fila.count("\n") == 1
    assert "motivo \\| con barra" in fila
