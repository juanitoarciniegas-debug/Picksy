# Cambios aprobados del contrato de la API

| Fecha | Motivo | Diferencias |
|---|---|---|
| 2026-10-28 | Línea base v1 (28-oct-2026) | (primera referencia: línea base) |
| 2026-11-07 | **Versión 3** (rama `version-3`). Aprobado al adaptar el bot; Juan debe confirmarlo en la revisión | Todas las rutas pasan a `/api/v1/...` (las sin versión siguen vivas pero ocultas). NUEVAS: registro en 2 pasos (`/auth/registro/confirmar`), `/auth/2fa/login`, `/auth/2fa/pendiente/*`, `/auth/2fa/codigos-recuperacion`, `/auth/recuperar*`, `/admin/usuarios*`, `/carritos*` (RF-13/14/17), `/productos/precios` (RF-16), `/salud`. `/buscar` y `/tiendas` ahora exigen sesión (401). `/historial` con `pagina`/`limite` y cabecera `X-Total-Count`. |
| 2026-11-09 | Version 4: rutas de pagos (/api/v1/pagos, metodos, membresia, planes) | RUTA NUEVA: DELETE /api/v1/pagos/metodos/{metodo_id}; RUTA NUEVA: GET /api/v1/pagos; RUTA NUEVA: GET /api/v1/pagos/membresia; RUTA NUEVA: GET /api/v1/pagos/metodos; RUTA NUEVA: GET /api/v1/pagos/planes; RUTA NUEVA: GET /api/v1/pagos/{pago_id}; RUTA NUEVA: POST /api/v1/pagos; RUTA NUEVA: POST /api/v1/pagos/metodos; RUTA NUEVA: POST /api/v1/pagos/{pago_id}/cancelar; RUTA NUEVA: POST /api/v1/pagos/{pago_id}/confirmar |
