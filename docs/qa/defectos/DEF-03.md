# DEF-03 · Un producto de solo espacios pasa la validación y se consulta con término vacío

| Campo | Valor |
|---|---|
| Requisito | RF-07 |
| Severidad | Media |
| Prioridad (la fija Requerimientos) | Por definir |
| Versión del software | v1 |
| Entorno | Tiendas simuladas (verificado en el bot); en producción afectaría a tiendas reales |
| Estado | **Abierto** (nuevo, confirmado por QA) |
| Frecuencia | Siempre. Hallado el 28-oct-2026 por el bot de QA. |
| Prueba que lo detecta | `qa/test_busqueda_reglas.py::test_cp07_3_producto_de_solo_espacios_se_rechaza (xfail)` |

## Pasos para reproducir
GET /buscar?producto=%20%20&presupuesto=500000

## Resultado esperado
422: el producto es obligatorio (ERS RF-07).

## Resultado obtenido
200 con resultados. La API consulta cada tienda con término vacío ('').

## Notas
Causa probable: busqueda.py valida min_length=2 sobre el texto con espacios y recién después aplica strip(). Además envía consultas vacías a las tiendas reales.

## Historial de estados
| Fecha | Estado | Quién | Comentario |
|---|---|---|---|
| 2026-10-28 | Abierto | QA | Registrado |
