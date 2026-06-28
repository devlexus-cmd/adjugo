"""
Compte de DÉMONSTRATION côté ACHETEUR (collectivités) — bac à sable public.

Crée une collectivité fictive pré-remplie de DCE complets, pour qu'un visiteur voie
immédiatement le produit fonctionner (sans attendre une génération IA). Cloisonné du
produit PME (table `acheteurs`). Idempotent : ne re-seede que si le compte n'a aucun DCE.
"""
import json
import os
import secrets

from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.models import Acheteur, AcheteurDce

DEMO_EMAIL = "demo@collectivites.adjugo.fr"
DEMO_NOM = "Mairie de Démoville (démonstration)"
_DATA = os.path.join(os.path.dirname(__file__), "acheteur_demo_dces.json")


def _apply_demo_meta(d, demo: dict) -> None:
    """Applique l'état de DÉMO (pilotage + diffusion) avec des dates calculées AU SEED, pour
    que la démo exerce vraiment ces fonctions sans jamais afficher d'échéances périmées."""
    if not demo:
        return
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    if demo.get("statut"):
        d.statut = demo["statut"]
    off = demo.get("date_limite_offset_days")
    if off is not None:
        d.date_limite = now + timedelta(days=int(off))
    if demo.get("diffuse"):
        d.date_diffusion = now
        d.nb_pme_diffusion = int(demo.get("nb_pme_diffusion") or 0)


def ensure_demo_acheteur(db):
    """Garantit l'existence du compte démo acheteur + ses DCE d'exemple. Renvoie l'Acheteur."""
    a = db.query(Acheteur).filter(Acheteur.email == DEMO_EMAIL).first()
    if not a:
        # Mot de passe aléatoire jamais communiqué : on n'entre QUE par /api/acheteur/demo.
        a = Acheteur(email=DEMO_EMAIL, hashed_password=hash_password(secrets.token_hex(16)),
                     nom_collectivite=DEMO_NOM)
        db.add(a)
        try:
            db.commit()
            db.refresh(a)
        except IntegrityError:
            # Création concurrente (deux /demo simultanés) → on récupère l'existant, pas de 500.
            db.rollback()
            a = db.query(Acheteur).filter(Acheteur.email == DEMO_EMAIL).first()
    if a is None:
        return None
    # Sérialise le seed des DCE entre workers concurrents : sans contrainte d'unicité sur
    # AcheteurDce, deux workers verraient tous deux count==0 et inséreraient les DCE en double.
    # Verrou sur la ligne Acheteur (no-op sous SQLite mono-worker, effectif sous Postgres).
    try:
        db.query(Acheteur).filter(Acheteur.id == a.id).with_for_update().first()
    except Exception:
        db.rollback()
    if db.query(AcheteurDce).filter(AcheteurDce.acheteur_id == a.id).count() == 0:
        try:
            with open(_DATA, encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            items = []
        for it in items:
            payload = it.get("payload") or {}
            if isinstance(payload, dict) and payload.get("objet"):
                d = AcheteurDce(acheteur_id=a.id, objet=(it.get("objet") or "")[:500], payload=payload)
                _apply_demo_meta(d, it.get("demo") or {})
                db.add(d)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()   # seed concurrent → on tolère, l'autre transaction l'a fait
    return a
