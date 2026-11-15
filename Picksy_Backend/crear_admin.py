"""
crear_admin.py - Crea el PRIMER administrador de Picksy (o convierte en administrador a un usuario que ya existe).

Uso (desde la carpeta del backend, con el entorno virtual activado):
    python crear_admin.py

Por qué existe: la página de registro solo crea usuarios normales. El primer administrador
se crea una sola vez desde aquí; después, un administrador puede promover a otros desde la API (PATCH /admin/usuarios/{id}/rol).

Si el correo NO existe: pide contraseña, muestra el QR de Google Authenticator en la terminal
y crea el administrador cuando escribas un código correcto.
Si el correo YA existe: solo le cambia el rol a 'admin'.
"""
import getpass
import sys

import qrcode
from sqlalchemy import text

import totp
from auth import encriptar
from database import engine

# En consolas de Windows el QR (bloques) puede dar error al imprimir; así se evita.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def main() -> None:
    correo = input("Correo del administrador: ").strip().lower()
    if "@" not in correo:
        sys.exit("Correo no válido.")

    with engine.begin() as conn:
        existente = conn.execute(text("SELECT id, rol FROM usuarios WHERE correo = :c"), {"c": correo}).first()
        if existente:
            conn.execute(text("UPDATE usuarios SET rol = 'admin' WHERE id = :id"), {"id": existente.id})
            print(f"[OK] {correo} ya existía: ahora es administrador.")
            return

    contrasena = getpass.getpass("Contraseña (mínimo 8 caracteres): ")
    if len(contrasena) < 8 or len(contrasena) > 50:
        sys.exit("La contraseña debe tener entre 8 y 50 caracteres.")
    if getpass.getpass("Repite la contraseña: ") != contrasena:
        sys.exit("Las contraseñas no coinciden.")

    secreto = totp.nuevo_secreto()
    uri = totp.uri_de(secreto, correo)
    qr = qrcode.QRCode(border=1)
    qr.add_data(uri)
    print("\nEscanea este QR con Google Authenticator (si no se ve bien, usa la clave de abajo):\n")
    qr.print_ascii(invert=True)
    print(f"\nClave manual: {secreto}\n")

    paso = None
    for _ in range(totp.MAX_INTENTOS):
        paso = totp.verificar_codigo(secreto, input("Código de 6 dígitos de la app: "), 0)
        if paso is not None:
            break
        print("Código incorrecto, intenta de nuevo.")
    if paso is None:
        sys.exit("No se creó el administrador (código incorrecto).")

    with engine.begin() as conn:
        nuevo_id = conn.execute(
            text("""
                INSERT INTO usuarios (correo, contrasena_hash, totp_secreto, totp_activo, totp_ultimo_paso, rol)
                VALUES (:c, :h, :s, TRUE, :p, 'admin') RETURNING id
            """),
            # CAMBIO: el secreto se guarda cifrado (totp.proteger usa TOTP_CLAVE del .env)
            {"c": correo, "h": encriptar(contrasena), "s": totp.proteger(secreto), "p": paso},
        ).scalar()
        codigos = totp.generar_codigos_recuperacion(conn, nuevo_id)
    print(f"[OK] Administrador {correo} creado. Ya puede iniciar sesión.")
    print("\nCÓDIGOS DE RECUPERACIÓN (guárdalos en un lugar seguro; cada uno sirve UNA vez si pierdes el celular):")
    for c in codigos:
        print(f"    {c}")


if __name__ == "__main__":
    main()
