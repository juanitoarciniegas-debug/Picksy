"""
ESQUEMA vs CÓDIGO: que la base creada con schema.sql tenga TODAS las tablas y columnas que el código usa.

Por qué existe: en la v2, el código de auth.py lee usuarios.totp_activo y la tabla login_pendientes, pero
schema.sql no los crea. En una base nueva (el CI, un compañero, el despliegue) el login da error 500.
La base del desarrollador sí los tiene (se agregaron a mano), por eso a él le funciona.

Lee las cadenas SQL de los .py del backend y comprueba tablas y columnas contra information_schema.
Revisa: SELECT col FROM t, INSERT INTO t (cols), UPDATE t SET col=..., y columnas en WHERE (si hay una sola tabla).
"""
import ast
import re
from pathlib import Path

from ayudas import consulta_db

BACKEND = Path(__file__).resolve().parent.parent
EXCLUIR = ("preparar_base.py",)
IDENT = r"[a-z_][a-z0-9_]*"
NO_SON_TABLAS = {"lateral", "set", "select", "only", "values"}
RESERVADAS = {"and", "or", "not", "null", "true", "false", "in", "like", "ilike", "is", "between", "now", "interval"}


def _sqls():
    for f in sorted(BACKEND.glob("*.py")):
        if f.name.startswith("test_") or f.name in EXCLUIR:
            continue
        arbol = ast.parse(f.read_text(encoding="utf-8-sig"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
                s = " ".join(nodo.value.split())
                if re.match(r"(?is)^(SELECT|INSERT|UPDATE|DELETE)\b", s):
                    yield f.name, s


def _esquema_real():
    filas = consulta_db("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public'")
    esquema = {}
    for t, c in filas:
        esquema.setdefault(t, set()).add(c)
    return esquema


def _columnas_usadas(sql):
    """Devuelve (tablas, [(tabla, columna)]). Solo columnas 'simples'; lo demás se ignora a propósito."""
    s = sql.strip().rstrip(";")
    tablas = [t.lower() for t in re.findall(rf"(?i)\b(?:FROM|JOIN|INTO|UPDATE)\s+({IDENT})", s)
              if t.lower() not in NO_SON_TABLAS]
    usadas = []
    una_tabla = len(set(tablas)) == 1 and not re.search(r"(?i)\bJOIN\b", s)
    if not una_tabla:
        return tablas, usadas
    t = tablas[0]

    m = re.match(rf"(?is)^SELECT\s+(.*?)\s+FROM\s+{t}\b", s)
    if m:
        for col in re.split(r",", m.group(1)):
            col = re.sub(r"(?i)\s+as\s+\w+$", "", col.strip())
            if re.fullmatch(IDENT, col, re.I) and col.lower() not in RESERVADAS:
                usadas.append((t, col.lower()))

    m = re.match(rf"(?is)^INSERT\s+INTO\s+{t}\s*\(([^)]*)\)", s)
    if m:
        usadas += [(t, c.strip().lower()) for c in m.group(1).split(",") if re.fullmatch(IDENT, c.strip(), re.I)]

    m = re.match(rf"(?is)^UPDATE\s+{t}\s+SET\s+(.*?)(?:\s+WHERE\s+|$)", s)
    if m:
        usadas += [(t, c.lower()) for c in re.findall(rf"(?i)(?:^|,)\s*({IDENT})\s*=(?!=)", m.group(1))]

    m = re.search(r"(?is)\bWHERE\s+(.*)$", s)
    if m:
        for col in re.findall(rf"(?i)(?<![:\.\w])({IDENT})\s*(?:=|<>|<=|>=|<|>|\bLIKE\b|\bILIKE\b)", m.group(1)):
            if col.lower() not in RESERVADAS:
                usadas.append((t, col.lower()))
    return tablas, usadas


def test_el_esquema_de_la_base_tiene_todo_lo_que_usa_el_codigo():
    esquema = _esquema_real()
    faltan = set()
    for archivo, sql in _sqls():
        tablas, usadas = _columnas_usadas(sql)
        for t in tablas:
            if t not in esquema:
                faltan.add(f"{archivo}: falta la TABLA {t}")
        for t, c in usadas:
            if t in esquema and c not in esquema[t]:
                faltan.add(f"{archivo}: falta la COLUMNA {t}.{c}")
    assert not faltan, (
        "schema.sql no crea lo que el código necesita (una base nueva se rompería):\n  - "
        + "\n  - ".join(sorted(faltan))
        + "\nBackend debe agregarlo a schema.sql.")
