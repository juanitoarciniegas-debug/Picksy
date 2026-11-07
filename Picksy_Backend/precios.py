"""
Variación de precios en el tiempo (RF-16).

    GET /productos/precios?url=<enlace del producto>

Cada vez que Picksy consulta una tienda guarda una "foto" del precio (tabla precios). Este endpoint devuelve esas
fotos de un producto y calcula cuánto cambió entre la primera y la última consulta.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from auth import usuario_actual
from database import engine

router = APIRouter(prefix="/productos", tags=["Precios en el tiempo"])

MAX_CONSULTAS = 200


@router.get("/precios")
def variacion(
    url: str = Query(min_length=8, max_length=2000, description="Enlace del producto en la tienda (el campo 'url' de /buscar)"),
    usuario=Depends(usuario_actual),
):
    with engine.connect() as conn:
        producto = conn.execute(
            text("""SELECT p.id, p.nombre, p.url, p.imagen_url, t.nombre AS tienda
                    FROM productos p JOIN tiendas t ON t.id = p.tienda_id WHERE p.url = :u LIMIT 1"""),
            {"u": url},
        ).first()
        if producto is None:
            raise HTTPException(status_code=404, detail="Ese producto todavía no tiene historial de precios")
        filas = conn.execute(
            text("""SELECT precio, envio, disponible, consultado_en FROM (
                        SELECT precio, envio, disponible, consultado_en FROM precios
                        WHERE producto_id = :p ORDER BY consultado_en DESC, id DESC LIMIT :l
                    ) x ORDER BY consultado_en ASC"""),
            {"p": producto.id, "l": MAX_CONSULTAS},
        ).all()

    consultas = [
        {"precio": float(f.precio), "envio": None if f.envio is None else float(f.envio),
         "disponible": f.disponible, "consultado_en": f.consultado_en.isoformat()}
        for f in filas
    ]
    if not consultas:
        raise HTTPException(status_code=404, detail="Ese producto todavía no tiene historial de precios")
    precios = [c["precio"] for c in consultas]
    resumen = {"consultas": len(consultas), "minimo": min(precios), "maximo": max(precios)}
    if len(consultas) < 2:
        resumen.update(cambio=None, cambio_porcentaje=None)
        mensaje = "Solo hay una consulta de este producto: todavía no hay variación para mostrar."
    else:
        cambio = round(precios[-1] - precios[0], 2)
        resumen.update(
            primera={"precio": precios[0], "fecha": consultas[0]["consultado_en"]},
            ultima={"precio": precios[-1], "fecha": consultas[-1]["consultado_en"]},
            cambio=cambio,
            cambio_porcentaje=round(cambio / precios[0] * 100, 2) if precios[0] else None,
        )
        mensaje = ("El precio no ha cambiado." if cambio == 0
                   else f"El precio {'subió' if cambio > 0 else 'bajó'} ${abs(cambio):,.0f} desde la primera consulta.".replace(",", "."))
    return {
        "producto": {"tienda": producto.tienda, "nombre": producto.nombre, "url": producto.url, "imagen": producto.imagen_url},
        "variacion": resumen,
        "consultas": consultas,
        "mensaje": mensaje,
    }
