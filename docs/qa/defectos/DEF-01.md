# DEF-01 · Un producto inexistente devuelve resultados irrelevantes

| Campo | Valor |
|---|---|
| Requisito | RF-04 / HU-02 |
| Severidad | Media |
| Prioridad (la fija Requerimientos) | Por definir |
| Versión del software | v1 |
| Entorno | Tiendas reales (flujo de pruebas lentas) |
| Estado | **Abierto** (nuevo, confirmado por QA) |
| Frecuencia | 3 de 3 ejecuciones (27-oct-2026, ejecuciones manuales 1 a 3). La ejecución 4 y el CI lo marcan como xfail. |
| Prueba que lo detecta | `test_api.py::test_producto_inexistente_devuelve_lista_vacia (xfail)` |

## Pasos para reproducir
GET /buscar?producto=asdfghjk&presupuesto=1000000

## Resultado esperado
Lista de opciones vacía: ninguna tienda tiene ese producto.

## Resultado obtenido
39 productos sin relación (el primero es un sticker de Falabella).

## Notas
Hipótesis, sin confirmar: los buscadores de las tiendas devuelven sugerencias aunque no haya coincidencia y Picksy no filtra por relevancia. Decidir con Requerimientos qué significa «relevante» (el ERS no lo define).

## Historial de estados
| Fecha | Estado | Quién | Comentario |
|---|---|---|---|
| 2026-10-28 | Abierto | QA | Registrado |
