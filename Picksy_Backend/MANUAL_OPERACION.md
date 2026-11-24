# Manual de operación de Picksy

Este manual dice **cómo mantener Picksy funcionando después de instalarlo**: revisar que esté sano, actualizarlo, hacer y
restaurar respaldos, recibir alertas, medir su rendimiento, mejorar su disponibilidad y, al final de su vida, retirarlo
con orden. La instalación inicial está en [`DESPLIEGUE_AWS.md`](DESPLIEGUE_AWS.md).

Todos los comandos se escriben **en el servidor** (entras con `ssh -i TU_LLAVE.pem ubuntu@IP_DEL_SERVIDOR`), salvo los que
dicen "en tu computador". Las rutas suponen la instalación de la guía: `/home/ubuntu/picksy/backend`.

**Regla de oro:** antes de cambiar cualquier cosa del servidor, haz un respaldo (sección 3) y una copia del archivo que vas a editar.

## 1. Revisar que todo esté sano

```bash
systemctl is-active picksy nginx postgresql          # los tres deben decir "active"
curl -s http://127.0.0.1:8000/api/v1/salud           # {"estado":"ok"}  (si la base falla responde 503)
sudo journalctl -u picksy -n 50 --no-pager           # últimas líneas del log de la API
sudo journalctl -u picksy --since "1 hour ago" | grep -E "TIENDA_FALLO|TIENDA_REINTENTO|LIMITADOR"   # fallas de tiendas y de Redis
df -h /                                              # espacio en disco (que no pase del 80 %)
free -m                                              # memoria
systemctl list-timers | grep certbot                 # la renovación automática del certificado debe aparecer
```

Qué significan las marcas del log:

| Marca | Significa |
|---|---|
| `TIENDA_FALLO tienda=Éxito error=HTTPStatusError http=403` | La tienda falló. `http=403` = la tienda bloquea la IP del servidor |
| `TIENDA_REINTENTO ...` | Falló por un corte pasajero y se volvió a preguntar (normalmente se resuelve solo) |
| `TIENDA_LENTA ...` | La tienda no contestó dentro de los 8 s de la búsqueda |
| `LIMITADOR Redis no disponible` | Redis se cayó; el límite de intentos sigue con la memoria de cada instancia |

**Qué se recupera solo (no hay que hacer nada):** la API se reinicia sola si se cae (`Restart=always`), se reconecta sola
a PostgreSQL si este se reinicia, el certificado HTTPS se renueva solo (certbot) y el sistema muestra datos guardados si
una tienda no responde.

## 2. Actualizar la aplicación

```bash
cd ~/picksy/backend && source venv/bin/activate
pip install -r requirements.txt          # por si cambió alguna librería
python preparar_base.py                  # crea tablas nuevas si las hay (no borra datos)
sudo systemctl restart picksy            # con UNA instancia hay unos segundos sin servicio
curl -s http://127.0.0.1:8000/api/v1/salud
```

Con **2 instancias** (sección 5) se actualiza sin cortar el servicio: `bash ~/picksy/backend/despliegue/reiniciar_sin_cortes.sh`
reinicia una, espera a que responda y recién entonces reinicia la otra. Si una no vuelve, se detiene y deja la otra atendiendo.

**Volver atrás si una actualización sale mal:** restaura la copia del código que hizo tu script de despliegue antes de
subir lo nuevo y reinicia (`sudo systemctl restart picksy`). Si el problema fue de datos, usa el respaldo (sección 3).

Si subes scripts `.sh` desde Windows y fallan con `\r: command not found`, convierte los finales de línea:
`sed -i 's/\r$//' ~/picksy/backend/despliegue/*.sh`.

**Roles y límite diario:** el significado de cada rol está en `ROLES_Y_PERMISOS.md`. Al actualizar desde una versión sin roles,
`python preparar_base.py` actualiza solo la restricción de roles y crea la tabla `uso_diario`. Si vas a hacer una prueba de
carga, pon `BUSQUEDAS_DIARIAS_USUARIO=0` en el `.env` y reinicia (el límite diario de 30 búsquedas por cuenta se vería como fallas).

## 3. Respaldos y restauración

### 3.1 Hacer un respaldo (automático y a mano)

