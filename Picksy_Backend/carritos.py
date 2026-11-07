"""
Carritos y mochila 0/1 (RF-13, RF-14, RF-17).

  RF-13  El usuario arma una lista de productos y le da una prioridad de 1 a 5 a cada uno (5 = indispensable, A-03).
         Puede agregar, editar y quitar productos.
  RF-14  El sistema aplica el algoritmo de la mochila 0/1: elige los productos que MÁS prioridad suman
         sin que el total pase del presupuesto. Informa qué quedó dentro y qué fuera, y avisa si nada cabe.
  RF-17  El usuario puede comparar dos carritos y ver la diferencia de total.

Todos los endpoints exigen sesión y solo ven los carritos del propio usuario.

    POST   /carritos                           crea un carrito (nombre + presupuesto)
    GET    /carritos                           lista los carritos del usuario
    GET    /carritos/comparar?a=1&b=2          compara dos carritos (RF-17)
    GET    /carritos/{id}                      un carrito con sus productos
    PATCH  /carritos/{id}                      cambia nombre o presupuesto
    DELETE /carritos/{id}                      lo elimina
    POST   /carritos/{id}/items                agrega un producto con su prioridad
    PATCH  /carritos/{id}/items/{item_id}      cambia la prioridad
    DELETE /carritos/{id}/items/{item_id}      quita el producto
    POST   /carritos/{id}/optimizar            calcula la mochila (RF-14)
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from auth import usuario_actual
from database import engine

router = APIRouter(prefix="/carritos", tags=["Carritos y mochila"])

MAX_ITEMS = 50          # productos por carrito (la mochila calcula sobre ellos)
MAX_CARRITOS = 30       # carritos por usuario
PRESUPUESTO_MAXIMO = 1_000_000_000
CENTAVO = Decimal("0.01")


# ---------- Modelos ----------
class CarritoEntrada(BaseModel):
    nombre: Optional[str] = Field(default=None, max_length=100)
    presupuesto: float = Field(gt=0, le=PRESUPUESTO_MAXIMO, allow_inf_nan=False)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v):
        return " ".join(v.split()) or None if v else None


class CarritoEdicion(BaseModel):
    nombre: Optional[str] = Field(default=None, max_length=100)
    presupuesto: Optional[float] = Field(default=None, gt=0, le=PRESUPUESTO_MAXIMO, allow_inf_nan=False)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v):
        return " ".join(v.split()) or None if v else None


class ItemEntrada(BaseModel):
    tienda: str = Field(min_length=1, max_length=100)
    nombre: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=8, max_length=2000)
    imagen: Optional[str] = Field(default=None, max_length=2000)
    precio: float = Field(ge=0, le=PRESUPUESTO_MAXIMO, allow_inf_nan=False)
    envio: Optional[float] = Field(default=None, ge=0, le=PRESUPUESTO_MAXIMO, allow_inf_nan=False)
    prioridad: int = Field(ge=1, le=5, description="1 = poco importante ... 5 = indispensable")

    @field_validator("url", "imagen")
    @classmethod
    def _http(cls, v):
        if v is not None and not v.lower().startswith(("http://", "https://")):
            raise ValueError("Debe ser un enlace que empiece por http:// o https://")
        return v


class PrioridadEntrada(BaseModel):
    prioridad: int = Field(ge=1, le=5)


# ---------- Auxiliares ----------
def _dinero(x) -> Decimal:
    return Decimal(str(x)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _num(x) -> float:
    return float(x) if x is not None else 0.0


def _carrito_propio(conn, carrito_id: int, usuario_id: int, bloquear: bool = False):
    fila = conn.execute(
        text(f"""SELECT id, nombre, presupuesto, total, creado_en, optimizado_en
                 FROM carritos WHERE id = :id AND usuario_id = :u {'FOR UPDATE' if bloquear else ''}"""),
        {"id": carrito_id, "u": usuario_id},
    ).first()
    if fila is None:   # mismo error si no existe o es de otro usuario: no se revela cuál
        raise HTTPException(status_code=404, detail="Ese carrito no existe")
    return fila


def _items(conn, carrito_id: int):
    return conn.execute(
        text("""
            SELECT i.id, i.producto_id, i.prioridad, i.precio_total, i.incluido,
                   p.nombre, p.url, p.imagen_url, t.nombre AS tienda
            FROM carrito_items i
            JOIN productos p ON p.id = i.producto_id
            JOIN tiendas t ON t.id = p.tienda_id
            WHERE i.carrito_id = :c
            ORDER BY i.id
        """),
        {"c": carrito_id},
    ).all()


def _item_json(i) -> dict:
    return {
        "id": i.id, "tienda": i.tienda, "nombre": i.nombre, "url": i.url, "imagen": i.imagen_url,
        "prioridad": i.prioridad, "precio_total": _num(i.precio_total), "incluido": i.incluido,
    }


def _resumen(c, items) -> dict:
    """Números de un carrito. Si ya se optimizó, el total cuenta solo lo que quedó dentro."""
    optimizado = c.optimizado_en is not None
    contados = [i for i in items if i.incluido] if optimizado else list(items)
    return {
        "id": c.id, "nombre": c.nombre, "presupuesto": _num(c.presupuesto),
        "optimizado": optimizado,
        "productos": len(items),
        "total": float(sum((_dinero(i.precio_total) for i in contados), Decimal("0"))),
        "prioridad_total": sum(i.prioridad for i in contados),
        "creado_en": c.creado_en.isoformat(),
    }


def _invalidar(conn, carrito_id: int) -> None:
    """Si cambian los productos o el presupuesto, el resultado de la mochila ya no vale."""
    conn.execute(text("UPDATE carrito_items SET incluido = FALSE WHERE carrito_id = :c"), {"c": carrito_id})
    conn.execute(text("UPDATE carritos SET total = 0, optimizado_en = NULL WHERE id = :c"), {"c": carrito_id})


# ---------- Mochila 0/1 ----------
def mochila(items: list[tuple[int, int, int]], capacidad: int) -> set[int]:
    """
    items: lista de (id, valor, costo) con costo en centavos. capacidad: presupuesto en centavos.
    Devuelve los ids elegidos: los que suman MÁS valor (prioridad) sin pasar de la capacidad;
    si hay empate de valor, el de menor costo.

    Se resuelve por programación dinámica sobre el VALOR (como mucho 5 por producto), no sobre el dinero:
    así es exacto y rápido aunque el presupuesto sea de miles de millones.
        dp[i][v] = menor costo para sumar exactamente 'v' de valor usando los primeros i productos.
    """
    n = len(items)
    total_valor = sum(v for _, v, _ in items)
    inf = float("inf")
    dp = [[inf] * (total_valor + 1) for _ in range(n + 1)]
    dp[0][0] = 0
    for i, (_, valor, costo) in enumerate(items, start=1):
        for v in range(total_valor + 1):
            dp[i][v] = dp[i - 1][v]
            if v >= valor and dp[i - 1][v - valor] + costo < dp[i][v]:
                dp[i][v] = dp[i - 1][v - valor] + costo
    mejor = max(v for v in range(total_valor + 1) if dp[n][v] <= capacidad)
    elegidos, v = set(), mejor
    for i in range(n, 0, -1):
        if dp[i][v] != dp[i - 1][v]:          # el producto i hizo falta para llegar a este valor
            elegidos.add(items[i - 1][0])
            v -= items[i - 1][1]
    return elegidos


# ---------- Carritos ----------
@router.post("", status_code=201)
def crear(datos: CarritoEntrada, usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        cuantos = conn.execute(text("SELECT count(*) FROM carritos WHERE usuario_id = :u"), {"u": usuario["id"]}).scalar()
        if cuantos >= MAX_CARRITOS:
            raise HTTPException(status_code=409, detail=f"Llegaste al máximo de {MAX_CARRITOS} carritos. Elimina alguno.")
        nuevo = conn.execute(
            text("""INSERT INTO carritos (usuario_id, nombre, presupuesto) VALUES (:u, :n, :p)
                    RETURNING id, nombre, presupuesto, total, creado_en, optimizado_en"""),
            {"u": usuario["id"], "n": datos.nombre, "p": _dinero(datos.presupuesto)},
        ).first()
    return _resumen(nuevo, [])


@router.get("")
def listar(usuario=Depends(usuario_actual)):
    with engine.connect() as conn:
        carritos = conn.execute(
            text("SELECT id, nombre, presupuesto, total, creado_en, optimizado_en FROM carritos WHERE usuario_id = :u ORDER BY id DESC"),
            {"u": usuario["id"]},
        ).all()
        return [_resumen(c, _items(conn, c.id)) for c in carritos]


# OJO: esta ruta va ANTES de "/{carrito_id}"; si no, FastAPI intentaría leer "comparar" como un número.
@router.get("/comparar")
def comparar(a: int = Query(description="id del primer carrito"), b: int = Query(description="id del segundo carrito"),
             usuario=Depends(usuario_actual)):
    if a == b:
        raise HTTPException(status_code=400, detail="Elige dos carritos distintos para compararlos")
    with engine.connect() as conn:
        ca, cb = _carrito_propio(conn, a, usuario["id"]), _carrito_propio(conn, b, usuario["id"])
        ra, rb = _resumen(ca, _items(conn, a)), _resumen(cb, _items(conn, b))
    diferencia = round(abs(ra["total"] - rb["total"]), 2)
    if ra["total"] == rb["total"]:
        mas_barato, mensaje = "igual", "Los dos carritos cuestan lo mismo."
    else:
        mas_barato = "a" if ra["total"] < rb["total"] else "b"
        ganador = ra if mas_barato == "a" else rb
        mensaje = f"«{ganador['nombre'] or 'Carrito ' + str(ganador['id'])}» es más barato por ${diferencia:,.0f}.".replace(",", ".")
    return {"a": ra, "b": rb, "diferencia": diferencia, "mas_barato": mas_barato, "mensaje": mensaje}


@router.get("/{carrito_id}")
def ver(carrito_id: int, usuario=Depends(usuario_actual)):
    with engine.connect() as conn:
        c = _carrito_propio(conn, carrito_id, usuario["id"])
        items = _items(conn, c.id)
    return {**_resumen(c, items), "items": [_item_json(i) for i in items]}


@router.patch("/{carrito_id}")
def editar(carrito_id: int, datos: CarritoEdicion, usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        c = _carrito_propio(conn, carrito_id, usuario["id"], bloquear=True)
        nombre = datos.nombre if datos.nombre is not None else c.nombre
        presupuesto = _dinero(datos.presupuesto) if datos.presupuesto is not None else c.presupuesto
        conn.execute(text("UPDATE carritos SET nombre = :n, presupuesto = :p WHERE id = :id"),
                     {"n": nombre, "p": presupuesto, "id": c.id})
        if datos.presupuesto is not None and presupuesto != c.presupuesto:
            _invalidar(conn, c.id)
        c = _carrito_propio(conn, carrito_id, usuario["id"])
        items = _items(conn, c.id)
    return {**_resumen(c, items), "items": [_item_json(i) for i in items]}


@router.delete("/{carrito_id}", status_code=204)
def eliminar(carrito_id: int, usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        c = _carrito_propio(conn, carrito_id, usuario["id"])
        conn.execute(text("DELETE FROM carritos WHERE id = :id"), {"id": c.id})   # sus items se borran en cascada
    return Response(status_code=204)


# ---------- Productos del carrito (RF-13) ----------
@router.post("/{carrito_id}/items", status_code=201)
def agregar(carrito_id: int, datos: ItemEntrada, usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        c = _carrito_propio(conn, carrito_id, usuario["id"], bloquear=True)
        if conn.execute(text("SELECT count(*) FROM carrito_items WHERE carrito_id = :c"), {"c": c.id}).scalar() >= MAX_ITEMS:
            raise HTTPException(status_code=409, detail=f"Un carrito admite máximo {MAX_ITEMS} productos")
        tienda_id = conn.execute(text("SELECT id FROM tiendas WHERE lower(nombre) = lower(:n)"), {"n": datos.tienda}).scalar()
        if tienda_id is None:
            raise HTTPException(status_code=400, detail="Tienda no reconocida")
        # El producto se crea si no existe. Si ya existe NO se cambian sus datos (nadie pisa el catálogo de otros).
        producto_id = conn.execute(
            text("""INSERT INTO productos (tienda_id, nombre, url, imagen_url) VALUES (:t, :n, :u, :i)
                    ON CONFLICT (tienda_id, url) DO UPDATE SET url = EXCLUDED.url RETURNING id"""),
            {"t": tienda_id, "n": datos.nombre[:500], "u": datos.url, "i": datos.imagen},
        ).scalar()
        if conn.execute(text("SELECT 1 FROM carrito_items WHERE carrito_id = :c AND producto_id = :p"),
                        {"c": c.id, "p": producto_id}).first():
            raise HTTPException(status_code=409, detail="Ese producto ya está en el carrito. Edita su prioridad.")
        # El precio se toma de la última consulta guardada en la base (no se confía en lo que mande el navegador);
        # solo si el producto no tiene consultas se usa el que llegó en la petición.
        ultimo = conn.execute(
            text("SELECT precio, envio FROM precios WHERE producto_id = :p ORDER BY consultado_en DESC, id DESC LIMIT 1"),
            {"p": producto_id},
        ).first()
        if ultimo is not None:
            total = _dinero(ultimo.precio) + _dinero(ultimo.envio or 0)
        else:
            total = _dinero(datos.precio) + _dinero(datos.envio or 0)
        item_id = conn.execute(
            text("""INSERT INTO carrito_items (carrito_id, producto_id, prioridad, precio_total)
                    VALUES (:c, :p, :pr, :t) RETURNING id"""),
            {"c": c.id, "p": producto_id, "pr": datos.prioridad, "t": total},
        ).scalar()
        _invalidar(conn, c.id)
        item = next(i for i in _items(conn, c.id) if i.id == item_id)
    return _item_json(item)


def _item_propio(conn, carrito_id: int, item_id: int):
    item = next((i for i in _items(conn, carrito_id) if i.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Ese producto no está en el carrito")
    return item


@router.patch("/{carrito_id}/items/{item_id}")
def cambiar_prioridad(carrito_id: int, item_id: int, datos: PrioridadEntrada, usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        c = _carrito_propio(conn, carrito_id, usuario["id"], bloquear=True)
        _item_propio(conn, c.id, item_id)
        conn.execute(text("UPDATE carrito_items SET prioridad = :p WHERE id = :id"), {"p": datos.prioridad, "id": item_id})
        _invalidar(conn, c.id)
        return _item_json(_item_propio(conn, c.id, item_id))


@router.delete("/{carrito_id}/items/{item_id}", status_code=204)
def quitar(carrito_id: int, item_id: int, usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        c = _carrito_propio(conn, carrito_id, usuario["id"], bloquear=True)
        _item_propio(conn, c.id, item_id)
        conn.execute(text("DELETE FROM carrito_items WHERE id = :id"), {"id": item_id})
        _invalidar(conn, c.id)
    return Response(status_code=204)


# ---------- Mochila (RF-14) ----------
@router.post("/{carrito_id}/optimizar")
def optimizar(carrito_id: int, usuario=Depends(usuario_actual)):
    with engine.begin() as conn:
        c = _carrito_propio(conn, carrito_id, usuario["id"], bloquear=True)
        items = _items(conn, c.id)
        capacidad = int(_dinero(c.presupuesto) * 100)
        elegidos = mochila([(i.id, i.prioridad, int(_dinero(i.precio_total) * 100)) for i in items], capacidad) if items else set()

        total = sum((_dinero(i.precio_total) for i in items if i.id in elegidos), Decimal("0"))
        assert total <= _dinero(c.presupuesto)   # el total NUNCA supera el presupuesto
        conn.execute(text("UPDATE carrito_items SET incluido = (id = ANY(:ids)) WHERE carrito_id = :c"),
                     {"ids": list(elegidos), "c": c.id})
        conn.execute(text("UPDATE carritos SET total = :t, optimizado_en = NOW() WHERE id = :c"), {"t": total, "c": c.id})
        c = _carrito_propio(conn, c.id, usuario["id"])
        items = _items(conn, c.id)

    dentro = [_item_json(i) for i in items if i.incluido]
    fuera = [_item_json(i) for i in items if not i.incluido]
    if not items:
        mensaje = "El carrito está vacío. Agrega productos con su prioridad para calcular la mejor combinación."
    elif not dentro:
        mensaje = "Ningún producto cabe en el presupuesto."
    elif not fuera:
        mensaje = "Todos los productos caben en el presupuesto."
    else:
        mensaje = f"Quedaron dentro {len(dentro)} producto(s) y fuera {len(fuera)} para no pasar del presupuesto."
    return {
        "carrito": _resumen(c, items),
        "incluidos": dentro,
        "excluidos": fuera,
        "total": float(total),
        "presupuesto": _num(c.presupuesto),
        "sobrante": float(_dinero(c.presupuesto) - total),
        "prioridad_total": sum(i["prioridad"] for i in dentro),
        "mensaje": mensaje,
    }
