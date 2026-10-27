from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Producto:
    tienda: str
    nombre: str
    precio: float
    envio: Optional[float]   # None = la tienda no lo informa en esta consulta
    disponible: bool
    url: str
    imagen: Optional[str]
    consultado_en: datetime