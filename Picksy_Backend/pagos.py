"""
Membresía de Picksy: planes, métodos de pago y pagos.

CAMBIO (pagos): módulo nuevo. Picksy NO vende los productos que compara; lo único que se cobra es el uso de la página,
como una membresía. Por eso aquí se paga un PLAN DE MEMBRESÍA (mensual, semestral o anual), no un carrito.

IMPORTANTE - MODO DEMOSTRACIÓN: todavía no hay una pasarela de pagos real conectada (Wompi, PayU, Mercado Pago...).
El pago es SIMULADO: se registra, la membresía se activa y se envían los correos, pero NO se cobra dinero. Lo que quedará igual
cuando se conecte una pasarela: los planes, los estados del pago, la fecha de vencimiento y los correos. Por seguridad
NUNCA se guarda el número de la tarjeta ni el CVV, solo la marca y los últimos 4 dígitos.

Flujo en el frontend (pago.html):
    1. GET  /pagos/planes y /pagos/membresia   -> planes y estado de la membresía del usuario
    2. GET/POST /pagos/metodos                 -> el usuario elige o agrega un método de pago
    3. POST /pagos {plan, metodo_id}           -> crea el pago "pendiente" y envía el correo "Iniciaste un pago"
    4. POST /pagos/{id}/confirmar              -> lo marca "pagado", activa/extiende la membresía y envía el comprobante
       (o POST /pagos/{id}/cancelar)
Si el usuario ya tenía membresía activa, el nuevo plan se SUMA al tiempo que le queda (no pierde días).

Endpoints (todos exigen sesión y solo ven lo del propio usuario):
    GET    /pagos/planes                   planes de membresía y sus precios
    GET    /pagos/membresia                estado de la membresía (activa o no, y hasta cuándo)
    GET    /pagos/metodos                  lista de métodos de pago
    POST   /pagos/metodos                  agrega un método (sin número de tarjeta)
    DELETE /pagos/metodos/{id}             elimina un método
    POST   /pagos                          inicia un pago (plan, metodo_id)
    GET    /pagos                          historial de pagos
    GET    /pagos/{id}                     un pago
    POST   /pagos/{id}/confirmar           confirma (simulado)
    POST   /pagos/{id}/cancelar            cancela un pago pendiente
"""
import secrets
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text

import correos
import limitador
from auth import usuario_actual
from database import engine

router = APIRouter(prefix="/pagos", tags=["Membresía y pagos"])

MAX_METODOS = 5            # métodos de pago por usuario
MINUTOS_PAGO = 30          # tiempo para confirmar un pago pendiente
MAX_PAGOS_HORA = 15        # pagos iniciados por usuario cada hora (evita llenar el correo de mensajes)
CENTAVO = Decimal("0.01")

NOMBRES_TIPO = {"tarjeta_credito": "crédito", "tarjeta_debito": "débito", "pse": "PSE", "nequi": "Nequi"}

# Planes de membresía (precios en pesos colombianos). AQUÍ se cambian los precios y las duraciones.
PLANES = [
    {"codigo": "mensual",   "nombre": "Mensual",   "meses": 1,  "valor": Decimal("12900")},
    {"codigo": "semestral", "nombre": "Semestral", "meses": 6,  "valor": Decimal("59900")},
    {"codigo": "anual",     "nombre": "Anual",     "meses": 12, "valor": Decimal("99900")},
]
PLAN_POR_CODIGO = {p["codigo"]: p for p in PLANES}


# ---------- Modelos ----------
class MetodoEntrada(BaseModel):
    tipo: Literal["tarjeta_credito", "tarjeta_debito", "pse", "nequi"]
    alias: str = Field(min_length=1, max_length=50, description="Nombre para reconocerlo, por ejemplo 'Mi Visa'")
    marca: Optional[Literal["Visa", "Mastercard", "American Express", "Otra"]] = None
    # Solo 4 dígitos: así el servidor NO PUEDE recibir un número de tarjeta completo (si llegan más, responde 422).
    ultimos4: Optional[str] = Field(default=None, pattern=r"^\d{4}$", description="Últimos 4 dígitos de la tarjeta o del celular Nequi")
    banco: Optional[str] = Field(default=None, max_length=60)
    predeterminado: bool = False

    @field_validator("alias", "banco")
    @classmethod
    def _limpiar(cls, v):
        return " ".join(v.split()) or None if v else v

    @model_validator(mode="after")
    def _segun_tipo(self):
        if not self.alias:
            raise ValueError("Ponle un nombre al método de pago")
        if self.tipo in ("tarjeta_credito", "tarjeta_debito") and not (self.marca and self.ultimos4):
            raise ValueError("Para una tarjeta indica la marca y los últimos 4 dígitos")
        if self.tipo == "nequi" and not self.ultimos4:
            raise ValueError("Para Nequi indica los últimos 4 dígitos del celular")
        if self.tipo == "pse" and not self.banco:
            raise ValueError("Para PSE indica el banco")
        return self