```bash
mkdir -p ~/picksy/respaldos
bash ~/picksy/backend/despliegue/respaldo.sh        # a mano: debe terminar con "OK respaldo: ...dump"
crontab -e                                          # automático: agrega esta línea al final y guarda
```
```
30 3 * * * /bin/bash /home/ubuntu/picksy/backend/despliegue/respaldo.sh >> /home/ubuntu/picksy/respaldos/respaldo.log 2>&1
```
Eso hace un respaldo todos los días a las 03:30 (hora del servidor, que es UTC: 22:30 en Colombia), comprueba que el
archivo sirva y borra los de más de 14 días. Verifica al día siguiente con `ls -lh ~/picksy/respaldos` y `tail ~/picksy/respaldos/respaldo.log`.

### 3.2 Sacar el respaldo de la máquina (importante)

Un respaldo que vive en el mismo servidor **no te salva si el servidor se pierde**. Cada semana (o antes de la entrega)
cópialo a tu computador. En PowerShell, **en tu computador**:

```powershell
scp -i "C:\ruta\TU_LLAVE.pem" ubuntu@IP_DEL_SERVIDOR:/home/ubuntu/picksy/respaldos/picksy_*.dump "C:\Respaldos Picksy\"
```
Alternativa: si tienes un bucket de S3 y AWS CLI en el servidor, define `RESPALDO_S3=s3://tu-bucket/picksy` en el cron y el
script lo sube solo. **Los respaldos contienen correos y datos de usuarios: guárdalos en un lugar privado, nunca en GitHub.**

### 3.3 Guardar `TOTP_CLAVE` (sin ella los respaldos no sirven)

El secreto de Google Authenticator de cada usuario está **cifrado** en la base con la `TOTP_CLAVE` del archivo `.env`. Si
pierdes esa clave, nadie podrá entrar con su código aunque restaures la base. Cópiala **una sola vez** a un gestor de
contraseñas (o un lugar privado del equipo), nunca a GitHub ni a un chat:

```bash
grep '^TOTP_CLAVE=' ~/picksy/backend/.env        # muestra la línea; cópiala y guárdala
chmod 600 ~/picksy/backend/.env                  # que solo el usuario ubuntu pueda leer el .env
```

### 3.4 Restaurar un respaldo

Se hace con el usuario `postgres` del servidor (`sudo -u postgres`), así no hace falta escribir la clave de la base, y se
le dice que los datos queden a nombre del usuario de la aplicación (`--role`). Primero **ensáyalo en una base de prueba**
(así sabes que el respaldo sirve sin tocar nada real):

```bash
cd ~/picksy/backend
DB_USER=$(grep -E '^DB_USER=' .env | cut -d= -f2-); DB_NAME=$(grep -E '^DB_NAME=' .env | cut -d= -f2-)   # solo nombres, no claves
ARCHIVO=~/picksy/respaldos/picksy_AAAAMMDD_HHMMSS.dump                     # elige el archivo (ls ~/picksy/respaldos)

sudo -u postgres createdb -O "$DB_USER" picksy_prueba
sudo -u postgres pg_restore --no-owner --role="$DB_USER" -d picksy_prueba < "$ARCHIVO" && echo "RESTAURACIÓN DE PRUEBA OK"
sudo -u postgres psql -d picksy_prueba -c "SELECT count(*) FROM tiendas;"   # debe dar 10
sudo -u postgres dropdb picksy_prueba
```

Restauración **de verdad** (deja la base exactamente como estaba en el respaldo; lo que se hizo después se pierde):

```bash
sudo systemctl stop picksy picksy-2 2>/dev/null        # que nadie escriba mientras se restaura (picksy-2 solo si lo activaste)
sudo -u postgres pg_restore --no-owner --role="$DB_USER" --clean --if-exists -d "$DB_NAME" < "$ARCHIVO"
sudo systemctl start picksy && sudo systemctl start picksy-2 2>/dev/null
curl -s http://127.0.0.1:8000/api/v1/salud
```
En una máquina nueva: instala PostgreSQL, crea el usuario y la base como en `DESPLIEGUE_AWS.md`, restaura el respaldo con los
mismos comandos y pon en el `.env` la **misma** `TOTP_CLAVE`. (Si la base está en RDS en vez de en el servidor, usa
`pg_restore -h ENDPOINT -U USUARIO ...` con la clave en la variable `PGPASSWORD`.)

## 4. Alertas

