"""
preparar_base.py - Prepara y verifica la base de datos PostgreSQL de Picksy.

Uso (desde la carpeta Picksy_Backend, con el entorno virtual activado):
    python preparar_base.py

Que hace, en orden:
  1. Lee las credenciales del archivo .env
  2. Se conecta al servidor PostgreSQL
  3. Crea la base de datos si todavia no existe
  4. Ejecuta schema.sql (se puede repetir sin problema: no borra datos)
  5. Verifica que esten todas las tablas, las columnas del 2FA/roles y las tiendas

Si algo falla, explica la causa mas probable y como arreglarla.
"""
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql

# En consolas de Windows antiguas los acentos pueden dar error al imprimir.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

AQUI = Path(__file__).resolve().parent
VARIABLES = ["DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME"]
TABLAS = [
    "usuarios", "tiendas", "productos", "precios", "historial_busquedas",
    "carritos", "carrito_items", "sesiones", "cache_busquedas", "cache_resultados",
    "login_pendientes", "registros_pendientes",   # CAMBIO (DEF-06): tablas del 2FA
    "codigos_recuperacion", "recuperaciones_clave",   # CAMBIO: códigos de recuperación y recuperar contraseña
]
# CAMBIO (DEF-06): columnas que usa el backend en "usuarios" (2FA y roles)
COLUMNAS_USUARIOS = ["totp_secreto", "totp_activo", "totp_ultimo_paso", "rol"]


def asegurar_clave_totp(ruta_env: Path) -> None:
    """CAMBIO (seguridad): crea TOTP_CLAVE en el .env si no existe (cifra el secreto de Google Authenticator en la base)."""
    if (os.getenv("TOTP_CLAVE") or "").strip():
        print("[OK] TOTP_CLAVE ya configurada (los secretos del 2FA se guardan cifrados)")
        return
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        terminar("Falta la libreria 'cryptography'", ["Ejecuta:  pip install -r requirements.txt"])
    clave = Fernet.generate_key().decode()
    texto = ruta_env.read_text(encoding="utf-8-sig")
    if texto and not texto.endswith("\n"):
        texto += "\n"
    ruta_env.write_text(texto + f"TOTP_CLAVE={clave}\n", encoding="utf-8")
    os.environ["TOTP_CLAVE"] = clave
    print("[OK] Se genero TOTP_CLAVE y se guardo en .env. NO la pierdas ni la subas a GitHub: sin ella no se pueden leer los codigos del 2FA.")


def terminar(titulo: str, ayuda: list[str] | None = None) -> None:
    print(f"\n[ERROR] {titulo}")
    for linea in ayuda or []:
        print(f"        - {linea}")
    sys.exit(1)


def explicar(error: Exception, config: dict) -> tuple[str, list[str]]:
    """Convierte un error de conexion en un mensaje claro y accionable."""
    # En Windows con PostgreSQL en espanol, el mensaje del servidor llega en cp1252 y psycopg2
    # falla al decodificarlo. Casi siempre significa que el servidor RECHAZO los datos.
    if isinstance(error, UnicodeDecodeError):
        return (
            "PostgreSQL rechazo la conexion (el mensaje llego en espanol y no se pudo leer).",
            [
                f"Casi siempre es la contrasena, el usuario ({config['user']}) o el nombre de la base incorrectos.",
                "Revisa DB_USER y DB_PASSWORD en el archivo .env (son los que pusiste al instalar PostgreSQL).",
            ],
        )
    texto = str(error).lower()
    if "password" in texto or "autentific" in texto or "authentication" in texto:
        return (
            f"La contrasena o el usuario son incorrectos (usuario: {config['user']}).",
            [
                "Revisa DB_USER y DB_PASSWORD en el archivo .env.",
                "Es la contrasena que elegiste al instalar PostgreSQL para el usuario 'postgres'.",
            ],
        )
    if any(p in texto for p in ("refused", "rechaz", "could not connect", "no se pudo conectar", "timeout", "timed out")):
        return (
            f"No se pudo llegar al servidor PostgreSQL en {config['host']}:{config['port']}.",
            [
                "Verifica que PostgreSQL este encendido: en Windows abre 'Servicios' y busca 'postgresql-x64-...' (debe decir 'En ejecucion').",
                "Verifica que DB_PORT sea el puerto que usa PostgreSQL (casi siempre 5432).",
                "Verifica que DB_HOST sea 'localhost' si la base esta en este mismo computador.",
            ],
        )
    return (f"Error de conexion: {error}", ["Revisa los datos del archivo .env."])


def conectar(config: dict, base: str):
    try:
        return psycopg2.connect(dbname=base, connect_timeout=5, **{k: v for k, v in config.items()})
    except (psycopg2.OperationalError, UnicodeDecodeError) as error:
        titulo, ayuda = explicar(error, config)
        terminar(titulo, ayuda)


