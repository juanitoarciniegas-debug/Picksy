# DEF-05 · Las tiendas sin resultados no se guardan en caché y se consultan en cada búsqueda repetida

| Campo | Valor |
|---|---|
| Requisito | RF-05 |
| Severidad | Media |
| Prioridad (la fija Requerimientos) | Por definir |
| Versión del software | v1 |
| Entorno | Tiendas simuladas; el efecto real es más tráfico hacia tiendas reales |
| Estado | **Abierto** (nuevo, confirmado por QA) |
| Frecuencia | Siempre. Hallado el 28-oct-2026 por el bot de QA. |
| Prueba que lo detecta | `qa/test_cache_reglas.py::test_cp05_5_tiendas_sin_resultados_tampoco_se_vuelven_a_consultar (xfail)` |

## Pasos para reproducir
Buscar dos veces el mismo producto que solo vende una tienda y contar las consultas a tiendas

## Resultado esperado
La segunda búsqueda no consulta ninguna tienda (criterio de aceptación de RF-05).

## Resultado obtenido
La segunda búsqueda vuelve a consultar las 8 tiendas que no tenían el producto (17 consultas en total en vez de 9).

## Notas
cache.py solo guarda «si hubo resultados» (decisión de diseño visible en buscador.py). Puede ser intencional para no cachear fallos como «vacío»: Backend y Requerimientos deciden. Si se mantiene, hay que ajustar el criterio de RF-05.

## Historial de estados
| Fecha | Estado | Quién | Comentario |
|---|---|---|---|
| 2026-10-28 | Abierto | QA | Registrado |
