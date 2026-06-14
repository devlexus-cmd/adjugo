#!/bin/sh
set -e

# Appliquer les migrations (Postgres en prod) avant de démarrer.
# Retry léger le temps que la base soit prête.
echo "→ Migrations Alembic…"
for i in 1 2 3 4 5; do
  if alembic upgrade head; then
    break
  fi
  echo "  base non prête, nouvel essai dans 3s ($i/5)…"
  sleep 3
done

echo "→ Démarrage de l'API…"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-4}"
