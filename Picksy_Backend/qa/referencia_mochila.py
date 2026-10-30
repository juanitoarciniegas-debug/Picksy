"""
referencia_mochila.py - ORÁCULO para RF-14 (mochila 0/1), escrito por QA ANTES de que exista el código.

Cuando Backend entregue la mochila (tarea B-05), se prueba comparando su resultado con este.
Tiene DOS implementaciones independientes (fuerza bruta y programación dinámica): si coinciden
entre sí, el oráculo es confiable.

Cada producto es (costo, prioridad). Se maximiza la prioridad total sin superar el presupuesto.
Desempate para que el resultado sea determinista: menor costo total y luego los índices más bajos.
"""
from itertools import combinations


def fuerza_bruta(items, presupuesto):
    """Devuelve (prioridad_total, costo_total, indices). Sirve para listas pequeñas (<= 15)."""
    mejor = (0, 0, ())
    for k in range(1, len(items) + 1):
        for combo in combinations(range(len(items)), k):
            costo = sum(items[i][0] for i in combo)
            if costo > presupuesto:
                continue
            prioridad = sum(items[i][1] for i in combo)
            if (prioridad, -costo) > (mejor[0], -mejor[1]):
                mejor = (prioridad, costo, combo)
    return mejor


def programacion_dinamica(items, presupuesto):
    """Solo devuelve la prioridad máxima (costos enteros). Segunda opinión independiente."""
    mejor = [0] * (presupuesto + 1)
    for costo, prioridad in items:
        for p in range(presupuesto, costo - 1, -1):
            mejor[p] = max(mejor[p], mejor[p - costo] + prioridad)
    return mejor[presupuesto]
