import unicodedata
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from conectores.base import Producto
from database import engine

HORAS_CACHE = 24


def normalizar(termino: str) -> str:
    """'Audífonos  JBL' y 'audifonos jbl' cuentan como la misma búsqueda."""
    t = unicodedata.normalize("NFD", termino.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(t.split())


def leer_cache(termino: str, tienda: str, solo_vigente: bool = True):
    """Devuelve la lista de productos guardados, o None si no hay (o si venció)."""
    with engine.connect() as conn:
        fila = conn.execute(
            text("""
                SELECT c.id, c.consultado_en
                FROM cache_busquedas c
                JOIN tiendas t ON t.id = c.tienda_id
                WHERE c.termino = :termino AND t.nombre = :tienda
            """),
            {"termino": termino, "tienda": tienda},
        ).first()
        if fila is None:
            return None

        limite = datetime.now(timezone.utc) - timedelta(hours=HORAS_CACHE)
        if solo_vigente and fila.consultado_en < limite:
            return None

        filas = conn.execute(
            text("""
                SELECT t.nombre AS tienda, p.nombre, p.url, p.imagen_url,
                       pr.precio, pr.envio, pr.disponible, pr.consultado_en
                FROM cache_resultados cr
                JOIN productos p ON p.id = cr.producto_id
                JOIN tiendas t ON t.id = p.tienda_id
                JOIN LATERAL (
                    SELECT precio, envio, disponible, consultado_en
                    FROM precios WHERE producto_id = p.id
                    ORDER BY id DESC LIMIT 1
                ) pr ON TRUE
                WHERE cr.cache_id = :cid
            """),
            {"cid": fila.id},
        ).all()

    return [
        Producto(
            tienda=f.tienda,
            nombre=f.nombre,
            precio=float(f.precio),
            envio=None if f.envio is None else float(f.envio),
            disponible=f.disponible,
            url=f.url,
            imagen=f.imagen_url,
            consultado_en=f.consultado_en,
        )
        for f in filas
    ]


def guardar_cache(termino: str, tienda: str, productos: list) -> None:
    with engine.begin() as conn:
        tienda_id = conn.execute(
            text("SELECT id FROM tiendas WHERE nombre = :n"), {"n": tienda}
        ).scalar()
        if tienda_id is None:
            return

        cache_id = conn.execute(
            text("""
                INSERT INTO cache_busquedas (termino, tienda_id, consultado_en)
                VALUES (:t, :tid, NOW())
                ON CONFLICT (termino, tienda_id) DO UPDATE SET consultado_en = NOW()
                RETURNING id
            """),
            {"t": termino, "tid": tienda_id},
        ).scalar()
        conn.execute(text("DELETE FROM cache_resultados WHERE cache_id = :c"), {"c": cache_id})

        for p in productos:
            if not p.url:
                continue
            producto_id = conn.execute(
                text("""
                    INSERT INTO productos (tienda_id, nombre, url, imagen_url)
                    VALUES (:tid, :nombre, :url, :img)
                    ON CONFLICT (tienda_id, url)
                    DO UPDATE SET nombre = EXCLUDED.nombre, imagen_url = EXCLUDED.imagen_url
                    RETURNING id
                """),
                {"tid": tienda_id, "nombre": p.nombre[:500], "url": p.url, "img": p.imagen},
            ).scalar()
            # Cada consulta guarda una "foto" del precio: es el historial (RF-16)
            conn.execute(
                text("""
                    INSERT INTO precios (producto_id, precio, envio, disponible, consultado_en)
                    VALUES (:pid, :precio, :envio, :disp, :cuando)
                """),
                {"pid": producto_id, "precio": p.precio, "envio": p.envio,
                 "disp": p.disponible, "cuando": p.consultado_en},
            )
            conn.execute(
                text("""
                    INSERT INTO cache_resultados (cache_id, producto_id)
                    VALUES (:c, :pid) ON CONFLICT DO NOTHING
                """),
                {"c": cache_id, "pid": producto_id},
            )