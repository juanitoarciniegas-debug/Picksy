import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

load_dotenv()  # lee el archivo .env

url = URL.create(
    drivername="postgresql+psycopg2",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    database=os.getenv("DB_NAME"),
)

# CAMBIO (alta disponibilidad): si PostgreSQL se reinicia (parche, mantenimiento o una caída), las conexiones que
# el servidor tenía abiertas quedan muertas y antes cada petición fallaba hasta reiniciar Picksy a mano.
#  - pool_pre_ping: antes de usar una conexión se comprueba que sigue viva; si no, se abre otra en el acto.
#    Así la API se recupera SOLA en cuanto la base vuelve (sin reiniciar picksy.service).
#  - pool_recycle: las conexiones con más de 30 minutos se renuevan.
#  - connect_timeout: si la base no contesta, la petición falla en 5 s con un 503 claro (ver errores.py)
#    en vez de quedarse colgada.
engine = create_engine(
    url,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={"connect_timeout": 5},
)
