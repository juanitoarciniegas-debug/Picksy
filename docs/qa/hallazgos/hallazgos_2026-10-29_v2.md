# Revisión de QA de la versión 2 (29-oct-2026)

Se ejecutó el bot sobre el backend v2 en una base nueva (preparar_base.py + schema.sql), y se leyó el código y el frontend.

## Resultado
| Situación | Resultado |
|---|---|
| v2 con schema.sql tal como llegó | **21 casos fallan** (login da 500): ver DEF-06 |
| v2 con el esquema completo | **163 pasan**, 1 alarma de contrato (esperada), 1 defecto abierto, 3 posiblemente corregidos, 10 omitidas |
| Los 20 casos rápidos de test_api.py sobre la v2 | 20 pasan |

## Lo que Backend corrigió (verificado por el bot)
| Defecto | Cambio | Estado de QA |
|---|---|---|
| DEF-03 | El producto se limpia antes de medir su largo; se rechazan los de solo espacios | Corregido (falta confirmar en el CI) |
| DEF-04 | `allow_inf_nan=False` y presupuesto máximo de 1.000.000.000 | Corregido (falta confirmar en el CI) |
| DEF-05 | Las tiendas sin resultados se guardan 30 minutos; las que fallan NO se guardan como vacías | Corregido (falta confirmar en el CI) |

## Lo que sigue igual
- DEF-02: los conectores no cambiaron (sigue faltando Mercado Libre).
- DEF-01: no cambió la lógica de relevancia (se verifica con tiendas reales).
- RF-13, RF-14, RF-16 y RF-17: siguen sin ruta ni pantalla.
- A-02 (ahorro): sin cambio.

## Cambio de contrato de la API (el bot lo detectó solo)
RUTA NUEVA: POST /auth/2fa/configurar, /activar, /desactivar y /login · PARÁMETRO MODIFICADO: GET /buscar `presupuesto` (máximo 1.000.000.000).
QA aprueba la nueva referencia cuando la v2 llegue a main:
`python qa/actualizar_contrato.py --motivo "v2: 2FA (4 rutas) y presupuesto maximo (DEF-04)"`

## Verificación en dos pasos (2FA): función NUEVA sin requisito
El ERS (sección 11) pide un ID de requisito para toda funcionalidad. QA la prueba como **RF-18 (propuesto)**, que no cuenta en «X de 25».
Requerimientos debe aprobarla, rechazarla o pedir que se retire.
- **23 casos automáticos pasan.** Para comprobar que no son pruebas vacías se rompió el código a propósito de 3 maneras (login sin pedir código, reutilizar un código, intentos ilimitados) y el bot lo detectó cada vez.
- Verificado: la contraseña sola no da sesión, el token temporal no sirve como sesión, el código no se reutiliza, 5 intentos fallidos invalidan el inicio de sesión, el token temporal vence y es de un solo uso, desactivar pide contraseña y código, el secreto no se expone, y el mensaje de error no revela qué dato falló.

### Observaciones sobre el 2FA
| ID | Observación |
|---|---|
| OBS-19 | **No hay códigos de recuperación.** Si el usuario pierde el teléfono, no puede entrar ni desactivar el 2FA (desactivar también pide el código): queda fuera de su cuenta. La pantalla verificar-2fa ofrece «Utilizar un código de recuperación», pero el propio código dice que el backend no lo tiene. |
| OBS-20 | El límite de 5 intentos es **por inicio de sesión, no por usuario**: quien conoce la contraseña puede pedir otro inicio de sesión y volver a intentar (revisión del código, no ejecutada). Conviene un límite por usuario. |
| OBS-21 | Activar el 2FA no cierra las sesiones que ya estaban abiertas (comportamiento actual, probado en CP-18.12). |

## Frontend v2
| ID | Observación |
|---|---|
| OBS-22 | La página «Recuperar contraseña» (enlace «¿La olvidaste?» del login) no está conectada al backend; su propio mensaje lo dice. No hay recuperación de contraseña en el ERS ni en la API. Un usuario la verá como una función que no funciona. |
| OBS-23 | En login.html se quitó el id `forgotPassword`. Las pruebas de navegador dependen de IDs estables: avisar antes de cambiarlos. |
| OBS-24 | main.py ya no responde /favicon.ico: el navegador recibirá 404 (cosmético). |
