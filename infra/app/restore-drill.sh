#!/usr/bin/env bash
# Restore drill. Plan T6.
# Restores the latest R2 replica into a fresh directory and runs a full integrity check.
# It also compares row counts per table with the live database.
# The live database is read, never written.
#
# Run as root on the `app` LXC: /opt/portfolio/infra/app/restore-drill.sh
# Set KEEP=1 to keep the restored copy for inspection.
set -euo pipefail
cd "$(dirname "$0")"

image=litestream/litestream:0.5.17
data_dir=/var/lib/portfolio/data
out=$(mktemp -d /tmp/restore-drill.XXXXXX)
chown 10001:10001 "$out"
if [[ "${KEEP:-0}" != 1 ]]; then trap 'rm -rf "$out"' EXIT; fi

if [[ ! -f .env.litestream ]]; then
  echo "error: $PWD/.env.litestream not found. Create it from the keys in /.env.example." >&2
  exit 1
fi

# Runs a binary from the Litestream image as the app UID.
in_image() {
  local bin=$1
  shift
  docker run --rm --user 10001:10001 --entrypoint "$bin" "$@"
}

echo "== Restore latest replica into $out"
in_image litestream \
  --env-file .env.litestream \
  -v "$PWD/litestream.yml:/etc/litestream.yml:ro" \
  -v "$out:/restore" \
  "$image" restore -config /etc/litestream.yml -integrity-check full \
  -o /restore/portfolio.db /data/portfolio.db

echo "== PRAGMA integrity_check on the restored copy"
result=$(in_image sqlite3 -v "$out:/restore" "$image" /restore/portfolio.db 'PRAGMA integrity_check;')
echo "$result"
if [[ "$result" != ok ]]; then
  echo "error: integrity check on $out/portfolio.db returned '$result', expected 'ok'" >&2
  exit 1
fi

# One query that counts rows in every user table of the restored copy.
tables=$(in_image sqlite3 -v "$out:/restore" "$image" /restore/portfolio.db \
  "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
query=$(printf "SELECT '%s', count(*) FROM \"%s\" UNION ALL " $(for t in $tables; do echo "$t $t"; done))
query="${query% UNION ALL };"

echo "== Row counts: restored vs live"
restored=$(in_image sqlite3 -v "$out:/restore" "$image" /restore/portfolio.db "$query")
live=$(in_image sqlite3 -v "$data_dir:/data" "$image" /data/portfolio.db "$query")
paste -d' ' <(echo "$restored" | tr '|' ' ') <(echo "$live" | cut -d'|' -f2) |
  awk 'BEGIN { printf "%-20s %10s %10s\n", "table", "restored", "live" }
       { printf "%-20s %10s %10s\n", $1, $2, $3 }'

if [[ "$restored" != "$live" ]]; then
  echo "warning: row counts differ. Writes in the last few seconds may not be replicated yet." >&2
  exit 2
fi
echo "== Drill passed $(date -u +%Y-%m-%dT%H:%M:%SZ)"
