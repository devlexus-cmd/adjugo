#!/bin/sh
set -e

# Appliquer les migrations (Postgres en prod) avant de démarrer.
# Retry léger le temps que la base soit prête.
echo "→ Migrations Alembic…"
MIGRATED=0
for i in 1 2 3 4 5; do
  if alembic upgrade head; then
    MIGRATED=1
    break
  fi
  echo "  base non prête, nouvel essai dans 3s ($i/5)…"
  sleep 3
done
if [ "$MIGRATED" != 1 ]; then
  # Échec après 5 tentatives → on NE démarre PAS sur un schéma périmé (sinon 500 silencieux
  # + hooks de démarrage cassés, déploiement « réussi » mais API HS). On échoue franchement :
  # Railway conserve alors la version précédente qui marche.
  echo "✗ Migrations Alembic échouées après 5 tentatives — arrêt." >&2
  exit 1
fi

# Cohérence rate-limit / état partagé : les compteurs de rate-limit, le cache d'index
# RAG et le pool de jobs sont PAR PROCESSUS. Sans store partagé (Redis), plusieurs
# workers dédoublent ces états et multiplient la limite anti-abus par leur nombre.
# → Fail-SAFE : en l'absence de RATELIMIT_STORAGE_URI=redis(s)://, on force 1 worker
#   (rate-limit correct, caches cohérents) au lieu de planter ou de protéger pour de
#   faux. Pour scaler horizontalement, configurez Redis ; le multi-worker sera alors
#   automatiquement réactivé.
WORKERS="${WEB_CONCURRENCY:-4}"
# WEB_CONCURRENCY non numérique (faute de frappe d'env) → on retombe sur 4 au lieu de faire
# échouer uvicorn --workers avec une valeur invalide et un message obscur.
case "$WORKERS" in (''|*[!0-9]*) WORKERS=4 ;; esac
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
