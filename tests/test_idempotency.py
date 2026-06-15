"""
Idempotence des requêtes mutantes : un POST facturé rejoué avec le même
Idempotency-Key ne s'exécute qu'une fois (réponse mise en cache).
"""
import uuid


def test_sans_entete_comportement_inchange(client):
    """Sans Idempotency-Key : deux inscriptions identiques → la 2e échoue (email pris)."""
    email = f"idem_{uuid.uuid4().hex[:8]}@test.fr"
    body = {"email": email, "password": "motdepasse123", "full_name": "X", "company_name": "Y SARL"}
    r1 = client.post("/api/auth/register", json=body)
    assert r1.status_code == 201
    r2 = client.post("/api/auth/register", json=body)
    assert r2.status_code != 201          # rejeu réellement exécuté → conflit


def test_avec_entete_rejeu_renvoie_le_cache(client):
    """Avec le même Idempotency-Key : le rejeu renvoie la 1re réponse, SANS réexécuter
    (sinon l'email serait déjà pris et on aurait une erreur)."""
    email = f"idem_{uuid.uuid4().hex[:8]}@test.fr"
    body = {"email": email, "password": "motdepasse123", "full_name": "X", "company_name": "Y SARL"}
    key = str(uuid.uuid4())
    r1 = client.post("/api/auth/register", json=body, headers={"Idempotency-Key": key})
    assert r1.status_code == 201
    token1 = r1.json()["access_token"]
    r2 = client.post("/api/auth/register", json=body, headers={"Idempotency-Key": key})
    assert r2.status_code == 201                       # rejeu = même réponse cachée
    assert r2.json()["access_token"] == token1         # corps identique (pas ré-exécuté)
    assert r2.headers.get("Idempotent-Replayed") == "true"


def test_cles_differentes_executent_chacune(client):
    """Deux clés différentes sur le même corps → la 2e s'exécute (et échoue : email pris)."""
    email = f"idem_{uuid.uuid4().hex[:8]}@test.fr"
    body = {"email": email, "password": "motdepasse123", "full_name": "X", "company_name": "Y SARL"}
    r1 = client.post("/api/auth/register", json=body, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r1.status_code == 201
    r2 = client.post("/api/auth/register", json=body, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r2.status_code != 201                       # clé différente → réellement exécuté
