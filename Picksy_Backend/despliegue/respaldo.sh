#!/usr/bin/env bash
# Respaldo de la base de datos de Picksy (pg_dump) con rotación. Seguro de ejecutar cuando quieras: solo LEE la base.
#
#   A mano:        bash ~/picksy/backend/despliegue/respaldo.sh
#   Automático:    una línea en crontab (ver MANUAL_OPERACION.md, sección "Respaldos")
#
# Guarda un archivo  picksy_AAAAMMDD_HHMMSS.dump  en ~/picksy/respaldos  y borra los de más de 14 días.
# Después de crear el respaldo comprueba que el archivo sirva (lo lista con pg_restore).
#
# OJO: un respaldo que está en la MISMA máquina no te salva si la máquina se pierde. Copia los archivos fuera
# (a tu computador con scp, o a un bucket de S3: define RESPALDO_S3=s3://tu-bucket/picksy si tienes AWS CLI).
# Y guarda aparte TOTP_CLAVE del .env: sin ella los respaldos no sirven para recuperar el Google Authenticator.
set -euo pipefail
umask 077                                  # los respaldos quedan legibles solo por el usuario que los crea

RAIZ="${PICKSY_DIR:-/home/ubuntu/picksy/backend}"
DESTINO="${RESPALDO_DIR:-/home/ubuntu/picksy/respaldos}"
DIAS="${RESPALDO_DIAS:-14}"

# Lee SOLO las variables de la base desde el .env (no ejecuta el archivo, así una clave con símbolos no rompe nada).
leer() {
  grep -E "^$1=" "$RAIZ/.env" | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//" || true
}
[ -f "$RAIZ/.env" ] || { echo "No encuentro $RAIZ/.env"; exit 1; }
DB_USER="$(leer DB_USER)"; DB_PASSWORD="$(leer DB_PASSWORD)"; DB_HOST="$(leer DB_HOST)"
DB_PORT="$(leer DB_PORT)"; DB_NAME="$(leer DB_NAME)"
: "${DB_USER:?falta DB_USER en el .env}" "${DB_NAME:?falta DB_NAME en el .env}"

mkdir -p "$DESTINO"
ARCHIVO="$DESTINO/picksy_$(date +%Y%m%d_%H%M%S).dump"
trap 'rm -f "$ARCHIVO.parcial"' EXIT      # si algo falla, no queda un archivo a medias

# -Fc = formato comprimido de PostgreSQL (se restaura con pg_restore). Se escribe a un archivo temporal y solo
# al terminar bien se renombra: nunca queda un respaldo a medias que parezca bueno.
PGPASSWORD="$DB_PASSWORD" pg_dump -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" -U "$DB_USER" -Fc -f "$ARCHIVO.parcial" "$DB_NAME"
mv "$ARCHIVO.parcial" "$ARCHIVO"
pg_restore --list "$ARCHIVO" > /dev/null   # si el archivo estuviera dañado, aquí falla y el script termina con error

# Rotación: borra los respaldos viejos
find "$DESTINO" -maxdepth 1 -name 'picksy_*.dump' -mtime +"$DIAS" -delete

# Copia fuera de la máquina (opcional)
if [ -n "${RESPALDO_S3:-}" ]; then
  if command -v aws > /dev/null 2>&1; then
    aws s3 cp "$ARCHIVO" "${RESPALDO_S3%/}/" --only-show-errors && echo "Copiado a $RESPALDO_S3"
  else
    echo "AVISO: RESPALDO_S3 está definido pero no está instalado AWS CLI; el respaldo quedó solo en esta máquina."
  fi
fi

echo "OK respaldo: $ARCHIVO ($(du -h "$ARCHIVO" | cut -f1))"