class PagoEntrada(BaseModel):
    plan: Literal["mensual", "semestral", "anual"]
    metodo_id: int = Field(gt=0)


# ---------- Auxiliares ----------
def _dinero(x) -> Decimal:
    return Decimal(str(x)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _plan_json(plan: dict) -> dict:
    base = PLANES[0]   # el mensual es la referencia para calcular cuánto se ahorra
    sin_descuento = base["valor"] * plan["meses"]
    return {
        "codigo": plan["codigo"], "nombre": plan["nombre"], "meses": plan["meses"], "valor": float(plan["valor"]),
        "valor_por_mes": float(_dinero(plan["valor"] / plan["meses"])),
        "ahorro_porcentaje": int(round((1 - plan["valor"] / sin_descuento) * 100)),
    }


def _descripcion(m) -> str:
    """'Visa crédito ••••4242', 'PSE · Bancolombia', 'Nequi ••••1234'."""
    if m.tipo == "pse":
        return f"PSE · {m.banco}"
    if m.tipo == "nequi":
        return f"Nequi ••••{m.ultimos4}"
    return f"{m.marca} {NOMBRES_TIPO[m.tipo]} ••••{m.ultimos4}"


def _metodo_json(m) -> dict:
    return {
        "id": m.id, "tipo": m.tipo, "alias": m.alias, "marca": m.marca, "ultimos4": m.ultimos4,
        "banco": m.banco, "predeterminado": m.predeterminado, "descripcion": _descripcion(m),
    }


def _metodo_propio(conn, metodo_id: int, usuario_id: int):
    fila = conn.execute(
        text("""SELECT id, tipo, alias, marca, ultimos4, banco, predeterminado
                FROM metodos_pago WHERE id = :id AND usuario_id = :u"""),
        {"id": metodo_id, "u": usuario_id},
    ).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Ese método de pago no existe")
    return fila


COLUMNAS_PAGO = ("id, referencia, plan, meses, valor, metodo_descripcion, estado, creado_en, expira_en, pagado_en, "
                 "membresia_hasta")


def _pago_propio(conn, pago_id: int, usuario_id: int, bloquear: bool = False):
    fila = conn.execute(
        text(f"SELECT {COLUMNAS_PAGO} FROM pagos_membresia WHERE id = :id AND usuario_id = :u {'FOR UPDATE' if bloquear else ''}"),
        {"id": pago_id, "u": usuario_id},
    ).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Ese pago no existe")
    return fila


def _estado(p) -> str:
    """Un pago pendiente cuyo tiempo se acabó se muestra como 'vencido'."""
    if p.estado == "pendiente" and p.expira_en <= datetime.now(timezone.utc):
        return "vencido"
    return p.estado


def _pago_json(p) -> dict:
    plan = PLAN_POR_CODIGO.get(p.plan, {"nombre": p.plan})
    return {
        "id": p.id, "referencia": p.referencia, "estado": _estado(p),
        "plan": p.plan, "plan_nombre": plan["nombre"], "meses": p.meses, "valor": float(p.valor),
        "metodo": p.metodo_descripcion,
        "creado_en": p.creado_en.isoformat(), "expira_en": p.expira_en.isoformat(),
        "pagado_en": p.pagado_en.isoformat() if p.pagado_en else None,
        "membresia_hasta": p.membresia_hasta.isoformat() if p.membresia_hasta else None,
        "simulado": True,   # modo demostración: no se cobra dinero real (ver el comienzo de este archivo)
    }


def _pago_para_correo(p) -> dict:
    """Los mismos datos pero con las fechas como fecha (no texto), que es lo que usa correos.py."""
    datos = _pago_json(p)
    datos["expira_en"], datos["pagado_en"], datos["membresia_hasta"] = p.expira_en, p.pagado_en, p.membresia_hasta
    return datos


def _membresia_json(conn, usuario_id: int) -> dict:
    fila = conn.execute(
        text("SELECT plan, inicia_en, vence_en FROM membresias WHERE usuario_id = :u"), {"u": usuario_id},
    ).first()
    ahora = datetime.now(timezone.utc)
    if fila is None or fila.vence_en <= ahora:
        return {"activa": False, "plan": None, "plan_nombre": "Sin membresía", "vence_en": fila.vence_en.isoformat() if fila else None,
                "dias_restantes": 0}
    return {"activa": True, "plan": fila.plan, "plan_nombre": PLAN_POR_CODIGO.get(fila.plan, {"nombre": fila.plan})["nombre"],
            "vence_en": fila.vence_en.isoformat(), "dias_restantes": (fila.vence_en - ahora).days}


# ---------- Planes y estado de la membresía ----------
@router.get("/planes")
def planes(usuario=Depends(usuario_actual)):
    return [_plan_json(p) for p in PLANES]


@router.get("/membresia")
def membresia(usuario=Depends(usuario_actual)):
    with engine.connect() as conn:
        return _membresia_json(conn, usuario["id"])


# ---------- Métodos de pago ----------
@router.get("/metodos")
def listar_metodos(usuario=Depends(usuario_actual)):
    with engine.connect() as conn:
        filas = conn.execute(
            text("""SELECT id, tipo, alias, marca, ultimos4, banco, predeterminado
                    FROM metodos_pago WHERE usuario_id = :u ORDER BY predeterminado DESC, id"""),
            {"u": usuario["id"]},
        ).all()
    return [_metodo_json(m) for m in filas]


@router.post("/metodos", status_code=201)
def agregar_metodo(datos: MetodoEntrada, usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        # Se bloquea la fila del usuario para que dos solicitudes a la vez no pasen del máximo.
        conn.execute(text("SELECT id FROM usuarios WHERE id = :u FOR UPDATE"), {"u": usuario["id"]})
        cantidad = conn.execute(text("SELECT COUNT(*) FROM metodos_pago WHERE usuario_id = :u"), {"u": usuario["id"]}).scalar()
        if cantidad >= MAX_METODOS:
            raise HTTPException(status_code=409, detail=f"Puedes guardar máximo {MAX_METODOS} métodos de pago. Elimina uno.")
        predeterminado = datos.predeterminado or cantidad == 0   # el primero siempre queda como predeterminado
        if predeterminado:
            conn.execute(text("UPDATE metodos_pago SET predeterminado = FALSE WHERE usuario_id = :u"), {"u": usuario["id"]})
        nuevo = conn.execute(
            text("""INSERT INTO metodos_pago (usuario_id, tipo, alias, marca, ultimos4, banco, predeterminado)
                    VALUES (:u, :tipo, :alias, :marca, :u4, :banco, :pre)
                    RETURNING id, tipo, alias, marca, ultimos4, banco, predeterminado"""),
            {"u": usuario["id"], "tipo": datos.tipo, "alias": datos.alias, "marca": datos.marca,
             "u4": datos.ultimos4, "banco": datos.banco, "pre": predeterminado},
        ).first()
    return _metodo_json(nuevo)


@router.delete("/metodos/{metodo_id}", status_code=204)
def eliminar_metodo(metodo_id: int, usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        _metodo_propio(conn, metodo_id, usuario["id"])
        # Un pago pendiente que usaba este método ya no se puede confirmar: se cancela.
        conn.execute(text("UPDATE pagos_membresia SET estado = 'cancelado' WHERE metodo_id = :m AND estado = 'pendiente'"), {"m": metodo_id})
        conn.execute(text("DELETE FROM metodos_pago WHERE id = :m"), {"m": metodo_id})
        # Si era el predeterminado, el más antiguo que quede toma su lugar.
        conn.execute(
            text("""UPDATE metodos_pago SET predeterminado = TRUE
                    WHERE id = (SELECT id FROM metodos_pago WHERE usuario_id = :u ORDER BY id LIMIT 1)
                      AND NOT EXISTS (SELECT 1 FROM metodos_pago WHERE usuario_id = :u AND predeterminado)"""),
            {"u": usuario["id"]},
        )
    return Response(status_code=204)


# ---------- Pagos ----------
@router.post("", status_code=201)
def iniciar_pago(datos: PagoEntrada, tareas: BackgroundTasks, usuario=Depends(usuario_actual)):
    clave = f"pagos:{usuario['id']}"
    limitador.exigir_libre(clave, MAX_PAGOS_HORA, 3600)
    plan = PLAN_POR_CODIGO[datos.plan]

    with engine.begin() as conn:
        metodo = _metodo_propio(conn, datos.metodo_id, usuario["id"])
        # Si el usuario cambió de idea, el pago pendiente anterior se cancela: queda uno solo.
        conn.execute(text("UPDATE pagos_membresia SET estado = 'cancelado' WHERE usuario_id = :u AND estado = 'pendiente'"),
                     {"u": usuario["id"]})
        fila = conn.execute(
            text(f"""INSERT INTO pagos_membresia (referencia, usuario_id, plan, meses, valor, metodo_id, metodo_descripcion, expira_en)
                     VALUES (:ref, :u, :plan, :meses, :valor, :m, :md, :exp)
                     RETURNING {COLUMNAS_PAGO}"""),
            {"ref": "PK-" + secrets.token_hex(4).upper(), "u": usuario["id"], "plan": plan["codigo"],
             "meses": plan["meses"], "valor": plan["valor"], "m": metodo.id, "md": _descripcion(metodo),
             "exp": datetime.now(timezone.utc) + timedelta(minutes=MINUTOS_PAGO)},
        ).first()

    limitador.anotar(clave, 3600)
    # CAMBIO (correos): "cuando el usuario quiere hacer el pago, le llega el correo".
    tareas.add_task(correos.pago_iniciado, usuario["correo"], _pago_para_correo(fila))
    return {**_pago_json(fila), "mensaje": "Te enviamos un correo con el resumen. Confirma el pago para activar tu membresía."}


@router.get("")
def historial(usuario=Depends(usuario_actual)):
    with engine.connect() as conn:
        filas = conn.execute(
            text(f"SELECT {COLUMNAS_PAGO} FROM pagos_membresia WHERE usuario_id = :u ORDER BY creado_en DESC, id DESC LIMIT 50"),
            {"u": usuario["id"]},
        ).all()
    return [_pago_json(p) for p in filas]


@router.get("/{pago_id}")
def ver_pago(pago_id: int, usuario=Depends(usuario_actual)):
    with engine.connect() as conn:
        return _pago_json(_pago_propio(conn, pago_id, usuario["id"]))


@router.post("/{pago_id}/confirmar")
def confirmar(pago_id: int, tareas: BackgroundTasks, usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        p = _pago_propio(conn, pago_id, usuario["id"], bloquear=True)
        if p.estado == "pagado":
            raise HTTPException(status_code=409, detail="Este pago ya fue confirmado")
        if p.estado == "cancelado":
            raise HTTPException(status_code=409, detail="Este pago fue cancelado. Inicia uno nuevo.")
        if _estado(p) == "vencido":
            raise HTTPException(status_code=409, detail="El pago venció. Inicia uno nuevo.")
        if conn.execute(text("SELECT metodo_id FROM pagos_membresia WHERE id = :id"), {"id": p.id}).scalar() is None:
            raise HTTPException(status_code=409, detail="El método de pago ya no existe. Inicia un pago nuevo.")
        # MODO DEMOSTRACIÓN: aquí se llamaría a la pasarela de pagos. Por ahora el pago siempre se aprueba.

        # Se activa la membresía. Si todavía tenía días, el plan nuevo se SUMA a lo que le queda.
        vence = conn.execute(
            text("""INSERT INTO membresias (usuario_id, plan, inicia_en, vence_en)
                    VALUES (:u, :plan, NOW(), NOW() + make_interval(months => :m))
                    ON CONFLICT (usuario_id) DO UPDATE SET
                        plan = EXCLUDED.plan,
                        inicia_en = CASE WHEN membresias.vence_en > NOW() THEN membresias.inicia_en ELSE NOW() END,
                        vence_en = GREATEST(membresias.vence_en, NOW()) + make_interval(months => :m)
                    RETURNING vence_en"""),
            {"u": usuario["id"], "plan": p.plan, "m": p.meses},
        ).scalar()
        fila = conn.execute(
            text(f"""UPDATE pagos_membresia SET estado = 'pagado', pagado_en = NOW(), membresia_hasta = :v
                     WHERE id = :id RETURNING {COLUMNAS_PAGO}"""),
            {"id": p.id, "v": vence},
        ).first()
    tareas.add_task(correos.pago_confirmado, usuario["correo"], _pago_para_correo(fila))
    return {**_pago_json(fila), "mensaje": "Pago confirmado. Tu membresía está activa. Te enviamos el comprobante por correo."}


@router.post("/{pago_id}/cancelar")
def cancelar(pago_id: int, tareas: BackgroundTasks, usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        p = _pago_propio(conn, pago_id, usuario["id"], bloquear=True)
        if p.estado != "pendiente":
            raise HTTPException(status_code=409, detail="Solo se puede cancelar un pago pendiente")
        fila = conn.execute(
            text(f"UPDATE pagos_membresia SET estado = 'cancelado' WHERE id = :id RETURNING {COLUMNAS_PAGO}"), {"id": p.id},
        ).first()
    tareas.add_task(correos.pago_cancelado, usuario["correo"], _pago_para_correo(fila))
    return {**_pago_json(fila), "mensaje": "Pago cancelado. No se cobró nada."}
