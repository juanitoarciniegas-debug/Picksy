"""
Avisa por correo si el certificado HTTPS de Picksy está por vencer. Es una red de seguridad por si falla la renovación
automática de certbot (que normalmente renueva cuando faltan 30 días).

Uso:   python herramientas/alerta_certificado.py                 # revisa el dominio de FRONTEND_URL; avisa si quedan 14 días o menos
       python herramientas/alerta_certificado.py --solo-ver      # solo muestra los días que quedan (no envía correo)
       python herramientas/alerta_certificado.py --dominio picksy.lat --dias 21
Se programa una vez al día con cron (ver MANUAL_OPERACION.md):
       0 9 * * *  cd /home/ubuntu/picksy/backend && venv/bin/python herramientas/alerta_certificado.py
Necesita en el .env:  ALERTA_CORREO=tu@correo.com   (y los SMTP_* para que el correo salga de verdad).
Código de salida: 0 = todo bien · 1 = quedan pocos días o no se pudo verificar el certificado · 2 = mal uso.
"""
import argparse
import os
import socket
import ssl
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # para poder importar los módulos del backend

import config  # noqa: E402  (carga el .env)


def dias_restantes(dominio: str, puerto: int = 443, cafile=None, tiempo_max: float = 10.0) -> float:
    """Días que le quedan al certificado que presenta ese dominio. Lanza ssl.SSLError si ya venció o no es válido."""
    contexto = ssl.create_default_context(cafile=cafile)
    with socket.create_connection((dominio, puerto), timeout=tiempo_max) as conexion:
        with contexto.wrap_socket(conexion, server_hostname=dominio) as segura:
            certificado = segura.getpeercert()
    return (ssl.cert_time_to_seconds(certificado["notAfter"]) - time.time()) / 86400


def dominio_por_defecto() -> str:
    return urlsplit(config.FRONTEND_URL).hostname or ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Avisa por correo si el certificado HTTPS está por vencer.")
    ap.add_argument("--dominio", default=None, help="dominio a revisar (por defecto el de FRONTEND_URL)")
    ap.add_argument("--puerto", type=int, default=443)
    ap.add_argument("--dias", type=int, default=14, help="avisar si quedan estos días o menos (por defecto 14)")
    ap.add_argument("--solo-ver", action="store_true", help="solo mostrar el resultado; no enviar correo")
    ap.add_argument("--cafile", help=argparse.SUPPRESS)   # solo para las pruebas automáticas
    a = ap.parse_args(argv)

    dominio = a.dominio or dominio_por_defecto()
    if not dominio or (not a.dominio and dominio in {"127.0.0.1", "localhost"}):   # FRONTEND_URL de desarrollo
        print("No sé qué dominio revisar: FRONTEND_URL del .env no es un dominio público. Usa --dominio picksy.lat")
        return 2

    problema = None
    try:
        dias = dias_restantes(dominio, a.puerto, a.cafile)
        print(f"El certificado de {dominio} vence en {dias:.1f} días.")
        if dias <= a.dias:
            problema = (f"El certificado HTTPS de {dominio} vence en {max(dias, 0):.0f} días (el aviso salta con {a.dias} o menos). "
                        "La renovación automática de certbot no está funcionando.")
    except ssl.SSLCertVerificationError as error:
        problema = f"El certificado HTTPS de {dominio} NO es válido o YA VENCIÓ ({error.verify_message})."
    except (OSError, ssl.SSLError) as error:
        problema = f"No se pudo comprobar el certificado de {dominio}: {type(error).__name__}: {error}"

    if problema is None:
        return 0

    print("ALERTA:", problema)
    texto = (f"{problema}\n\nQué hacer (en el servidor):\n"
             "  1) sudo certbot renew --dry-run      (prueba la renovación sin cambiar nada)\n"
             "  2) sudo certbot renew                (renueva de verdad)\n"
             "  3) sudo systemctl reload nginx\n"
             "  4) revisar:  systemctl list-timers | grep certbot   y   sudo journalctl -u certbot -n 50\n")
    destino = os.getenv("ALERTA_CORREO", "").strip()
    if a.solo_ver:
        pass
    elif not destino:
        print("No se envió correo: define ALERTA_CORREO en el .env.")
    else:
        import correos
        correos.enviar(destino, f"ALERTA Picksy: certificado HTTPS de {dominio}", texto)
        print(f"Aviso enviado a {destino}.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
