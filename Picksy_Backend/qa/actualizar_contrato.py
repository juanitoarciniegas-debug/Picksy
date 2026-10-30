"""
actualizar_contrato.py - SOLO QA. Guarda como nueva referencia el contrato actual de la API.

Uso (desde Picksy_Backend):
    python qa/actualizar_contrato.py --motivo "agregan POST /mochila (RF-14)"

Muestra las diferencias, escribe qa/referencia/openapi.snapshot.json y deja una línea en
qa/referencia/CAMBIOS.md. Luego hay que hacer commit de ambos archivos: así queda escrito QUIÉN aprobó
el cambio, CUÁNDO y POR QUÉ.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI))

from contrato import comparar, normalizar  # noqa: E402
from main import app  # noqa: E402

SNAPSHOT = AQUI / "referencia" / "openapi.snapshot.json"
CAMBIOS = AQUI / "referencia" / "CAMBIOS.md"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--motivo", required=True, help="por qué se acepta este cambio (obligatorio)")
    motivo = parser.parse_args().motivo.strip()
    if len(motivo) < 5:
        sys.exit("El motivo debe explicar el cambio.")

    actual = normalizar(app.openapi())
    anterior = json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else {}
    diferencias = comparar(anterior, actual) if anterior else ["(primera referencia: línea base)"]
    print("Diferencias que se aprueban:")
    for d in diferencias:
        print("  -", d)

    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not CAMBIOS.exists():
        CAMBIOS.write_text("# Cambios aprobados del contrato de la API\n\n| Fecha | Motivo | Diferencias |\n|---|---|---|\n",
                           encoding="utf-8")
    with CAMBIOS.open("a", encoding="utf-8") as f:
        f.write(f"| {date.today().isoformat()} | {motivo} | {'; '.join(diferencias)[:300]} |\n")
    print("\nReferencia actualizada. Haz commit de qa/referencia/.")


if __name__ == "__main__":
    main()