| Qué vigilar | Cómo | Quién avisa |
|---|---|---|
| Certificado HTTPS por vencer | `herramientas/alerta_certificado.py` (abajo) | Correo del sistema |
| El sitio se cae | Monitor externo gratuito (abajo) | Correo del monitor |
| La API se cae sola | `Restart=always` la levanta en 3 s; queda en `journalctl` | Nadie: se recupera sola |
| Vencimiento del dominio (Namecheap) | **Recordatorio en el calendario del equipo** 30 días antes | Una persona |

**Alerta de certificado** (red de seguridad por si certbot falla). En el `.env` del servidor agrega
`ALERTA_CORREO=correo-del-equipo@...` (y completa los `SMTP_*`, si no el aviso solo sale en el log) y programa una vez al día:

```bash
cd ~/picksy/backend && venv/bin/python herramientas/alerta_certificado.py --solo-ver     # prueba: debe decir cuántos días quedan
crontab -e      # agrega:
```
```
0 14 * * * cd /home/ubuntu/picksy/backend && /home/ubuntu/picksy/backend/venv/bin/python herramientas/alerta_certificado.py >> /home/ubuntu/picksy/respaldos/alerta.log 2>&1
```
Avisa por correo si faltan 14 días o menos (certbot renueva cuando faltan 30; si llegamos a 14, algo falla).

**Monitor externo "el sitio está caído"** (no se puede hacer desde el mismo servidor: si el servidor muere, no avisa nada).
Una opción gratuita es UptimeRobot: crea una cuenta, "Add New Monitor", tipo *HTTP(s)*, URL
`https://picksy.lat/api/v1/salud`, intervalo de 5 minutos y como contacto de alerta el correo del equipo. Como `/salud` responde
503 cuando la base de datos falla, el monitor avisa también de ese caso. (Los nombres de los botones pueden cambiar; la idea
es: vigilar esa URL cada pocos minutos y avisar por correo si no responde 200.)

## 5. Alta disponibilidad básica: 2 instancias de la API (OPCIONAL)

**Qué logra:** si una instancia de la API se cae o se reinicia, la otra sigue atendiendo; y se actualiza sin cortar el servicio.
**Qué NO logra** (decirlo con honestidad en la sustentación): no protege contra la caída de la máquina EC2 ni de su zona de
disponibilidad, ni contra la caída de PostgreSQL o de Nginx, porque todo sigue en una sola máquina. Eso exigiría una segunda
máquina en otra zona con un balanceador y una base administrada con réplica (RDS Multi-AZ): es el siguiente nivel, no está hecho.

**Por qué hace falta Redis:** el límite de intentos de login cuenta los fallos en memoria. Con 2 instancias cada una contaría
por su lado y quien adivina contraseñas tendría el doble de intentos (en la prueba: el bloqueo llegó en el intento 11 en lugar
del 6). Con Redis las 2 instancias comparten la misma cuenta (llegó en el 6).

**Costo de recursos:** cada instancia ocupa unos 80–100 MB de RAM; Redis, unos 7 MB. Cabe de sobra en la t3.small.

### Activarlo (en este orden; cada paso se puede revertir)

```bash
# 0. Respaldo y copias de seguridad de lo que vas a tocar
bash ~/picksy/backend/despliegue/respaldo.sh
sudo cp /etc/nginx/sites-available/picksy /etc/nginx/sites-available/picksy.bak

# 1. Redis (solo escucha en este mismo servidor; NO abras el puerto 6379 en el grupo de seguridad de AWS)
sudo apt update && sudo apt install -y redis-server
redis-cli ping                                          # debe responder PONG
sudo grep -E '^bind' /etc/redis/redis.conf              # debe decir  bind 127.0.0.1 -::1

# 2. Código nuevo y librería de Redis
cd ~/picksy/backend && source venv/bin/activate && pip install -r requirements.txt

# 3. Decirle a la API que use Redis
nano .env                                               # agrega la línea:   REDIS_URL=redis://127.0.0.1:6379/0
sudo systemctl restart picksy
# prueba: haz un inicio de sesión con la clave mal y mira que Redis guardó el intento (deben salir 2 llaves picksy:limite:...)
redis-cli --scan --pattern 'picksy:limite:*'

# 4. Segunda instancia (puerto 8001)
sudo cp despliegue/picksy-2.service /etc/systemd/system/picksy-2.service
sudo systemctl daemon-reload && sudo systemctl enable --now picksy-2
curl -s http://127.0.0.1:8001/api/v1/salud              # {"estado":"ok"}

# 5. Nginx: edita el archivo real siguiendo despliegue/nginx-2-instancias.conf.ejemplo (2 cambios)
sudo nano /etc/nginx/sites-available/picksy
sudo nginx -t && sudo systemctl reload nginx            # si nginx -t da error, NO recargues: restaura el .bak
```

