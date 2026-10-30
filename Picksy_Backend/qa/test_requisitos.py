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
