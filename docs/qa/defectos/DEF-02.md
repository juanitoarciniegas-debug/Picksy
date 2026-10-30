# DEF-02 · La API expone 9 tiendas y el ERS dice 10 (falta Mercado Libre)

| Campo | Valor |
|---|---|
| Requisito | RF-04 |
| Severidad | Media |
| Prioridad (la fija Requerimientos) | Por definir |
| Versión del software | v1 |
| Entorno | Cualquiera (no depende de tiendas reales) |
| Estado | **Abierto** (nuevo, confirmado por QA) |
| Frecuencia | Siempre (3 de 3 ejecuciones manuales y en cada ejecución del bot). |
| Prueba que lo detecta | `qa/test_tiendas.py::test_cp04_2b_la_api_expone_las_10_tiendas_del_ers (xfail)` |

## Pasos para reproducir
GET /tiendas y comparar con el ERS sección 2.1 y con la tabla tiendas

## Resultado esperado
Las 10 tiendas del ERS, cada una con su conector.

## Resultado obtenido
9 tiendas. La tabla tiendas sí tiene las 10; falta el conector de Mercado Libre en buscador.py.

## Notas
Severidad subida de Baja a Media: incumple un requisito de prioridad Alta y el alcance. El equipo decide si se agrega el conector o se corrige el ERS. Cuando se corrija, el bot lo marca como POSIBLEMENTE CORREGIDO.

## Historial de estados
| Fecha | Estado | Quién | Comentario |
|---|---|---|---|
| 2026-10-28 | Abierto | QA | Registrado |
