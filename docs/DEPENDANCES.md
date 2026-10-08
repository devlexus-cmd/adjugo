# Dépendances Python : lock, mise à jour, audit

Audit cyber d'octobre 2026, rang 16 : dépendances montées, lockfile avec hachages,
pip-audit en CI.

## Les deux fichiers

| Fichier | Rôle | Qui l'écrit |
|---|---|---|
| `requirements.txt` | Dépendances **directes**, épinglées (`==`), commentées. Source lisible. | À la main |
| `requirements.lock` | Fermeture **complète** (directes + indirectes), version exacte et hachage SHA-256 de chaque paquet. Cible : linux x86_64, Python 3.12, comme l'image Docker. | Généré, jamais édité à la main |

L'image de production (`Dockerfile`) et la CI installent le lock :

```bash
pip install --no-cache-dir --require-hashes -r requirements.lock
```

Si un paquet téléchargé ne correspond pas à son hachage, ou si une dépendance manque
dans le lock, l'installation échoue. Le build s'arrête alors et la version en ligne
reste en place.

Le lock contient les hachages de toutes les roues publiées pour chaque version, macOS
compris. On peut donc créer le venv local depuis le lock, et les tests valident alors la
même pile que la production :

```bash
uv venv --seed --python 3.12 .venv      # --seed : installe pip dans le venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
```

## Contraintes à respecter en montant une version

- `anthropic==0.34.0` reste figé : c'est un invariant du projet, son API est utilisée telle quelle.
- `httpx` reste en 0.27.x : anthropic 0.34 passe `proxies=` à httpx, et httpx 0.28 a supprimé ce paramètre.
- pydantic reste en v2 et SQLAlchemy en 2.0.
- Les middlewares maison sont du pur ASGI et dépendent du comportement de starlette et de python-multipart : `BodySizeLimitMiddleware` dans `app/main.py` et `IdempotencyMiddleware` dans `app/core/idempotency.py`. Toute montée de fastapi, starlette ou python-multipart doit être suivie de la suite complète, qui couvre les 413, le chunked et l'idempotence.
- sentry-sdk doit être compatible avec la version de starlette. Sinon, `init_sentry()` attrape l'erreur et Sentry se coupe **en silence** au démarrage.

## Mettre à jour une dépendance

1. Modifier la version dans `requirements.txt`, avec un commentaire qui dit pourquoi.
2. Régénérer le lock. uv garde les versions déjà verrouillées, sauf si on lui demande d'en monter :

   ```bash
   uv pip compile requirements.txt --python-version 3.12 \
     --python-platform x86_64-unknown-linux-gnu --generate-hashes -o requirements.lock
   # rafraîchir une dépendance indirecte précise :   ... --upgrade-package urllib3
   # tout rafraîchir (à éviter hors d'une revue dédiée) : ... --upgrade
   ```

3. Auditer, avec la même commande que la CI :

   ```bash
   pip install pip-audit
   pip-audit -r requirements.lock --require-hashes --disable-pip --strict \
     --ignore-vuln GHSA-3qf3-8w2g-rqmx --ignore-vuln GHSA-wj6h-64fc-37mp
   ```

4. Recréer un venv neuf depuis le lock (voir plus haut), puis lancer toute la suite :
   `ADJUGO_TEST_DB=test_deps.db .venv/bin/python -m pytest -q`.
5. Commiter `requirements.txt` et `requirements.lock` **ensemble**.

La CI (`.github/workflows/ci.yml`, job `dependances`) rejoue l'audit à chaque push et
à chaque PR. Elle le relance aussi chaque lundi : une faille peut être publiée sans que
le code ait bougé. Un job rouge signale une nouvelle faille. Il faut alors monter le
paquet concerné jusqu'à la première version qui la corrige, puis suivre les étapes ci-dessus.

## Résiduels acceptés (aucun correctif publié)

