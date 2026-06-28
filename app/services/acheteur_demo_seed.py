"""
Compte de DÉMONSTRATION côté ACHETEUR (collectivités) — bac à sable public.

Crée une collectivité fictive pré-remplie de DCE complets, pour qu'un visiteur voie
immédiatement le produit fonctionner (sans attendre une génération IA). Cloisonné du
produit PME (table `acheteurs`). Idempotent : ne re-seede que si le compte n'a aucun DCE.
"""
import json
import os
import secrets

from app.core.security import hash_password
from app.models import Acheteur, AcheteurDce

DEMO_EMAIL = "demo@collectivites.adjugo.fr"
DEMO_NOM = "Mairie de Démoville (démonstration)"
_DATA = os.path.join(os.path.dirname(__file__), "acheteur_demo_dces.json")


def ensure_demo_acheteur(db):
    """Garantit l'existence du compte démo acheteur + ses DCE d'exemple. Renvoie l'Acheteur."""
    a = db.query(Acheteur).filter(Acheteur.email == DEMO_EMAIL).first()
    if not a:
        # Mot de passe aléatoire jamais communiqué : on n'entre QUE par /api/acheteur/demo.
        a = Acheteur(email=DEMO_EMAIL, hashed_password=hash_password(secrets.token_hex(16)),
                     nom_collectivite=DEMO_NOM)
        db.add(a)
        db.commit()
        db.refresh(a)
    if db.query(AcheteurDce).filter(AcheteurDce.acheteur_id == a.id).count() == 0:
        try:
            with open(_DATA, encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            items = []
        for it in items:
            payload = it.get("payload") or {}
            if isinstance(payload, dict) and payload.get("objet"):
                db.add(AcheteurDce(acheteur_id=a.id, objet=(it.get("objet") or "")[:500], payload=payload))
        db.commit()
    return a
