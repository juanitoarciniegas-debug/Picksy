# Bot de QA · Versión 3 del software (rama `version-3`)

Esta rama toma la `version-2` y le pone encima el backend nuevo (versión 3) con el bot de QA adaptado.
Las versiones siguen separadas por rama: `main` = v1 · `version-2` = v2 · **`version-3` = v3**.

## Qué cambió en el software (v3) y cómo lo cubre el bot

| Novedad de la v3 | Archivo de pruebas | Requisito |
|---|---|---|
| Registro en 2 pasos con QR de Google Authenticator; login en 2 pasos; 2FA **obligatorio** (ya no se puede apagar) | `test_autenticacion.py`, `test_dos_factores.py` | RF-01, RF-02, RF-18* |
| Sesión de 2 h (configurable), bloqueo 429 por intentos, secreto 2FA cifrado | `test_autenticacion.py`, `test_dos_factores.py` | RF-03, RNF-02, RNF-09* |
| Cuentas antiguas sin Authenticator lo configuran en su primer login | `test_autenticacion.py` | RF-02 |
| Códigos de recuperación (8, un solo uso) y "olvidé mi contraseña" | `test_dos_factores.py`, `test_recuperacion.py` | RF-20* |
| Roles `usuario` / `admin` y panel de administrador | `test_roles_admin.py` | RF-19* |
| `/buscar` y `/tiendas` exigen sesión (401 sin ella) | `test_historial.py`, `test_autenticacion.py` | RF-02, RF-15 |
| Filtro de relevancia (DEF-01) y alias "PlayStation 5" = "PS5" | `test_relevancia.py` | RF-04 |
| Historial paginado (`pagina`, `limite`, `X-Total-Count`) | `test_historial.py` | RF-15 |
| Carritos con prioridad 1-5 (límites 30 carritos / 50 productos) | `test_carritos.py` | RF-13 |
| Mochila 0/1, comparada contra el oráculo de fuerza bruta (`referencia_mochila.py`) | `test_mochila.py` | RF-14 |
| Comparar carritos | `test_comparar_precios.py` | RF-17 |
| Variación de precios | `test_comparar_precios.py` | RF-16 |
| API en `/api/v1`, errores con formato único, CORS, `/api/v1/salud` | `test_api_errores.py` | RNF-10* |

\* Funciones que existen en el código pero **no tienen ID en el ERS**. Se registran como "propuestas" en
`requisitos.yml` (no cuentan en el "X de 25"). Requerimientos debe aprobarlas, cambiarles el ID o retirarlas.

## Cambios en el propio bot

- `ayudas.py`: ahora automatiza el flujo real (registro → código → login → código) con `pyotp`. Funciones nuevas:
  `crear_cuenta`, `cuenta_con_sesion`, `admin_con_sesion`, `codigo_totp`, `crear_carrito`, `agregar_item`...
  `/buscar` usa por defecto una sesión de QA (`cabecera_por_defecto`); `SIN_SESION` pide sin sesión.
- `conftest.py`: reinicia el limitador de intentos antes de cada caso y limpia las tablas nuevas.
- `mocks.py`: como ahora /buscar oculta lo que no se parece a lo buscado, la tienda simulada pone el término
  en el nombre (`relevantes=True`). Las pruebas del propio filtro usan `relevantes=False`.
- `requisitos.yml`: RF-13, RF-14, RF-16 y RF-17 pasan de "no implementado" a probados; se agregan RF-19, RF-20, RNF-09 y RNF-10 como propuestos.
- `test_api.py`: adaptado al registro/login en 2 pasos y a que buscar exige sesión.
- Workflows: `qa.yml` también corre en cada push a `version-3`; la columna `version_software` del historial dice `v3`.
- **Contrato (`referencia/openapi.snapshot.json`)**: se regeneró para `/api/v1` (32 operaciones). Está explicado en `CAMBIOS.md`.
  La regla de oro dice que el bot nunca actualiza su referencia solo: **Juan debe revisar ese commit y aprobarlo**.

## Lo que el bot encontró en el backend (y ya quedó corregido en esta rama)

1. **Buscar `ps5` no encontraba "PlayStation 5"** (`relevancia.py`): la búsqueda pegada ("ps5", "iphone15") no coincidía con el producto escrito con espacio.
   Además `a5` coincidía con "Galaxy A54". Corregido. Pruebas: `test_relevancia.py` (`cp04_3h`, `cp04_3k`).
2. **DEF-07: un JSON con `NaN` o `Infinity` daba error 500** en cualquier ruta con cuerpo (`errores.py`): el error de validación repetía el valor y no se podía escribir. Ahora responde 422. Prueba: `test_api_errores.py::test_cp21_6`.

## Estado de la última ejecución local (base PostgreSQL 16 limpia)

389 pasaron · 0 fallaron · 1 defecto abierto (DEF-02: 9 tiendas, el ERS dice 10) · 3 "posiblemente corregidos" (DEF-03, DEF-04, DEF-05, que QA debe verificar y cerrar quitando su `xfail`) · 10 omitidas (9 tiendas reales + 1 bloqueada por la ambigüedad A-02).

Con el bot de la v2 sobre el backend de la v3 fallaban **98** casos (casi todos porque el login ya no entrega sesión con la contraseña sola).

## Pendiente (decisión de QA o de otros)

- Las pruebas con **tiendas reales** (`test_humo_conectores.py` y las `slow` de `test_api.py`) no se pudieron correr fuera de GitHub; las ejecuta el flujo diario.
- No hay pruebas de navegador (Playwright) todavía: dependen de que el frontend lleve `data-testid`.
- DEF-02 (Mercado Libre), A-02 (regla del ahorro) y A-03 (escala de prioridad 1-5) siguen abiertos.
- Los archivos de defectos (`docs/qa/defectos/`) viven en la rama `qa-registros`: DEF-07 hay que registrarlo ahí.

## Cómo correrlo

```
cd Picksy_Backend
pip install -r requirements.txt -r requirements-qa.txt
python preparar_base.py          # con DB_NAME=smartbudget_test en el .env
pytest qa -v
pytest test_api.py -v -m "not slow"
```
