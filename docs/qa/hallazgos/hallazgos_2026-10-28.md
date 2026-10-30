# Hallazgos de QA al revisar el código de la v1 (28-oct-2026)

Salen de leer main.py, busqueda.py, buscador.py, cache.py, auth.py, historial.py, schema.sql y el frontend,
y de ejecutar el bot de QA (123 casos pasan, 4 defectos conocidos).

## Defectos nuevos (ver carpeta defectos/)
DEF-03 (producto de solo espacios), DEF-04 (presupuesto «inf» da 500), DEF-05 (tiendas sin resultados no se cachean).

## Requisitos que NO existen en la v1 (verificado en el contrato de la API y en el frontend)
| Requisito | Qué falta |
|---|---|
| RF-13 | Lista de productos con prioridad: no hay ruta ni pantalla |
| RF-14 | Mochila 0/1: no hay ruta ni pantalla («Mochilas» en la página es solo un botón de búsqueda) |
| RF-16 | Variación de precios: la tabla precios guarda las «fotos», pero ninguna ruta las expone |
| RF-17 | Comparar carritos: existen las tablas carritos y carrito_items, pero ninguna ruta |

Esto cambia la matriz del plan: esos cuatro pasan de «Sin probar» a «No implementado (v1)». Falta confirmar con Backend si
llegarán en la v2 (tareas B-05 y B-06 del ERS).

## Observaciones al ERS y al equipo
| ID | Observación |
|---|---|
| OBS-11 | El código calcula el ahorro como «más cara VIABLE menos la mejor». La propuesta A-02 dice «más cara CONSULTADA menos la mejor». Hay que decidir A-02: son resultados distintos. |
| OBS-12 | Si el envío no se informa, el total cuenta el envío como 0 (queda marcado con envio_confirmado=false). El ERS no dice qué hacer (A-06). |
| OBS-13 | RF-04 pide «disponibilidad» por tienda; la API solo excluye los agotados y devuelve un contador. No hay un campo de disponibilidad por opción. |
| OBS-14 | La contraseña acepta máximo 50 caracteres (el ERS no define máximo). |
| OBS-15 | test_buscador.py y test_cache.py son scripts, no pruebas: hacen búsquedas reales al importarse. Un «pytest» a secas los ejecutaría. Conviene renombrarlos (por ejemplo probar_buscador.py). |
| OBS-16 | requirements.txt está en UTF-16 y no incluye pytest ni pytest-html. QA agrega requirements-qa.txt. |
| OBS-17 | .env.example tiene espacios al inicio de cada línea. |

## Lo que sí está bien (verificado por el bot)
Registro, login, mensajes que no revelan qué dato falló, cierre de sesión, expiración a 24 h, hash bcrypt con sal, historial aislado entre usuarios,
cálculo del total, descarte por presupuesto (incluidos los bordes exactos), orden ascendente, caída y lentitud de tiendas, vigencia de caché a 24 h,
protección frente a inyección SQL en todas las entradas probadas.
