#!/bin/sh
# Daily database backup. Run from the repo root (see deploy/README.md for the cron line).
set -eu
DIR="${BACKUP_DIR:-$HOME/leadflow-backups}"
mkdir -p "$DIR"
FILE="$DIR/leadflow-$(date +%F-%H%M).sql.gz"
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml \
  exec -T db pg_dump -U leadflow leadflow | gzip > "$FILE"
# Keep two weeks.
find "$DIR" -name 'leadflow-*.sql.gz' -mtime +14 -delete
echo "backup written: $FILE"
