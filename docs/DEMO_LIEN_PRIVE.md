# Lien privé de démonstration

La démo publique reste fermée (décision du 08/10/2026). Le lien privé permet de donner la
démonstration à une personne choisie (Mathys, pour la prospection) sans rien rouvrir sur le site.

Lien : `https://adjugo.pro/demo#<clé>`

- La clé est après le `#` : le navigateur ne l'envoie jamais au serveur dans l'adresse. Elle
  n'apparaît donc ni dans les journaux d'accès ni dans le Referer. La page l'efface de la barre
  d'adresse dès l'ouverture et l'envoie dans le corps d'une requête.
- La page propose deux choix : « Espace entreprises » (compte démo PME) et « Espace
  collectivités » (espace acheteur démo). Entreprise, collectivité et données sont fictives.
- Les garde-fous de la démo ne changent pas : aucun email vers un tiers, aucun fichier déposé,
  aucun appel d'IA payant, aucune modification du compte.
- Sans clé, ou avec une mauvaise clé : « Ce lien de démonstration n'est plus valide. » et un lien
  vers /demande-acces. La page n'est pas indexée et le site n'y renvoie nulle part.

## 1. Générer une clé (sur votre ordinateur)

```sh
openssl rand -base64 33 | tr '+/' '-_' | tr -d '='
```

La commande affiche 44 caractères. Moins de 32 caractères : la clé est ignorée et le lien reste
fermé. Ne la mettez ni dans le dépôt, ni dans un ticket, ni dans un document partagé.

## 2. La poser dans Railway

Railway > service de l'API (`adjugo-api`) > Variables > nouvelle variable `DEMO_LIEN_CLE` = la clé. Railway redéploie.
`DEMO_PUBLIC` ne change pas : laissez-la absente (démo publique fermée).

## 3. Donner le lien à Mathys

Envoyez-lui `https://adjugo.pro/demo#` suivi de la clé, par un canal privé (message direct).
Il garde le lien : chaque ouverture redonne les deux choix. Une session dure 12 heures au plus (réglage par défaut)
et se ferme après une heure sans activité côté entreprises ; il suffit alors de rouvrir le lien.

## 4. Couper l'accès

Remplacez `DEMO_LIEN_CLE` par une nouvelle clé (étape 1), ou supprimez la variable. Dès le
redéploiement, l'ancien lien affiche « Ce lien de démonstration n'est plus valide. » et toutes
les sessions ouvertes avec l'ancienne clé sont refusées. Avec une nouvelle clé, renvoyez le
nouveau lien aux personnes qui doivent garder l'accès.

## Pour mémoire (technique)

- Routes : `POST /api/auth/demo/lien` (vérifie la clé, n'ouvre rien), `POST /api/auth/demo` et
  `POST /api/acheteur/demo` (corps `{"cle": "..."}`). Clé absente, courte ou fausse : 404, comme une
  route inexistante. Comparaison à temps constant, limite de débit par adresse IP.
- Chaque session ouverte par le lien porte l'empreinte de la clé (revendication `dl` du jeton :
  16 premiers caractères d'un HMAC-SHA256 de la clé, clé du HMAC = `SECRET_KEY`). Elle n'est
  acceptée que si l'empreinte correspond à la clé actuelle (`app/core/demo_guard.py`).
- La clé n'est jamais journalisée : le corps des requêtes n'est pas envoyé à Sentry, et la
  valeur exacte de la clé est masquée dans tout journal (`app/core/redact.py`).
- `DEMO_PUBLIC=1` garde son sens : réouverture publique, sessions sans empreinte.
