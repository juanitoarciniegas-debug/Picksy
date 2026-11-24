# Roles y permisos de Picksy

Picksy tiene **6 roles**. No existe el rol "invitado": por orden del profesor **nadie entra sin registrarse**
(quien no tiene sesión solo puede registrarse, iniciar sesión o recuperar su contraseña).

## Qué puede hacer cada rol

| Permiso | usuario | premium | soporte | analista | moderador_tiendas | admin |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Buscar, mochila, historial, membresía y pagos | sí | sí | sí | sí | sí | sí |
| Búsquedas por día | **30** (sin membresía) | sin límite | sin límite | sin límite | sin límite | sin límite |
| Ver usuarios, desbloquear cuentas y cerrar sesiones (`/soporte`) | no | no | **sí** | no | no | sí |
| Ver estadísticas agregadas (`/analista`) | no | no | no | **sí** | no | sí |
| Activar o desactivar tiendas (`/moderacion`) | no | no | no | no | **sí** | sí |
| Ver/borrar usuarios y cambiar roles (`/admin`) | no | no | no | no | no | **sí** |

Reglas importantes:

- **Premium** es quien tiene el rol `premium` **o** una membresía vigente (aunque su rol siga siendo `usuario`).
  Cuando la membresía vence, vuelve a tener el límite diario.
- El límite diario se reinicia a **medianoche, hora de Colombia**. Borrar el historial **no** lo reinicia.
  Al pasarse responde `429` con la cabecera `Retry-After` (segundos que faltan).
- **Soporte** nunca ve contraseñas, secretos del Authenticator ni códigos de recuperación, y **no puede tocar
  cuentas de administrador** (solo otro administrador puede).
- **Analista** solo recibe números agregados: ningún endpoint le devuelve correos ni quién buscó qué.
- **Moderador**: una tienda desactivada no se consulta, no sale en los resultados (ni aunque estuviera en la caché)
  y no aparece en `/tiendas`. Se vuelve a activar con el mismo endpoint. No se borra nada.
- **Admin** puede todo lo de los demás roles. Un admin no puede cambiarse el rol ni borrarse a sí mismo, y siempre
  queda al menos un admin.
- Ninguna ruta pública asigna roles: el registro nace siempre como `usuario`, aunque mande otro valor.

## Cómo se asigna un rol

1. **Desde la API (lo normal):** un administrador llama `PATCH /api/v1/admin/usuarios/{id}/rol` con
   `{"rol": "soporte"}` (valores: `usuario`, `premium`, `soporte`, `analista`, `moderador_tiendas`, `admin`).
2. **Desde el servidor (si no hay ningún admin o para la demostración):**
   `cd ~/picksy/backend && source venv/bin/activate && python crear_admin.py` crea o ascienda al primer administrador.

## Endpoints nuevos

| Método y ruta | Rol | Qué hace |
|---|---|---|
| `GET /api/v1/auth/me` | cualquiera | (ya existía) ahora también trae `premium`, `limite_diario`, `busquedas_hoy` y `busquedas_restantes` (`null` = sin límite) |
| `GET /api/v1/soporte/usuarios?q=&pagina=&limite=` | soporte | busca usuarios por correo (total en la cabecera `X-Total-Count`) |
| `GET /api/v1/soporte/usuarios/{id}` | soporte | ficha: membresía, búsquedas de hoy, sesiones abiertas |
| `POST /api/v1/soporte/usuarios/{id}/desbloquear` | soporte | quita el bloqueo por intentos fallidos |
| `POST /api/v1/soporte/usuarios/{id}/cerrar-sesiones` | soporte | cierra todas las sesiones de esa cuenta |
| `GET /api/v1/analista/resumen` | analista | usuarios por rol, membresías, pagos (simulados) y búsquedas por día (14 días) |
| `GET /api/v1/analista/busquedas-populares?dias=&limite=` | analista | lo que más se busca |
| `GET /api/v1/analista/tiendas-ganadoras?dias=&limite=` | analista | tiendas que más veces dieron la mejor opción |
| `GET /api/v1/moderacion/tiendas` | moderador | las tiendas de Picksy y si están activas |
| `PATCH /api/v1/moderacion/tiendas/{id}` | moderador | `{"activa": true\|false}` |

Un rol sin permiso recibe `403`; sin sesión, `401`.

## Configuración

`BUSQUEDAS_DIARIAS_USUARIO` en el `.env` (por defecto **30**). `0` = sin límite para todos: **ponlo en 0 antes de
una prueba de carga**, porque una sola cuenta haciendo muchas búsquedas toparía con el límite y se vería como falla.
Después de cambiarlo: `sudo systemctl restart picksy`.

## Qué tocó este cambio en la base de datos

- La restricción de `usuarios.rol` ahora acepta los 6 roles (`preparar_base.py` la actualiza sola, una vez; se puede repetir).
- Tabla nueva `uso_diario` (búsquedas por cuenta y día). No se borra nada existente.
