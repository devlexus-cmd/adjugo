"""
Compte de DÉMONSTRATION côté ACHETEUR (collectivités) — bac à sable public.

Crée une collectivité fictive pré-remplie de DCE complets, pour qu'un visiteur voie
immédiatement le produit fonctionner (sans attendre une génération IA). Cloisonné du
produit PME (table `acheteurs`). Idempotent : ne re-seede que si le compte n'a aucun DCE,
ou si les DCE d'exemple ont changé (acheteur_demo_dces.json) : ils sont alors remplacés.

Tout est fictif : la commune (Démoville) n'existe pas ; aucune collectivité réelle n'y est nommée.
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


def _items() -> list:
    """Les DCE d'exemple du fichier (ceux qui ont un objet), dans l'ordre du fichier."""
    try:
        with open(_DATA, encoding="utf-8") as f:
            items = json.load(f)
    except Exception:
        return []
    return [it for it in items if isinstance(it, dict) and isinstance(it.get("payload"), dict)
            and it["payload"].get("objet")]


def _empreinte(payload) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def ensure_demo_acheteur(db, force: bool = False):
    """Garantit l'existence du compte démo acheteur + ses DCE d'exemple. Renvoie l'Acheteur.
    force=True (remise à neuf entre deux présentations, app/services/demo_remise.py) : les DCE
    d'exemple sont recréés, dates de pilotage recalculées à aujourd'hui."""
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
    items = _items()
    q = db.query(AcheteurDce).filter(AcheteurDce.acheteur_id == a.id)
    presents = q.all()
    if items and presents and (force or sorted(_empreinte(d.payload) for d in presents)
                               != sorted(_empreinte(it["payload"]) for it in items)):
        # Les DCE d'exemple ont changé depuis le dernier seed (13/10/2026 : la commune réelle des
        # exemples remplacée par Démoville, fictive), ou remise à neuf entre deux présentations
        # (force) : ceux du compte démo sont remplacés. Le compte est
        # en lecture seule (403 sur toute écriture) : il n'a jamais d'autres DCE que ceux du seed.
        q.delete(synchronize_session=False)
        db.flush()
        presents = []
    if not presents:
        for it in items:
            d = AcheteurDce(acheteur_id=a.id, objet=(it.get("objet") or "")[:500], payload=it["payload"])
            _apply_demo_meta(d, it.get("demo") or {})
            db.add(d)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()   # seed concurrent → on tolère, l'autre transaction l'a fait
    return a