### Comprobar que funciona

```bash
sudo systemctl stop picksy-2;  curl -s https://picksy.lat/api/v1/salud; sudo systemctl start picksy-2    # sigue respondiendo con una sola
sudo systemctl stop picksy;    curl -s https://picksy.lat/api/v1/salud; sudo systemctl start picksy      # también con la otra
```

### Volver atrás (si algo sale mal)

```bash
sudo cp /etc/nginx/sites-available/picksy.bak /etc/nginx/sites-available/picksy && sudo nginx -t && sudo systemctl reload nginx
sudo systemctl disable --now picksy-2
# Redis puede quedarse instalado sin hacer daño. Para volver al límite en memoria, quita la línea REDIS_URL del .env:
sudo systemctl restart picksy
```

### Si Redis se cae

La API **no se cae**: el límite de intentos pasa a la memoria de cada instancia (queda un aviso `LIMITADOR Redis no
disponible` en el log) y vuelve a probar Redis cada 30 segundos. Mientras dure, el límite deja de ser compartido.
Para levantarlo: `sudo systemctl restart redis-server`.

## 6. Medir el rendimiento (TPS)

```bash
cd ~/picksy/backend && source venv/bin/activate
python herramientas/prueba_carga.py --concurrencia 50 --segundos 20 --salida tps_1_instancia.json
```
Mide la propia API (`127.0.0.1:8000`, sin pasar por Nginx) con la ruta `/api/v1/salud`, e imprime TPS (peticiones exitosas por
segundo) y los tiempos de respuesta (mediana, p95, p99, máximo). **Cuidado:**

- La herramienta se **niega** a medir direcciones que no sean locales: probar `https://picksy.lat` sería atacar tu propio sitio
  (y Nginx limita a 50 peticiones/s por IP, así que no mediría la API).
- Úsala solo con rutas baratas como `/salud`. **Nunca con `/buscar`**: golpearía a las tiendas reales.
- Si la prueba y la API están en la misma máquina comparten procesador: el número vale para *esa* máquina en *ese* momento.
  Repite 2 o 3 veces y usa la mediana.
- El resultado depende de la máquina: **no copies cifras de otro computador**. Mide en el servidor y escribe tu propio número.

Para comparar 1 contra 2 instancias, mide cada puerto **a la vez** (dos terminales) y suma:
`--url http://127.0.0.1:8000/api/v1/salud` y `--url http://127.0.0.1:8001/api/v1/salud`. En una máquina de pruebas de 2 núcleos
(ejemplo, no tu servidor) 1 instancia dio ~390 TPS y 2 instancias ~500 en total: mejora, pero no el doble, porque la prueba y
las instancias se reparten los mismos procesadores.

## 7. Tiendas

**Ver cuáles responden desde el servidor** (una consulta por tienda, separadas 3 s; no usa la base ni el caché):

```bash
cd ~/picksy/backend && source venv/bin/activate && python herramientas/revisar_tiendas.py
```
Si una dice `HTTPStatusError http=403`, la tienda **bloquea la IP de AWS** (en las pruebas del equipo, Éxito respondió 403 desde AWS; otras tiendas pueden hacerlo en algún momento). No se
arregla con código: Picksy sigue mostrando los datos guardados anteriormente y avisa "no respondió". Las alternativas son
pedir acceso a la tienda o salir por otra IP (proxy), decisiones que dependen del equipo.

**Mercado Libre (OPCIONAL, tienda 10).** El ERS define 10 tiendas; hoy hay conector para 9. El conector de Mercado Libre ya
está escrito y probado con respuestas simuladas, pero **no se pudo probar contra la API real**. Para activarlo:

1. Entra a <https://developers.mercadolibre.com.co> con una cuenta de Mercado Libre y crea una aplicación (los pasos exactos del
   sitio pueden cambiar). Copia el *App ID* y la *Secret Key*.
2. Agrégalos al `.env` **del servidor** (nunca a GitHub): `ML_CLIENT_ID=...` y `ML_CLIENT_SECRET=...`
3. Pruébalos: `python herramientas/probar_mercadolibre.py` (explica en español qué falló si algo falla).
4. Solo si el paso 3 dijo "Todo bien": `sudo systemctl restart picksy`. Aparece como una tienda más; el frontend no cambia.

