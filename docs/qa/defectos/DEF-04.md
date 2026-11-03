# DEF-04 · Un presupuesto «inf» provoca error 500

| Campo | Valor |
|---|---|
| Requisito | RF-07 |
| Severidad | Media |
| Prioridad (la fija Requerimientos) | Por definir |
| Versión del software | v1 |
| Entorno | Cualquiera |
| Estado | **Corregido por Backend en la v2** (falta verificarlo en el CI tras el merge) |
| Frecuencia | Siempre. Hallado el 28-oct-2026 por el bot de QA. |
| Prueba que lo detecta | `qa/test_busqueda_reglas.py::test_cp07_4_presupuesto_infinito_se_rechaza (xfail)` |

## Pasos para reproducir
GET /buscar?producto=tv&presupuesto=inf

## Resultado esperado
422: presupuesto inválido.

## Resultado obtenido
500 Internal Server Error.

## Notas
Causa probable: float('inf') cumple gt=0 y la respuesta JSON no puede representar infinito. Conviene también fijar un presupuesto máximo razonable (hoy 1e308 se acepta). No hay pérdida de datos.

## Historial de estados
| Fecha | Estado | Quién | Comentario |
|---|---|---|---|
| 2026-10-28 | Abierto | QA | Registrado |
| 2026-10-29 | Corregido (v2) | Backend | El bot de QA ejecutó la v2 en el entorno de QA: la prueba que lo reproducía ahora pasa («posiblemente corregido»). Se agregaron pruebas de límites. QA lo cierra cuando el CI lo confirme con la v2 en main. |
