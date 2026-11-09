"""
Correos de Picksy (todos salen de aquí).

CAMBIO (correos): antes solo existía el correo de "olvidé mi contraseña". Ahora hay uno solo punto de envío y
estos mensajes:
    - recuperación de contraseña (con las instrucciones paso a paso)
    - aviso de contraseña cambiada
    - aviso de inicio de sesión ("acabas de entrar a Picksy, ¿fuiste tú?")
    - pago de la membresía: iniciado, confirmado y cancelado

Cómo se envían:
    - Si en el .env está SMTP_HOST, se envían por SMTP (texto + versión HTML).
    - Si no, se IMPRIMEN en la terminal del backend (sirve para probar y para la demostración sin servidor de correo).
Un fallo del correo NUNCA rompe la respuesta al usuario: se registra en el log y se sigue.
Todo texto que viene del usuario o del navegador se escapa antes de ir al HTML.
"""
import html
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

import config

log = logging.getLogger("picksy")

HORA_COLOMBIA = timezone(timedelta(hours=-5))   # Colombia no tiene horario de verano


# ---------- Envío ----------
def enviar(destino: str, asunto: str, texto: str, html_cuerpo: str | None = None) -> None:
    """Envía un correo (o lo imprime si no hay SMTP configurado). Nunca lanza error."""
    if not config.SMTP_HOST:
        print(f"\n[correo] Para: {destino}\n[correo] Asunto: {asunto}\n{texto}\n")
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = asunto
        msg["From"] = config.SMTP_REMITENTE
        msg["To"] = destino
        # CAMBIO (anti-spam): cabeceras que los filtros esperan en un correo legítimo. Además, el correo ya lleva
        # versión de texto + HTML, asunto claro y ningún adjunto ni enlace acortado.
        msg["Date"] = formatdate(localtime=False, usegmt=True)
        msg["Message-ID"] = make_msgid(domain=(parseaddr(config.SMTP_REMITENTE)[1].split("@")[-1] or "picksy.local"))
        msg["Reply-To"] = config.SMTP_REMITENTE
        msg["Auto-Submitted"] = "auto-generated"          # es un aviso automático (no una cadena de respuestas)
        msg["X-Auto-Response-Suppress"] = "OOF, AutoReply"
        msg.set_content(texto)
        if html_cuerpo:
            msg.add_alternative(html_cuerpo, subtype="html")
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as servidor:
            servidor.starttls()
            if config.SMTP_USUARIO:
                servidor.login(config.SMTP_USUARIO, config.SMTP_CLAVE)
            servidor.send_message(msg)
    except Exception:  # noqa: BLE001 - un fallo del correo no debe romper la respuesta
        log.exception("No se pudo enviar el correo '%s'", asunto)


# ---------- Utilidades ----------
def pesos(valor) -> str:
    """12345.5 -> '$12.346' (formato colombiano, sin decimales)."""
    return "$" + f"{round(float(valor)):,}".replace(",", ".")


def hora_local(momento: datetime | None = None) -> str:
    momento = (momento or datetime.now(timezone.utc)).astimezone(HORA_COLOMBIA)
    return momento.strftime("%d/%m/%Y %I:%M %p") + " (hora de Colombia)"


def describir_navegador(user_agent: str | None) -> str:
    """'Chrome en Windows' a partir del User-Agent. Solo para informar al usuario; no se usa para seguridad."""
    ua = (user_agent or "").lower()
    if not ua:
        return "un navegador desconocido"
    navegador = ("Edge" if "edg/" in ua else "Opera" if "opr/" in ua or "opera" in ua
                 else "Chrome" if "chrome" in ua else "Firefox" if "firefox" in ua
                 else "Safari" if "safari" in ua else "un navegador")
    sistema = ("Windows" if "windows" in ua else "Android" if "android" in ua
               else "iPhone/iPad" if "iphone" in ua or "ipad" in ua else "macOS" if "mac os" in ua
               else "Linux" if "linux" in ua else "un sistema desconocido")
    return f"{navegador} en {sistema}"


def _e(valor) -> str:
    return html.escape(str(valor), quote=True)


