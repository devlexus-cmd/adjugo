"""
Seed de démonstration Adjugo.
Réinitialise la base SQLite et crée un scénario cohérent :
  - 1 entreprise de GROS ŒUVRE / MAÇONNERIE (couvre le Lot 1 seule)
  - des critères de veille
  - un réseau de co-traitants (électricité, CVC, menuiserie + 2 distracteurs)

→ Met en valeur l'agent Stratège : l'entreprise ne peut pas répondre seule à un
   marché alloti tous corps d'état, l'agent compose le groupement.

Usage :  python seed_demo.py
"""
import os

# Réinitialiser la base SQLite pour repartir d'un schéma propre
DB_FILE = os.path.join(os.path.dirname(__file__), "adjugo.db")
if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
    print("• Ancienne base supprimée")

from app.core.database import Base, engine, SessionLocal
import app.models  # noqa: enregistre les modèles
import app.routers.cotraitants  # noqa: enregistre Cotraitant
import app.routers.criteria_v2  # noqa: enregistre MatchingCriteriaExt
from app.models import User, Company
from app.routers.cotraitants import Cotraitant
from app.routers.criteria_v2 import MatchingCriteriaExt
from app.core.security import hash_password, create_access_token

Base.metadata.create_all(bind=engine)
db = SessionLocal()

# ── Utilisateur démo ──
from app.models import PlanType
user = User(
    email="demo@adjugo.fr",
    hashed_password=hash_password("demo1234"),
    full_name="Démo Adjugo",
    is_active=True,
    plan=PlanType.business,   # illimité : pas de blocage quota pendant la démo
)
db.add(user); db.commit(); db.refresh(user)
print(f"• Utilisateur démo créé (id={user.id}) — demo@adjugo.fr / demo1234")

# ── Entreprise candidate : gros œuvre / maçonnerie ──
company = Company(
    user_id=user.id,
    name="BTP Armor Construction",
    siret="80391274500018",
    code_ape="4399C",
    forme_juridique="SARL",
    capital="50 000 EUR",
    representant_legal="Yann Le Gall",
    address="14 rue des Carriers",
    city="Quimper",
    postal_code="29000",
    tva_intracom="FR40803912745",
    phone="02 98 00 00 00",
    email="contact@btp-armor.fr",
    ca_n1=1250000, ca_n2=1180000, ca_n3=1090000,
    effectif=12,
    qualifications=[
        {"name": "Qualibat 2111", "detail": "Maçonnerie et béton armé courant", "expiration": "2027-06-01"},
        {"name": "Qualibat 1112", "detail": "Démolition", "expiration": "2027-06-01"},
    ],
    references=[
        {"name": "Réhabilitation mairie de Briec", "client": "Mairie de Briec", "value": 320000, "year": 2024},
        {"name": "Extension crèche", "client": "CCAS Quimper", "value": 210000, "year": 2023},
    ],
)
db.add(company); db.commit()
print("• Entreprise créée : BTP Armor Construction (gros œuvre, Quimper 29)")

# ── Critères de veille ──
crit = MatchingCriteriaExt(
    user_id=user.id,
    budget_min=50000, budget_max=900000,
    max_distance_km=80,
    departements="29, 56, 22",
    regions="Bretagne",
    types_marche="Travaux",
    procedures_acceptees="MAPA, AOO",
    codes_cpv="45223220, 45262500, 45000000",
    qualifications="Qualibat 2111",
    specialites="Gros œuvre, Maçonnerie, Réhabilitation, Démolition",
    penalty_max=10,
    excluded_keywords="désamiantage, voirie",
    go_threshold=60, nogo_threshold=40,
)
db.add(crit); db.commit()
print("• Critères de veille créés")

# ── Co-traitants : AUCUN seedé ──
# Les co-traitants proviennent désormais des registres officiels (SIRENE/annuaire)
# via le flux « Sourcing IA » et la découverte réelle. Plus de données fabriquées.
print("• Réseau co-traitants : vide (sourcing réel via SIRENE)")

db.close()
print("\n" + "=" * 60)
print("SEED TERMINÉ ✓")
print("=" * 60)
print("Compte démo :  demo@adjugo.fr  /  demo1234  (plan business, illimité)")
print("Profil entreprise + critères Go/No-Go prêts. Sourcing 100% sources réelles.")
print("→  http://localhost:8000/app")
print("=" * 60)
