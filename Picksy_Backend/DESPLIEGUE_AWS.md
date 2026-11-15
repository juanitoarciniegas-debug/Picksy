# Despliegue de Picksy en AWS (guía paso a paso)

Esta guía deja Picksy funcionando en **una sola máquina EC2** (Ubuntu) con PostgreSQL en la misma máquina.
Es lo más simple y suficiente para la sustentación. Si el profesor pide base de datos administrada, ver el apartado "Variante con RDS".

Arquitectura: `Navegador → Nginx (HTTPS) → /api/* → Uvicorn (FastAPI) → PostgreSQL`
y los archivos del frontend los sirve el mismo Nginx.

## 0. Antes de empezar
- Una cuenta de AWS y un dominio (o usar la IP pública de la instancia mientras tanto; sin dominio no hay HTTPS).
- El backend y el frontend en un repositorio de GitHub (**sin** el archivo `.env`; ya está en `.gitignore`).

## 1. Crear la máquina
1. EC2 → *Launch instance* → **Ubuntu 24.04**, tipo **t3.small** (2 GB de RAM; t3.micro funciona pero va justo).
2. Crea un *key pair* y descárgalo (lo necesitas para entrar por SSH).
3. *Security group*: permite **22** (SSH, solo tu IP), **80** y **443** (HTTP/HTTPS, todo el mundo).
   **No abras el 5432 ni el 8000** al público.
4. Asigna una **Elastic IP** y, si tienes dominio, apúntalo a esa IP (registro A).

## 2. Instalar lo necesario
```bash
ssh -i tu-llave.pem ubuntu@IP_DE_LA_MAQUINA
sudo apt update && sudo apt install -y python3-venv python3-pip postgresql nginx git certbot python3-certbot-nginx
```

## 3. Base de datos
```bash
sudo -u postgres psql -c "CREATE USER picksy WITH PASSWORD 'UNA_CLAVE_LARGA_Y_UNICA';"
sudo -u postgres psql -c "CREATE DATABASE picksy OWNER picksy;"
```

## 4. Subir el proyecto
```bash
mkdir -p ~/picksy && cd ~/picksy
git clone https://github.com/TU_USUARIO/TU_REPO.git .      # deja backend/ y frontend/ aquí
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## 5. Configurar el `.env` del servidor
Copia `.env.example` a `.env` (`cp .env.example .env && nano .env`) y llena:
```
DB_USER=picksy
DB_PASSWORD=UNA_CLAVE_LARGA_Y_UNICA
DB_HOST=localhost
DB_PORT=5432
DB_NAME=picksy
SESION_HORAS=2
CORS_ORIGENES=https://tudominio.com
FRONTEND_URL=https://tudominio.com
```
(Sin dominio todavía: usa `http://IP_PUBLICA` en ambas.)
Correo para "olvidé mi contraseña": completa `SMTP_*` (por ejemplo una cuenta de Gmail con *contraseña de aplicación* o Amazon SES).
Si lo dejas vacío, el enlace se imprime en el log del servidor (`journalctl -u picksy -f`): sirve para la demostración.

## 6. Crear las tablas y el primer administrador
```bash
python preparar_base.py     # crea tablas, tiendas y genera TOTP_CLAVE en el .env
python crear_admin.py       # escanea el QR y GUARDA los códigos de recuperación
```
**Haz copia de seguridad de `TOTP_CLAVE`** (está en `.env`): sin ella nadie podría entrar con Google Authenticator.

## 7. Dejar el backend siempre encendido
```bash
sudo cp despliegue/picksy.service /etc/systemd/system/picksy.service
sudo systemctl daemon-reload && sudo systemctl enable --now picksy
sudo systemctl status picksy          # debe decir "active (running)"
curl http://127.0.0.1:8000/api/v1/salud    # {"estado":"ok"}
```

## 8. Nginx + HTTPS
```bash
sudo cp despliegue/nginx-picksy.conf /etc/nginx/sites-available/picksy      # edita tudominio.com
sudo ln -s /etc/nginx/sites-available/picksy /etc/nginx/sites-enabled/ && sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d tudominio.com        # activa HTTPS y la renovación automática
```

## 9. Apuntar el frontend a la API
En `frontend/js/api.js` cambia **solo esta línea**:
```js
const API_URL = "https://tudominio.com/api/v1";
```
Súbelo (`git pull` en el servidor) y abre `https://tudominio.com`.

## 10. Comprobar
- `https://tudominio.com/api/v1/salud` → `{"estado":"ok"}`
- `https://tudominio.com/docs` → documentación interactiva de la API
- Registrar un usuario, entrar con el código, buscar, armar un carrito.

## Actualizar después de un cambio
```bash
cd ~/picksy && git pull && cd backend && source venv/bin/activate && pip install -r requirements.txt && python preparar_base.py
sudo systemctl restart picksy
```

## Variante con RDS (PostgreSQL administrado)
Crea una instancia RDS PostgreSQL (clase db.t3.micro) en la misma VPC, permite el puerto 5432 **solo** desde el security group de la EC2,
y en el `.env` pon `DB_HOST=<endpoint de RDS>`. El resto es igual (no hace falta instalar `postgresql` en la EC2).

## Notas de seguridad (para decir en la sustentación)
- Contraseñas con bcrypt; secreto de Google Authenticator **cifrado** en la base (Fernet, `TOTP_CLAVE`); códigos de recuperación guardados como hash.
- Sesiones cortas (2 h, configurable) y límite de intentos (HTTP 429) contra adivinar contraseñas y códigos.
- Todos los errores salen con el mismo formato JSON; la API está versionada (`/api/v1`).
- Una sola instancia de uvicorn (`--workers 1`): el limitador de intentos vive en memoria. Con varios servidores habría que moverlo a Redis o a la base.