| Faille | Paquet | Pourquoi elle ne s'applique pas ici |
|---|---|---|
| CVE-2026-85394 (GHSA-3qf3-8w2g-rqmx), critique | python-jose ≤ 3.5.0, dernière version | Elle permet de forger un jeton HS256 en se servant de la **clé publique** du service comme secret HMAC, quand les algorithmes ne sont pas imposés. Adjugo signe en HS256 avec un secret **symétrique** (`SECRET_KEY`) et impose `algorithms=[settings.ALGORITHM]` au décodage (`app/core/security.py`). Aucune clé publique n'est en jeu. Tout nouvel usage de `jose.jwt.decode` doit lui aussi imposer `algorithms=[...]`. |
| CVE-2024-23342 (GHSA-wj6h-64fc-37mp), haute | ecdsa (dépendance de python-jose) | Attaque temporelle sur la **signature** ECDSA P-256. Le projet ecdsa ne prévoit pas de correctif. Adjugo ne signe rien en ECDSA, et python-jose utilise `cryptography` pour les courbes elliptiques : le module `ecdsa` n'est même jamais importé (vérifié). |

Pour supprimer ces deux résiduels, on peut remplacer python-jose par PyJWT. Cela
retire python-jose, ecdsa, rsa et pyasn1, et ne touche que `app/core/security.py`.
C'est une décision à prendre à part : ce lot n'ajoute aucune dépendance.

## Montée d'octobre 2026 (avant → après)

Inventaire fait avec pip-audit sur la fermeture complète, pour Python 3.12 sur linux x86_64.
Avant : 64 failles connues dans 7 paquets. Après : 2 résiduels, listés plus haut.

| Paquet | Avant | Après | Failles fermées |
|---|---|---|---|
| starlette (via fastapi) | 0.38.6 | 1.3.1 | 7 : CVE-2024-47874, CVE-2025-54121, CVE-2026-48710, CVE-2026-48817, CVE-2026-48818, CVE-2026-54282, CVE-2026-54283 |
| fastapi | 0.115.0 | 0.133.0 | aucune en propre : c'est la première version qui accepte starlette 1.x |
| python-multipart | 0.0.9 | 0.0.31 | 7 : CVE-2024-53981, CVE-2026-24486, CVE-2026-40347, CVE-2026-42561, CVE-2026-53538, CVE-2026-53539, CVE-2026-53540 |
| python-jose | 3.3.0 | 3.5.0 | 3 : CVE-2024-33663, CVE-2024-33664, CVE-2024-29370. La 3.4.0 imposait pyasn1 < 0.5, qui a 4 failles hautes. |
| pillow | 10.4.0 | 12.3.0 | 17, dont 13 hautes : écritures hors limites, bombes de décompression |
| pypdf | 6.11.0 | 6.19.0 | 27, dont 10 hautes : mémoire, boucles infinies sur PDF piégé |
| python-dotenv | 1.0.1 | 1.2.2 | 1 : CVE-2026-28684 |
| sentry-sdk | 2.18.0 | 2.56.0 | aucune en propre : c'est la première version compatible starlette 1.x. Avec 2.18 à 2.55, `sentry_sdk.init` lève `ImportError: jinja2 must be installed…` (vérifié) et Sentry se coupe. |

Comportements vérifiés identiques : hooks de démarrage, upload multipart, 413 en
français au-delà de 60 Mo (annoncé ou chunked), JSON de plus de 2 Mo refusé en 413,
idempotence, webhook Stripe signé ou altéré, remontée Sentry, appel anthropic 0.34 sous
Sentry. Les contrôles ont été faits sous TestClient et sur un vrai serveur uvicorn.

Seul changement de comportement : depuis fastapi 0.132, une requête qui envoie un corps
JSON **sans en-tête `Content-Type`** reçoit un 422 au lieu d'être acceptée. C'est un
durcissement d'origine (`strict_content_type`). Le front envoie toujours
`Content-Type: application/json`, et les appels cron n'ont pas de corps : aucun impact
connu. Pour revenir à l'ancien comportement : `FastAPI(..., strict_content_type=False)`
dans `app/main.py`.
