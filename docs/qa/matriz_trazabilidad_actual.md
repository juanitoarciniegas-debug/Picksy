# Matriz de trazabilidad (generada por el bot)

Ejecución `44932669011-1` · 2026-11-21 17:56:29 UTC · commit `afe9fe8` · versión v3

| Requisito | Prioridad | Título | Estado | Casos que lo cubren |
|---|---|---|---|---|
| RF-01 | Alta | Registro con correo y contraseña | Sin prueba | - |
| RF-02 | Alta | Inicio y cierre de sesión seguros | Sin prueba | - |
| RF-03 | Media | Sesión activa que expira de forma controlada | Sin prueba | - |
| RF-04 | Alta | Precio, envío y disponibilidad de las 10 tiendas | Falló | test_humo_conector_responde_con_productos_validos[\xc9xito] (failed)<br>test_humo_conector_responde_con_productos_validos[Ol\xedmpica] (passed)<br>test_humo_conector_responde_con_productos_validos[Homecenter] (passed)<br>test_humo_conector_responde_con_productos_validos[Falabella] (passed)<br>test_humo_conector_responde_con_productos_validos[Alkosto] (passed)<br>test_humo_conector_responde_con_productos_validos[Ktronix] (passed)<br>test_humo_conector_responde_con_productos_validos[Alkomprar] (passed)<br>test_humo_conector_responde_con_productos_validos[Buscalibre] (failed)<br>test_humo_conector_responde_con_productos_validos[Farmatodo] (passed) |
| RF-05 | Alta | Caché con vigencia y fecha de actualización | Sin prueba | - |
| RF-06 | Alta | Tienda caída - avisa y continúa con las demás | Sin prueba | - |
| RF-07 | Alta | Entrada de producto y presupuesto máximo | Sin prueba | - |
| RF-08 | Alta | Total = precio + envío | Sin prueba | - |
| RF-09 | Alta | Descarta opciones sobre el presupuesto | Sin prueba | - |
| RF-10 | Alta | Ordena viables por total ascendente | Sin prueba | - |
| RF-11 | Alta | Mejor opción y ahorro | Bloqueado (A-02) | - |
| RF-12 | Alta | Enlace a la tienda original | Sin prueba | - |
| RF-13 | Alta | Lista de productos con prioridad (carritos) | Bloqueado (A-03) | - |
| RF-14 | Alta | Mochila 0/1 | Sin prueba | - |
| RF-15 | Media | Guarda las búsquedas del usuario | Sin prueba | - |
| RF-16 | Media | Variación de precios en el tiempo | Sin prueba | - |
| RF-17 | Media | Comparar carritos | Sin prueba | - |
| RNF-01 | - | Búsqueda en menos de 5 s con caché | Sin prueba | - |
| RNF-02 | - | Hash bcrypt, HTTPS y consultas parametrizadas | Sin prueba | - |
| RNF-03 | - | Usabilidad - flujo en pocos pasos | Revisión manual pendiente | - |
| RNF-04 | - | Compatibilidad con navegadores y responsivo | Revisión manual pendiente | - |
| RNF-05 | - | La caída de una tienda no deja el sistema fuera de servicio | Sin prueba | - |
| RNF-06 | - | Subsistemas independientes | Revisión manual pendiente | - |
| RNF-07 | - | Ley 1581 y términos de uso de las tiendas | Revisión manual pendiente | - |
| RNF-08 | - | Fecha y hora de actualización en cada precio | Sin prueba | - |
| RF-18 | - | Verificación en dos pasos (2FA) con TOTP - PROPUESTO por QA | Sin prueba [propuesto, sin aprobar en el ERS] | - |
| RF-19 | - | Roles y panel de administrador - PROPUESTO por QA | Sin prueba [propuesto, sin aprobar en el ERS] | - |
| RF-20 | - | Recuperar contraseña y códigos de recuperación del 2FA - PROPUESTO por QA | Sin prueba [propuesto, sin aprobar en el ERS] | - |
| RNF-09 | - | Límite de intentos (429) contra fuerza bruta y abuso - PROPUESTO por QA | Sin prueba [propuesto, sin aprobar en el ERS] | - |
| RNF-10 | - | API versionada (/api/v1), errores en formato unificado y CORS configurable - PROPUESTO por QA | Sin prueba [propuesto, sin aprobar en el ERS] | - |
| RF-21 | - | Membresía de pago y pagos simulados - PROPUESTO por QA | Sin prueba [propuesto, sin aprobar en el ERS] | - |
| RF-22 | - | Correos de aviso: inicio de sesión, recuperar contraseña y pagos - PROPUESTO por QA | Sin prueba [propuesto, sin aprobar en el ERS] | - |
| RNF-11 | - | Datos de pago mínimos: nunca se guarda el número completo de la tarjeta ni el CVV - PROPUESTO por QA | Sin prueba [propuesto, sin aprobar en el ERS] | - |
