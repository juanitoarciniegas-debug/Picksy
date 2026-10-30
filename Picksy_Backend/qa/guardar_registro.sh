#!/usr/bin/env bash
# guardar_registro.sh - Sube el registro de la ejecución a la rama qa-registros (NUNCA toca main).
# Variables: REMOTE_URL (obligatoria), RAMA (por defecto qa-registros), y las de GitHub Actions.
# Si dos ejecuciones terminan a la vez, el push de una falla: se vuelve a clonar y se repite (hasta 4 veces).
set -euo pipefail
RAMA="${RAMA:-qa-registros}"
BACKEND="$(pwd)"
PARAMS_REGISTRO=(--entrada "$BACKEND/qa_salida" --reportes "$BACKEND/reporte_*.html" --otros-fallaron "${OTROS_FALLARON:-false}")

for intento in 1 2 3 4; do
  TMP="$(mktemp -d)"
  if git ls-remote --exit-code --heads "$REMOTE_URL" "$RAMA" >/dev/null 2>&1; then
    git clone --quiet --depth 1 --branch "$RAMA" "$REMOTE_URL" "$TMP/r"
  else
    mkdir "$TMP/r"
    git -C "$TMP/r" init -q -b "$RAMA"
    git -C "$TMP/r" remote add origin "$REMOTE_URL"
  fi
  git -C "$TMP/r" config user.name "QA Bot Picksy"
  git -C "$TMP/r" config user.email "qa-bot@users.noreply.github.com"

  python3 "$BACKEND/qa/registrar.py" "${PARAMS_REGISTRO[@]}" --destino "$TMP/r/docs/qa"

  git -C "$TMP/r" add -A
  if git -C "$TMP/r" diff --cached --quiet; then echo "Nada nuevo que guardar."; exit 0; fi
  git -C "$TMP/r" commit -q -m "QA: registro de ejecución ${GITHUB_RUN_ID:-local} (${GITHUB_EVENT_NAME:-local})"
  if git -C "$TMP/r" push -q origin "$RAMA"; then echo "Registro guardado en la rama $RAMA."; exit 0; fi
  echo "Intento $intento: otra ejecución escribió primero; reintentando..."; sleep $((intento * 2))
done
echo "No se pudo guardar el registro tras 4 intentos." >&2
exit 1
