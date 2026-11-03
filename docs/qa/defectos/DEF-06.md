# DEF-06 · schema.sql no crea las columnas ni la tabla del 2FA: el login da error 500 en una base nueva

| Campo | Valor |
|---|---|
| Requisito | RF-02 (inicio de sesión) · afecta a todo entorno nuevo |
| Severidad | **Crítica** en una instalación nueva (nadie puede iniciar sesión) |
| Prioridad (la fija Requerimientos) | Por definir (QA recomienda Urgente: bloquea el CI y el despliegue) |
| Versión del software | v2 |
| Entorno | Base creada con preparar_base.py + schema.sql de la v2 (como lo hace el CI de GitHub) |
| Estado | **Abierto** (nuevo, confirmado por QA) |
| Frecuencia | Siempre |
| Prueba que lo detecta | `qa/test_esquema.py::test_el_esquema_de_la_base_tiene_todo_lo_que_usa_el_codigo` (y 21 casos de autenticación, historial y seguridad fallan con 500) |

## Pasos para reproducir
1. Crear una base nueva con `python preparar_base.py` usando el `schema.sql` de la v2.
2. `POST /auth/registro` con un correo y una contraseña válidos (funciona).
3. `POST /auth/login` con esas mismas credenciales.

## Resultado esperado
200 con el token de sesión.

## Resultado obtenido
500. El error de la base de datos es: `column "totp_activo" does not exist`.

## Qué falta en schema.sql (6 piezas, detectadas por el bot)
- Columnas de `usuarios`: `totp_secreto`, `totp_activo`, `totp_ultimo_paso`.
- La tabla `login_pendientes` (la usan auth.py y dos_factores.py).

## Propuesta (inferida del código; Backend debe validarla con su base real)
```sql
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS totp_secreto VARCHAR(64);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS totp_activo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS totp_ultimo_paso BIGINT NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS login_pendientes (
  token VARCHAR(64) PRIMARY KEY,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  expira_en TIMESTAMPTZ NOT NULL,
  intentos INTEGER NOT NULL DEFAULT 0
);
```

## Notas
- A Backend le funciona porque su base local ya tiene esas columnas (se agregaron a mano). Por eso el error solo aparece en una base nueva.
- Con el esquema completo, la v2 pasa 163 casos del bot (ver hallazgos_2026-10-29_v2.md).
- El zip de la v2 tampoco traía preparar_base.py: confirmar que no se borró del repositorio.

## Historial de estados
| Fecha | Estado | Quién | Comentario |
|---|---|---|---|
| 2026-10-29 | Abierto | QA | Registrado |
