#!/usr/bin/env bash
# Reinicia las instancias de la API UNA POR UNA para actualizar sin cortar el servicio:
# mientras una se reinicia, Nginx manda el tráfico a la otra.
# Si una instancia no vuelve a responder, el script SE DETIENE y no toca la siguiente (la otra sigue atendiendo).
#
# Uso (en el servidor):   bash ~/picksy/backend/despliegue/reiniciar_sin_cortes.sh
# Solo tiene sentido con las 2 instancias activas (ver MANUAL_OPERACION.md). Con una sola, usa:  sudo systemctl restart picksy
set -euo pipefail

read -ra SERVICIOS <<< "${SERVICIOS:-picksy picksy-2}"
read -ra PUERTOS <<< "${PUERTOS:-8000 8001}"
ESPERA_MAX="${ESPERA_MAX:-40}"          # segundos máximos esperando que una instancia vuelva a responder

if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi

for i in "${!SERVICIOS[@]}"; do
  servicio="${SERVICIOS[$i]}"; puerto="${PUERTOS[$i]}"
  echo ">> Reiniciando $servicio (puerto $puerto)..."
  $SUDO systemctl restart "$servicio"

  ok=0
  for ((t = 1; t <= ESPERA_MAX; t++)); do
    if curl -fsS --max-time 3 "http://127.0.0.1:$puerto/api/v1/salud" > /dev/null 2>&1; then ok=1; break; fi
    sleep 1
  done
  if [ "$ok" -ne 1 ]; then
    echo "!! $servicio NO respondió en ${ESPERA_MAX} s. Me detengo SIN tocar las demás instancias (siguen atendiendo)."
    echo "   Revisa:  sudo journalctl -u $servicio -n 50 --no-pager"
    exit 1
  fi
  echo "   $servicio responde bien."
done
echo "Listo: todas las instancias reiniciadas sin cortar el servicio."
