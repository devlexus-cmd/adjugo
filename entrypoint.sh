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

# Cohérence rate-limit / état partagé : les compteurs de rate-limit, le cache d'index
# RAG et le pool de jobs sont PAR PROCESSUS. Sans store partagé (Redis), plusieurs
# workers dédoublent ces états et multiplient la limite anti-abus par leur nombre.
# → Fail-SAFE : en l'absence de RATELIMIT_STORAGE_URI=redis(s)://, on force 1 worker
#   (rate-limit correct, caches cohérents) au lieu de planter ou de protéger pour de
#   faux. Pour scaler horizontalement, configurez Redis ; le multi-worker sera alors
#   automatiquement réactivé.
WORKERS="${WEB_CONCURRENCY:-4}"
case "${RATELIMIT_STORAGE_URI:-memory://}" in
  redis://*|rediss://*) : ;;                       # store partagé → multi-worker OK
  *)
    if [ "${WORKERS}" -gt 1 ] 2>/dev/null; then
      echo "⚠ Rate-limit en mémoire sans Redis : passage à 1 worker (état partagé cohérent)."
      echo "  Pour ${WORKERS} workers, définissez RATELIMIT_STORAGE_URI=redis://…"
      WORKERS=1
    fi
    ;;
esac
export WEB_CONCURRENCY="${WORKERS}"   # main.py lit cette valeur pour son garde-fou

echo "→ Démarrage de l'API ( ${WORKERS} worker(s) )…"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WORKERS}"
