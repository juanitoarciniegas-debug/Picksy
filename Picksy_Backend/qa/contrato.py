"""
contrato.py - Convierte /openapi.json en una versión "normalizada" y compara dos versiones.
Se normaliza para que solo importen los cambios que le afectan al frontend y a QA:
rutas, métodos, parámetros (nombre, tipo, obligatorio, límites), campos del cuerpo y códigos de respuesta.
"""

CLAVES_ESQUEMA = ("type", "format", "minLength", "maxLength", "minimum", "maximum",
                  "exclusiveMinimum", "exclusiveMaximum", "default")


def _esquema(esq, componentes):
    if not esq:
        return {}
    if "$ref" in esq:
        return _esquema(componentes.get(esq["$ref"].split("/")[-1], {}), componentes)
    out = {k: esq[k] for k in CLAVES_ESQUEMA if k in esq}
    if "anyOf" in esq:
        out["anyOf"] = sorted(str(_esquema(x, componentes).get("type", "?")) for x in esq["anyOf"])
    if "properties" in esq:
        out["campos"] = {n: _esquema(v, componentes) for n, v in sorted(esq["properties"].items())}
        out["obligatorios"] = sorted(esq.get("required", []))
    return out


def normalizar(spec):
    comp = spec.get("components", {}).get("schemas", {})
    resultado = {}
    for ruta, metodos in sorted(spec["paths"].items()):
        for metodo, op in sorted(metodos.items()):
            params = {f"{p['in']}:{p['name']}": {"obligatorio": bool(p.get("required")),
                                                 **_esquema(p.get("schema"), comp)}
                      for p in op.get("parameters", [])}
            cuerpo = None
            if "requestBody" in op:
                contenido = op["requestBody"].get("content", {})
                cuerpo = _esquema(next(iter(contenido.values()), {}).get("schema"), comp)
            resultado[f"{metodo.upper()} {ruta}"] = {
                "parametros": dict(sorted(params.items())),
                "cuerpo": cuerpo,
                "respuestas": sorted(op.get("responses", {}).keys()),
            }
    return resultado


def comparar(referencia, actual):
    """Lista de diferencias legibles. Vacía = el contrato no cambió."""
    dif = []
    for r in sorted(set(actual) - set(referencia)):
        dif.append(f"RUTA NUEVA: {r}")
    for r in sorted(set(referencia) - set(actual)):
        dif.append(f"RUTA ELIMINADA: {r}")
    for r in sorted(set(referencia) & set(actual)):
        a, b = referencia[r], actual[r]
        for p in sorted(set(b["parametros"]) - set(a["parametros"])):
            dif.append(f"PARÁMETRO NUEVO en {r}: {p}")
        for p in sorted(set(a["parametros"]) - set(b["parametros"])):
            dif.append(f"PARÁMETRO ELIMINADO en {r}: {p}")
        for p in sorted(set(a["parametros"]) & set(b["parametros"])):
            if a["parametros"][p] != b["parametros"][p]:
                dif.append(f"PARÁMETRO MODIFICADO en {r}: {p}: {a['parametros'][p]} -> {b['parametros'][p]}")
        if a["cuerpo"] != b["cuerpo"]:
            dif.append(f"CUERPO MODIFICADO en {r}: {a['cuerpo']} -> {b['cuerpo']}")
        if a["respuestas"] != b["respuestas"]:
            dif.append(f"CÓDIGOS DE RESPUESTA MODIFICADOS en {r}: {a['respuestas']} -> {b['respuestas']}")
    return dif