def main() -> None:
    print("== Preparando la base de datos de Picksy ==\n")

    # 1) .env
    ruta_env = AQUI / ".env"
    if not ruta_env.exists():
        terminar(
            "No existe el archivo .env",
            [
                "Copia .env.example, renombralo a .env y llena DB_USER y DB_PASSWORD.",
                "Debe quedar en la misma carpeta que main.py.",
            ],
        )
    load_dotenv(ruta_env)
    faltan = [v for v in VARIABLES if not (os.getenv(v) or "").strip()]
    if faltan:
        terminar(f"Faltan datos en el archivo .env: {', '.join(faltan)}",
                 ["Ejemplo: DB_USER=postgres, DB_HOST=localhost, DB_PORT=5432, DB_NAME=smartbudget."])
    try:
        puerto = int(os.environ["DB_PORT"])
    except ValueError:
        terminar("DB_PORT debe ser un numero (por ejemplo 5432)")

    asegurar_clave_totp(ruta_env)

    nombre_base = os.environ["DB_NAME"].strip()
    config = {
        "user": os.environ["DB_USER"].strip(),
        "password": os.environ["DB_PASSWORD"],
        "host": os.environ["DB_HOST"].strip(),
        "port": puerto,
    }
    print(f"[OK] .env leido (usuario={config['user']}, servidor={config['host']}:{config['port']}, base={nombre_base})")

    # 2) servidor
    conexion = conectar(config, "postgres")  # base administrativa que siempre existe
    print("[OK] Conectado al servidor PostgreSQL")

    # 3) crear la base si no existe
    conexion.autocommit = True
    with conexion.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nombre_base,))
        existe = cur.fetchone() is not None
        if existe:
            print(f"[OK] La base '{nombre_base}' ya existe")
        else:
            try:
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nombre_base)))
                print(f"[OK] Base '{nombre_base}' creada")
            except psycopg2.errors.InsufficientPrivilege:
                terminar(f"El usuario '{config['user']}' no tiene permiso para crear bases de datos",
                         ["Usa el usuario 'postgres' o crea la base manualmente en pgAdmin."])
    conexion.close()

    # 4) esquema
    ruta_schema = AQUI / "schema.sql"
    if not ruta_schema.exists():
        terminar("No se encontro schema.sql", ["Debe estar en la misma carpeta que este script."])
    conexion = conectar(config, nombre_base)
    try:
        with conexion, conexion.cursor() as cur:
            cur.execute(ruta_schema.read_text(encoding="utf-8-sig"))
    except psycopg2.Error as error:
        terminar(f"schema.sql fallo: {str(error).strip()}")
    print("[OK] schema.sql ejecutado (puede repetirse sin problema)")

    # 5) verificacion
    with conexion.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        existentes = {fila[0] for fila in cur.fetchall()}
        cur.execute("SELECT count(*) FROM tiendas")
        n_tiendas = cur.fetchone()[0]
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'usuarios'")
        columnas = {fila[0] for fila in cur.fetchall()}
    # CAMBIO (seguridad): cifra los secretos de 2FA que estuvieran guardados en texto plano (de versiones anteriores).
    from cryptography.fernet import Fernet
    fernet = Fernet(os.environ["TOTP_CLAVE"].encode())
    with conexion, conexion.cursor() as cur:
        cur.execute("SELECT id, totp_secreto FROM usuarios WHERE totp_secreto IS NOT NULL AND totp_secreto NOT LIKE 'gAAAA%'")
        pendientes = cur.fetchall()
        for uid, secreto in pendientes:
            cur.execute("UPDATE usuarios SET totp_secreto = %s WHERE id = %s", (fernet.encrypt(secreto.encode()).decode(), uid))
    if pendientes:
        print(f"[OK] {len(pendientes)} secreto(s) de Google Authenticator que estaban sin cifrar ahora estan cifrados")
    conexion.close()

    faltantes = [t for t in TABLAS if t not in existentes]
    if faltantes:
        terminar(f"Faltan tablas: {', '.join(faltantes)}", ["Revisa que schema.sql este completo."])
    faltan_columnas = [c for c in COLUMNAS_USUARIOS if c not in columnas]
    if faltan_columnas:
        terminar(f"A la tabla usuarios le faltan columnas: {', '.join(faltan_columnas)}", ["Revisa que schema.sql este completo."])
    print(f"[OK] {len(TABLAS)} tablas listas, columnas de 2FA/roles correctas y {n_tiendas} tiendas cargadas")

    print("\nSi aun no tienes un administrador, crealo una vez con:")
    print("    python crear_admin.py")
    print("\nTodo listo. Ahora inicia el servidor con:")
    print("    uvicorn main:app --reload")
    print("y abre http://127.0.0.1:8000/docs para probar la API.")


if __name__ == "__main__":
    main()
