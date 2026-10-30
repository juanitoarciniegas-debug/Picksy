"""
Pruebas del PROPIO oráculo de la mochila (no llevan marcador de requisito: no prueban a Picksy,
prueban la herramienta con la que se probará a Picksy cuando exista RF-14).
"""
import random

from referencia_mochila import fuerza_bruta, programacion_dinamica


def test_ejemplo_calculado_a_mano():
    items = [(300, 5), (200, 4), (250, 3), (100, 1)]
    prioridad, costo, indices = fuerza_bruta(items, 500)
    assert (prioridad, costo, indices) == (9, 500, (0, 1))     # 300 + 200


def test_ninguno_cabe():
    assert fuerza_bruta([(600, 5), (700, 4)], 500) == (0, 0, ())


def test_presupuesto_exacto_a_la_suma():
    assert fuerza_bruta([(100, 2), (200, 3)], 300)[0] == 5


def test_lista_vacia():
    assert fuerza_bruta([], 500) == (0, 0, ())


def test_las_dos_implementaciones_coinciden_en_300_casos_al_azar():
    azar = random.Random(42)                                    # semilla fija: siempre los mismos casos
    for _ in range(300):
        items = [(azar.randint(1, 60), azar.randint(1, 5)) for _ in range(azar.randint(0, 10))]
        presupuesto = azar.randint(1, 200)
        assert fuerza_bruta(items, presupuesto)[0] == programacion_dinamica(items, presupuesto), (items, presupuesto)
