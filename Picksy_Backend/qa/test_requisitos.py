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


CLAVES_PERMITIDAS = {"id", "titulo", "prioridad", "implementado", "bloqueado_por", "metodo_manual", "nota", "pendiente"}


def test_ningun_requisito_tiene_claves_inesperadas():
    """Atrapa errores de formato del YAML (por ejemplo, una coma sin comillas que parte el título en dos)."""
    for r in REQUISITOS["requisitos"]:
        sobran = set(r) - CLAVES_PERMITIDAS
        assert not sobran, f"{r['id']} tiene claves inesperadas: {sobran}. Revisa comillas y comas en requisitos.yml"
