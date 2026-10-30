# Matriz de trazabilidad (generada por el bot)

Ejecución `41094725067-1` · 2026-10-30 16:59:51 UTC · commit `63cc9f0` · versión v1

| Requisito | Prioridad | Título | Estado | Casos que lo cubren |
|---|---|---|---|---|
| RF-01 | Alta | Registro con correo y contraseña | Sin prueba | - |
| RF-02 | Alta | Inicio y cierre de sesión seguros | Sin prueba | - |
| RF-03 | Media | Sesión activa que expira de forma controlada | Sin prueba | - |
| RF-04 | Alta | Precio, envío y disponibilidad de las 10 tiendas | Falló | test_humo_conector_responde_con_productos_validos[\xc9xito] (passed)<br>test_humo_conector_responde_con_productos_validos[Ol\xedmpica] (passed)<br>test_humo_conector_responde_con_productos_validos[Homecenter] (passed)<br>test_humo_conector_responde_con_productos_validos[Falabella] (passed)<br>test_humo_conector_responde_con_productos_validos[Alkosto] (passed)<br>test_humo_conector_responde_con_productos_validos[Ktronix] (passed)<br>test_humo_conector_responde_con_productos_validos[Alkomprar] (passed)<br>test_humo_conector_responde_con_productos_validos[Buscalibre] (failed)<br>test_humo_conector_responde_con_productos_validos[Farmatodo] (passed) |
| RF-05 | Alta | Caché con vigencia y fecha de actualización | Sin prueba | - |
| RF-06 | Alta | Tienda caída - avisa y continúa con las demás | Sin prueba | - |
| RF-07 | Alta | Entrada de producto y presupuesto máximo | Sin prueba | - |
| RF-08 | Alta | Total = precio + envío | Sin prueba | - |
| RF-09 | Alta | Descarta opciones sobre el presupuesto | Sin prueba | - |
| RF-10 | Alta | Ordena viables por total ascendente | Sin prueba | - |
| RF-11 | Alta | Mejor opción y ahorro | Bloqueado (A-02) | - |
| RF-12 | Alta | Enlace a la tienda original | Sin prueba | - |
| RF-13 | Alta | Lista de productos con prioridad | No implementado (v1) | - |
| RF-14 | Alta | Mochila 0/1 | No implementado (v1) | - |
| RF-15 | Media | Guarda las búsquedas del usuario | Sin prueba | - |
| RF-16 | Media | Variación de precios en el tiempo | No implementado (v1) | - |
| RF-17 | Media | Comparar carritos | No implementado (v1) | - |
| RNF-01 | - | Búsqueda en menos de 5 s con caché | Sin prueba | - |
| RNF-02 | - | Hash bcrypt, HTTPS y consultas parametrizadas | Sin prueba | - |
| RNF-03 | - | Usabilidad - flujo en pocos pasos | Revisión manual pendiente | - |
| RNF-04 | - | Compatibilidad con navegadores y responsivo | Revisión manual pendiente | - |
| RNF-05 | - | La caída de una tienda no deja el sistema fuera de servicio | Sin prueba | - |
| RNF-06 | - | Subsistemas independientes | Revisión manual pendiente | - |
| RNF-07 | - | Ley 1581 y términos de uso de las tiendas | Revisión manual pendiente | - |
| RNF-08 | - | Fecha y hora de actualización en cada precio | Sin prueba | - |