Si no se logra (por ejemplo, Mercado Libre responde 403 a la aplicación), deja las variables vacías y corrige el ERS: *"El sistema
integra 9 tiendas; Mercado Libre queda como trabajo futuro por restricciones de acceso a su API."*

## 8. Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El sitio no abre | `nginx` o `picksy` apagado | `systemctl status nginx picksy`; `sudo systemctl start ...`; mira el log (sección 1) |
| `/api/v1/salud` da 503 | PostgreSQL caído | `sudo systemctl status postgresql`; `sudo systemctl start postgresql`. La API se reconecta sola |
| Todo da error 500 tras actualizar | Librería o tabla nueva sin instalar | `pip install -r requirements.txt`, `python preparar_base.py`, reiniciar; si no, volver atrás (sección 2) |
| Las búsquedas tardan ~8 s y faltan tiendas | Tiendas lentas o que bloquean | `python herramientas/revisar_tiendas.py`; revisar `TIENDA_FALLO` en el log |
| Inicio de sesión responde 429 | Límite de intentos (5 fallos en 15 min) | Esperar el tiempo que indica `Retry-After`; es la protección funcionando |
| El navegador avisa que el certificado venció | Falló la renovación | `sudo certbot renew --dry-run`, luego `sudo certbot renew` y `sudo systemctl reload nginx` |
| El disco se llena | Respaldos o logs | `df -h /`; `ls -lh ~/picksy/respaldos`; `sudo journalctl --vacuum-time=7d` |
| Usuarios no pueden usar el Authenticator tras restaurar | Falta la `TOTP_CLAVE` original | Poner en el `.env` la `TOTP_CLAVE` guardada (sección 3.3) |
| `\r: command not found` al correr un `.sh` | Archivo con finales de línea de Windows | `sed -i 's/\r$//' archivo.sh` |

## 9. Seguridad operativa (revisar antes de la entrega)

- `.env` con permiso `600` y **fuera de GitHub** (ya está en `.gitignore`).
- Si el QR o los códigos de recuperación del administrador se mostraron en un chat o una pantalla compartida, **créalo de nuevo**
  (`python crear_admin.py`) y guarda los códigos nuevos en un lugar privado.
- Activa la verificación en dos pasos en las cuentas que mandan sobre el sistema: AWS, GitHub, Namecheap (dominio) y el correo.
- SSH (puerto 22) abierto **solo a tu IP** en el grupo de seguridad; 5432, 6379 y 8000/8001 nunca al público.
- Cambia contraseñas si alguna se pegó en un chat, un correo o una captura de pantalla.

## 10. Plan de retiro de Picksy (fin de vida)

Cuando el sistema deje de ofrecerse, se retira en este orden para no dejar datos personales ni cobros olvidados:

1. **Decidir y avisar.** Fija una fecha de cierre y avísala en el sitio y por correo a los usuarios registrados (por ejemplo, 15 días antes).
2. **Respaldo final** (sección 3) y guardado privado, solo el tiempo que se haya decidido conservarlo (política de retención).
3. **Atender el derecho a suprimir datos** (Ley 1581 de 2012): el administrador puede borrar usuarios con
   `DELETE /api/v1/admin/usuarios/{id}`; al cerrar el sistema se borra la base completa (paso 5).
4. **Apagar los servicios:** `sudo systemctl disable --now picksy picksy-2 nginx` (y `redis-server` si se usó).
5. **Borrar los datos:** `sudo -u postgres dropdb NOMBRE_DE_LA_BASE`, borrar `~/picksy/respaldos` del servidor y los respaldos copiados fuera (computadores, bucket de S3).
6. **Quitar la infraestructura de AWS** (para que no sigan los cobros): terminar la instancia EC2, borrar sus volúmenes y *snapshots*,
   **liberar la Elastic IP** (una IP elástica sin usar se cobra), borrar el grupo de seguridad y el *key pair*, y la instancia RDS si existiera.
7. **Revocar credenciales:** contraseña de aplicación del correo (SMTP), credenciales de Mercado Libre, tokens de GitHub si se crearon.
8. **Dominio:** dejarlo vencer o transferirlo, y borrar los registros DNS que apuntaban al servidor.
9. **Repositorio:** archivarlo en GitHub (Settings → Archive) con un aviso en el README de que el servicio terminó.
10. **Dejar constancia:** fecha, quién lo hizo y qué se borró (una nota en el repositorio o el acta del proyecto).