def _pagina(titulo: str, parrafos: list[str], filas: list[tuple[str, str]] | None = None,
            boton: tuple[str, str] | None = None, pie: str = "") -> str:
    """Estructura HTML simple (estilos en línea, porque los clientes de correo ignoran las hojas de estilo)."""
    partes = [
        '<div style="background:#F5F4EC;padding:24px;font-family:Arial,Helvetica,sans-serif;color:#1E2B22">',
        '<div style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:16px;padding:28px;'
        'border:1px solid #E2E5D8">',
        '<div style="font-size:20px;font-weight:700;color:#2C4A34;margin-bottom:14px">picksy</div>',
        f'<h2 style="margin:0 0 12px;font-size:20px;color:#2C4A34">{_e(titulo)}</h2>',
    ]
    partes += [f'<p style="margin:0 0 12px;line-height:1.55;font-size:14px">{_e(p)}</p>' for p in parrafos]
    if filas:
        partes.append('<table style="width:100%;border-collapse:collapse;margin:8px 0 16px;font-size:14px">')
        partes += [
            f'<tr><td style="padding:6px 0;color:#6B7A6E">{_e(k)}</td>'
            f'<td style="padding:6px 0;text-align:right;font-weight:700">{_e(v)}</td></tr>'
            for k, v in filas
        ]
        partes.append("</table>")
    if boton:
        partes.append(
            f'<p style="margin:18px 0"><a href="{_e(boton[1])}" style="background:#2C4A34;color:#ffffff;'
            f'text-decoration:none;padding:12px 20px;border-radius:12px;font-weight:700;display:inline-block">'
            f'{_e(boton[0])}</a></p>'
        )
    if pie:
        partes.append(f'<p style="margin:16px 0 0;font-size:12px;color:#6B7A6E;line-height:1.5">{_e(pie)}</p>')
    partes.append("</div></div>")
    return "".join(partes)


# ---------- 1. Recuperar contraseña ----------
def recuperacion(destino: str, enlace: str, minutos: int) -> None:
    pasos = [
        "1. Abre el enlace de este correo.",
        "2. Escribe tu contraseña nueva (mínimo 8 caracteres).",
        "3. Escribe el código de 6 dígitos de Google Authenticator, o uno de tus códigos de recuperación.",
        "4. Inicia sesión con la contraseña nueva.",
    ]
    texto = (
        "Hola,\n\nRecibimos una solicitud para restablecer la contraseña de tu cuenta de Picksy.\n\n"
        "Sigue estos pasos:\n" + "\n".join(pasos) + f"\n\nEnlace (vale {minutos} minutos y sirve una sola vez):\n{enlace}\n\n"
        "Si no fuiste tú, ignora este mensaje: tu contraseña no cambia y nadie puede entrar sin tu código.\n"
    )
    cuerpo = _pagina(
        "Restablece tu contraseña",
        ["Recibimos una solicitud para restablecer la contraseña de tu cuenta de Picksy. Sigue estos pasos:"] + pasos,
        boton=("Restablecer mi contraseña", enlace),
        pie=f"El enlace vale {minutos} minutos y sirve una sola vez. Si no fuiste tú, ignora este mensaje: "
            "tu contraseña no cambia y nadie puede entrar sin tu código de Google Authenticator.",
    )
    enviar(destino, "Restablece tu contraseña de Picksy", texto, cuerpo)


def clave_cambiada(destino: str) -> None:
    enlace = f"{config.FRONTEND_URL}/recuperar.html"
    texto = (
        "Hola,\n\nLa contraseña de tu cuenta de Picksy se cambió el " + hora_local() + ".\n"
        "Por seguridad cerramos todas tus sesiones abiertas.\n\n"
        f"Si no fuiste tú, restablécela de inmediato aquí:\n{enlace}\n"
    )
    cuerpo = _pagina(
        "Tu contraseña se cambió",
        [f"La contraseña de tu cuenta se cambió el {hora_local()}. Por seguridad cerramos todas tus sesiones abiertas."],
        boton=("No fui yo: asegurar mi cuenta", enlace),
        pie="Si fuiste tú, no tienes que hacer nada.",
    )
    enviar(destino, "Tu contraseña de Picksy fue cambiada", texto, cuerpo)


