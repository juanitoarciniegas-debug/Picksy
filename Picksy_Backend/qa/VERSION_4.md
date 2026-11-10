# Versión 4: qué cambió en el bot de QA

La v4 trae **membresía de pago, correos de aviso** y ajustes del frontend. El bot se adaptó así.

## Pruebas nuevas

| Archivo | Cubre | Requisito |
|---|---|---|
| `test_pagos.py` | Planes y precios, métodos de pago, flujo del pago (pendiente / pagado / cancelado / vencido), suma y reactivación de la membresía, límite de pagos por hora | RF-21 (propuesto), RNF-09 |
| `test_pagos.py` | **Aislamiento entre usuarios:** nadie ve, paga, confirma, cancela ni borra lo de otro (404). Un pago no se confirma dos veces (409). Sin sesión: 401 en todas las rutas | RF-21 |
| `test_pagos.py` | Nunca se guarda ni se devuelve el número completo de la tarjeta ni el CVV; la base no tiene columnas para eso | RNF-11 (propuesto) |
| `test_correos.py` | Aviso de inicio de sesión, instrucciones para recuperar la contraseña, aviso de cambio de clave, correos de pago iniciado / confirmado / cancelado. Quién los recibe y cuándo **no** se envían | RF-22 (propuesto) |

Los correos no salen de verdad: se intercepta `correos.enviar` y se lee lo que habría enviado.
Los usuarios de prueba son `qa_*@test.com` y los borra la limpieza del bot (los pagos y métodos se van en cascada).

## Requisitos nuevos en `requisitos.yml`

RF-21, RF-22 y RNF-11 quedan como **propuestos**: existen en el código pero no están en el ERS, así que no cuentan en "X de 25".
Requerimientos debe aprobarlos, rechazarlos o pedir que se retiren (igual que RF-18 a RF-20).

## Arreglos del propio bot

1. **`actualizar_contrato.py` recortaba `CAMBIOS.md`.** Cortaba la línea a 300 caracteres y la fila de la v4 quedó con 7 de las 10 rutas de pagos (terminaba en `POST /api/v1 |`). Ahora escribe todas las diferencias y escapa el carácter `|`. La fila de la v4 se completó con las 10 rutas reales (no cambia el contrato aprobado: es el mismo `openapi.snapshot.json`). Hay una prueba que lo protege (`test_requisitos.py`).
2. **La versión del historial** (`version_software`) ahora dice `v4` en `qa.yml`, `conftest.py` y `registrar.py`.

## Lo que sigue pendiente (decisión de QA o de Requerimientos)

- Aprobar o rechazar RF-21, RF-22 y RNF-11 como requisitos.
- Decisiones abiertas desde la v3: A-02, DEF-02 y A-03 (ver `DECISIONES_V3.md`).
- Los pagos son **simulados**: cuando haya pasarela real (Wompi, PayU, etc.) hay que rehacer las pruebas de pago y el contrato.
- Que el correo llegue a la bandeja y no a spam solo se puede verificar en un despliegue con SMTP real.
- La membresía todavía no limita ninguna función de la página.