# ---------- 2. Aviso de inicio de sesión ----------
def inicio_de_sesion(destino: str, ip: str, user_agent: str | None, con_codigo_recuperacion: bool = False) -> None:
    donde = describir_navegador(user_agent)
    enlace = f"{config.FRONTEND_URL}/recuperar.html"
    extra = ("Entraste con un código de recuperación (se gasta al usarlo). " if con_codigo_recuperacion else "")
    texto = (
        "Hola,\n\nAcabas de iniciar sesión en Picksy.\n\n"
        f"  Fecha: {hora_local()}\n  Dispositivo: {donde}\n  Dirección IP: {ip}\n\n{extra}"
        "¿Fuiste tú? Si es así, no tienes que hacer nada.\n"
        f"¿No fuiste tú? Cambia tu contraseña ya, así se cierran todas las sesiones:\n{enlace}\n"
    )
    cuerpo = _pagina(
        "¿Acabas de entrar a Picksy?",
        ["Detectamos un inicio de sesión en tu cuenta. " + extra + "¿Fuiste tú?"],
        filas=[("Fecha", hora_local()), ("Dispositivo", donde), ("Dirección IP", ip)],
        boton=("No fui yo: cambiar mi contraseña", enlace),
        pie="Si fuiste tú, no tienes que hacer nada. Si no, cambiar la contraseña cierra todas las sesiones abiertas.",
    )
    enviar(destino, "Nuevo inicio de sesión en tu cuenta de Picksy", texto, cuerpo)


# ---------- 3. Pagos de la membresía ----------
def _filas_pago(p: dict) -> list[tuple[str, str]]:
    return [
        ("Referencia", p["referencia"]),
        ("Membresía", f"Plan {p['plan_nombre']} ({p['meses']} {'mes' if p['meses'] == 1 else 'meses'})"),
        ("Método de pago", p["metodo"]),
        ("Total", pesos(p["valor"])),
    ]


def _lineas(filas) -> str:
    return "\n".join(f"  {k}: {v}" for k, v in filas)


def pago_iniciado(destino: str, p: dict) -> None:
    filas = _filas_pago(p)
    enlace = f"{config.FRONTEND_URL}/pago.html"
    texto = (
        "Hola,\n\nIniciaste el pago de tu membresía de Picksy. Todavía NO se ha cobrado: confirma en la página de "
        "pagos para activarla.\n\n"
        f"{_lineas(filas)}\n\nEste pago vence el {hora_local(p['expira_en'])}.\n"
        f"Confírmalo o cancélalo aquí: {enlace}\n"
        "Si no fuiste tú, cancélalo y cambia tu contraseña.\n"
        "Nota: Picksy está en modo de demostración; los pagos son simulados y no se cobra dinero real.\n"
    )
    cuerpo = _pagina(
        "Iniciaste el pago de tu membresía",
        ["Todavía no se ha cobrado nada: confirma en la página de pagos para activar tu membresía."],
        filas=filas,
        boton=("Ir a mis pagos", enlace),
        pie=f"Este pago vence el {hora_local(p['expira_en'])}. Si no fuiste tú, cancélalo y cambia tu contraseña. "
            "Picksy está en modo de demostración: los pagos son simulados y no se cobra dinero real.",
    )
    enviar(destino, f"Iniciaste un pago en Picksy ({p['referencia']})", texto, cuerpo)


def pago_confirmado(destino: str, p: dict) -> None:
    filas = _filas_pago(p) + [("Activa hasta", hora_local(p["membresia_hasta"]))]
    texto = (
        "Hola,\n\n¡Tu pago quedó confirmado y tu membresía de Picksy está activa!\n\n"
        f"{_lineas(filas)}\n\nFecha del pago: {hora_local(p['pagado_en'])}\n\n"
        "Nota: Picksy está en modo de demostración; el pago es simulado y no se cobró dinero real.\n"
    )
    cuerpo = _pagina(
        "¡Pago confirmado!",
        [f"Tu membresía de Picksy está activa. Fecha del pago: {hora_local(p['pagado_en'])}."],
        filas=filas,
        pie="Picksy está en modo de demostración: el pago es simulado y no se cobró dinero real.",
    )
    enviar(destino, f"Pago confirmado en Picksy ({p['referencia']})", texto, cuerpo)


def pago_cancelado(destino: str, p: dict) -> None:
    texto = f"Hola,\n\nCancelaste el pago {p['referencia']} por {pesos(p['valor'])}. No se cobró nada.\n"
    cuerpo = _pagina("Pago cancelado", [f"Cancelaste el pago {p['referencia']} por {pesos(p['valor'])}. No se cobró nada."])
    enviar(destino, f"Pago cancelado en Picksy ({p['referencia']})", texto, cuerpo)
