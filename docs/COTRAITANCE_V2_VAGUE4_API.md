# Co-traitance v2 — vague 4 « Preuves, dépôt, finitions » : contrat d'API pour le front

> Partie serveur livrée le 08/10/2026 (branche de worktree, non déployée). Ce document suffit pour
> écrire les écrans **sans relire le code serveur**. Hors périmètre (vague 3, développée en
> parallèle) : fiche partenaire de l'annuaire, historique réseau.
>
> Code : `app/services/journal_membre.py` (journal vérifiable, exports), `app/routers/journal_membre.py`
> (routes), `app/core/sri.py` + `scripts/sri_update.py` (empreintes des scripts),
> `app/services/groupement_members.py` (`depot_readiness`), `app/routers/groupement.py` (dépôt,
> tableau de bord), `app/services/alerts.py` (relances), migration `q1r2s3t4u5v6`.
> Tests : `tests/test_cotraitance_v4.py` (24 tests, rejoués aussi sur Postgres 16).

## 1. Principes à respecter dans l'interface

- **Zéro émoji**, icônes lucide uniquement ; explications dans une bulle (i) (composant `.tip`
  existant ; `tip()` dans `invite.html`) ; rythme 16 px ; propre à 375 px ; aucun `v-html` /
  `innerHTML` sur une donnée serveur ; vrais boutons, libellés, focus visible, `aria-live` pour
  les résultats de vérification.
- **Un seul pourcentage dans le produit : le score de groupement.** Les contrôles avant dépôt
  s'affichent en « 3 contrôles sur 4 » (`n_ok` / `n_total`), plus en « 75 % » (le champ `pct`
  reste renvoyé pour l'écran actuel, **à ne plus afficher**).
- **Vocabulaire** : « groupement », « partenaire », « chef de file » (le serveur dit encore
  « mandataire » dans certains libellés du journal : les afficher tels quels) ; « accord
  enregistré », jamais « signature électronique » ; « DPGF » toujours accompagné de sa phrase
  simple : « le détail de vos prix de vente, ligne par ligne ».
- **On ne survend pas la preuve.** Libellé exact : `integrity_label` = « Journal vérifiable :
  toute modification ou suppression d'entrée est détectable ». Les limites (`limites[]`) vont
  dans la bulle (i), jamais cachées.

## 2. Journal vérifiable par chaque membre

### 2.1 Routes

| Route | Qui | Limite |
|---|---|---|
| `GET /api/invite/{token}/journal` | partenaire (lien magique) | 60/min |
| `GET /api/invite/{token}/journal/integrity` | partenaire (lien magique) | 30/min |
| `GET /api/invite/{token}/journal/export?format=json\|pdf` | partenaire (lien magique) | 10/min |
| `GET /api/shared/{project_id}/journal` | compte qui a réclamé le lien (« Partagé avec moi ») | 60/min |
| `GET /api/shared/{project_id}/journal/integrity` | idem | 30/min |
| `GET /api/shared/{project_id}/journal/export?format=json\|pdf` | idem | 10/min |

- `{project_id}` = champ `project_id` d'un élément de `GET /api/shared`. Bearer obligatoire
  (401 sans session) ; 404 « Dossier partagé introuvable » si ce compte n'a pas réclamé de lien
  actif sur ce marché (le chef de file lui-même reçoit aussi 404 : il a son propre journal).
- Lien magique : 404 « Lien invalide ou révoqué », 410 décliné / expiré, 404 « Projet introuvable
  ou retiré » si le marché est en corbeille. `format` inconnu : 422 « Format inconnu : json ou pdf. ».
- `GET …/journal` : réponse inchangée (`entries`, `chained`, `integrity_label`) ; seul le libellé
  change (voir § 1). Nouvelles entrées possibles : « Vous avez exporté votre journal »,
  « Le mandataire a marqué le dossier comme déposé », « Le mandataire a annulé le marquage
  « déposé » » ; le détail des alertes d'attestations devient « J-7 (date limite 20/10/2026) ».

### 2.2 `GET …/journal/integrity` — verdict + sous-chaîne recalculée

Le serveur relit les entrées qui concernent le membre (les siennes + les événements de groupement
du marché : exactement ce que montre son journal), recalcule l'empreinte de CHACUNE et vérifie
qu'elle est reliée à l'entrée qui la précède dans le journal du chef de file ; il vérifie aussi le
journal complet du chef de file et le compare à la dernière empreinte quotidienne horodatée.
Résultat mis en cache 60 s (vérification complète du journal : 5 min).

```json
{
  "schema": "adjugo-journal-membre-v1",
  "verdict": "intact", "verdict_label": "Intact", "perimetre": null,
  "message": "Journal intact : 5 entrées vérifiées une à une, aucune modification ni suppression détectée.",
  "integrity_label": "Journal vérifiable : toute modification ou suppression d'entrée est détectable",
  "verifie_le": "2026-10-08T10:19:46",
  "entrees": {"total": 5, "verifiees": 5, "alterees": 0, "non_chainees": 0},
  "premiere_alteration": null,
  "journal_complet_intact": true,
  "ancrage": null,
  "empreinte": "70160122b334e339be214653a123564432a975f46515898f7dab5aa43de3dc3b",
  "tronque": false,
  "limites": [
    "La vérification entrée par entrée est faite par Adjugo ; vous pouvez la compléter hors ligne en comparant deux exports successifs de votre journal.",
    "Les entrées écrites depuis la dernière empreinte quotidienne (moins de 24 h) ne sont couvertes que par l'export que vous avez conservé.",
    "Le journal ne montre jamais l'adresse IP ni l'email des autres membres : leurs entrées sont engagées par un sceau, pas révélées."
  ],
  "chaine": [
    {"n": 1, "at": "2026-10-08T10:19:46.548921", "action": "invite.created", "qui": "mandataire",
     "label": "Le mandataire vous a invité", "detail": "Le Gall Électricité",
     "sceau": "60e278b34d355285e1a5b2d3bb7a3ffcd369113a2b4eaece43652672f3cfea76",
     "maillon": "1f029466d2278a0d7aaa250eea6e46a8a3e0a17b8d690151c76b6e8ceba10c6d",
     "statut": "verifiee", "couverte_par_ancrage": false}
  ]
}
```

| Champ | Valeurs | Affichage recommandé |
|---|---|---|
| `verdict` | `intact` · `altere` · `vide` | pastille verte « Intact » (icône `shield-check`) · rouge « Altéré » (`shield-alert`) · grise « Aucune entrée » |
| `perimetre` | `null` · `vos_entrees` (une de SES entrées, ou une voisine, a changé) · `journal` (ses entrées sont cohérentes mais le journal du chef de file a été modifié ou tronqué) | `message` tel quel, en `aria-live="polite"` |
| `premiere_alteration` | `{n, at, label}` ou `null` | « Entrée concernée : … » sous le message |
| `ancrage` | `null` (pas encore d'empreinte quotidienne) ou `{date, date_label, horodate, entrees_couvertes, message}` | `ancrage.message` en petit (« 4 entrées antérieures au 07/10/2026 sont aussi couvertes par l'empreinte quotidienne du journal, horodatée par une autorité indépendante. ») |
| `chaine[].statut` | `verifiee` · `alteree` · `non_chainee` (entrée antérieure au chaînage, rare) | icône par ligne (`circle-check` / `circle-x` / `circle-dashed`) |
| `chaine[].couverte_par_ancrage` | booléen | facultatif (icône `stamp` en gris) |
| `empreinte` | sha256 hex | « Empreinte de votre journal : 7016 0122 b334… » (police mono, bouton « Copier ») |
| `tronque` | `true` au-delà de 2 000 entrées (cas théorique) | bandeau « Seules les 2 000 premières entrées sont vérifiées » |

Ce que la réponse ne contient **jamais** : IP, email, identifiant interne (id d'entrée, de tenant,
d'invitation), empreinte brute (`entry_hash` / `prev_hash`) d'aucune entrée. Les entrées des autres
membres n'apparaissent que comme événements de groupement (« Un partenaire a validé la convention »).

### 2.3 `GET …/journal/export?format=json` — la preuve, vérifiable hors ligne

`Content-Disposition: attachment; filename="Journal_<marché>.json"`. Chaque export est
journalisé (« Vous avez exporté votre journal ») APRÈS sa construction : l'export suivant contient
cette entrée et **prolonge** le précédent.

```json
{
  "schema": "adjugo-journal-membre-v1",
  "exporte_le": "2026-10-08T10:19:46Z",
  "marche": "Réhabilitation de l'école Jules-Ferry",
  "membre": "Le Gall Électricité",
  "verdict": {"verdict": "intact", "verdict_label": "Intact", "perimetre": null, "message": "…",
              "entrees": {"total": 5, "verifiees": 5, "alterees": 0, "non_chainees": 0},
              "premiere_alteration": null, "journal_complet_intact": true, "ancrage": null, "tronque": false},
  "integrity_label": "Journal vérifiable : toute modification ou suppression d'entrée est détectable",
  "empreinte": "70160122…",
  "algorithme": {"nom": "adjugo-journal-membre-v1", "sceau": "…", "maillon": "…", "empreinte": "…",
                 "verification_hors_ligne": ["…", "…"]},
  "limites": ["…"],
  "entrees": [{"n": 1, "at": "2026-10-08T10:19:46.548921", "action": "invite.created", "qui": "mandataire",
               "label": "Le mandataire vous a invité", "detail": "Le Gall Électricité",
               "sceau": "60e2…", "maillon": "1f02…", "statut": "verifiee"}]
}
```

`format=pdf` : même contenu, lisible (tableau date / qui / événement / 16 premiers caractères du
sceau, verdict, empreinte, rappel de l'algorithme et des limites). La preuve vérifiable est le JSON.

### 2.4 Algorithme (à recopier dans la bulle (i) « Comment vérifier ? » et la page sécurité)

1. **Sceau d'une entrée** : `sceau = sha256("adjugo-sceau-v1|" + empreinte_de_l_entree)` (hex). Il
   engage l'empreinte réelle de l'entrée dans le journal du chef de file **sans la révéler** (avec
   l'empreinte brute et sa voisine, on pourrait retrouver par force brute l'adresse IP du chef de
   file : le sceau, à sens unique, l'empêche).
2. **Maillons** : `maillon_0 = ""` ; `maillon_n = sha256(maillon_(n-1) + "|" + n + "|" + at + "|" +
   action + "|" + qui + "|" + sceau_n)` (texte UTF-8, hex). **Empreinte du journal** = dernier maillon.
3. **Vérifier un fichier** : recalculer chaque maillon depuis `n`, `at`, `action`, `qui`, `sceau` ;
   chacun doit égaler le `maillon` écrit, le dernier égaler `empreinte`.
4. **Comparer deux exports** (le point fort) : toute entrée `n` de l'export conservé doit se
   retrouver à l'identique (`at`, `action`, `qui`, `sceau`, `maillon`) dans le nouvel export. Une
   entrée modifiée ou supprimée, ou un journal réécrit par Adjugo (qui changerait les empreintes,
   donc les sceaux), rompt la comparaison.

Implémentation de référence (Python, bibliothèque standard seulement — également
`app.services.journal_membre.verify_export` / `prolonge`) :

```python
import hashlib, json

def maillon(prev, e):
    s = f'{prev}|{e["n"]}|{e["at"]}|{e["action"]}|{e["qui"]}|{e["sceau"]}'
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def verifier(doc):
    prev = ""
    for e in doc["entrees"]:
        prev = maillon(prev, e)
        if prev != e["maillon"]:
            return False
    return prev == doc["empreinte"]

def prolonge(ancien, nouveau):
    k = ("n", "at", "action", "qui", "sceau", "maillon")
    a, b = ancien["entrees"], nouveau["entrees"]
    return len(b) >= len(a) and all({x: e[x] for x in k} == {x: f[x] for x in k} for e, f in zip(a, b))

ancien, nouveau = json.load(open("Journal_ancien.json")), json.load(open("Journal_nouveau.json"))
print(verifier(ancien), verifier(nouveau), prolonge(ancien, nouveau))
```

**Limites (à afficher, cf. `limites[]`)** : la vérification entrée par entrée (empreinte recalculée)
est faite par Adjugo — le membre ne peut pas la refaire seul sans l'IP et l'acteur exacts des
entrées, qu'il ne doit pas voir ; ce qu'il refait seul, c'est le recalcul des maillons et la
comparaison d'exports. Les entrées des dernières 24 h ne sont couvertes que par son propre export.
Le hachage n'est pas une signature. L'ancrage quotidien couvre tous les clients : il n'est pas
communiqué tel quel au membre (il révélerait les autres comptes) ; le verdict en cite la date.

### 2.5 Parcours d'écran (invite.html et « Partagé avec moi », même composant)

Dans « Mon journal — qui a vu quoi » : bouton secondaire « Vérifier mon journal »
(`GET …/integrity`) → pastille + `message` (zone `aria-live`) + `ancrage.message` + empreinte
(copiable) ; liens « Télécharger la preuve (JSON) » et « Télécharger le journal (PDF) ». Bulle (i)
à côté du titre : `integrity_label` + `limites`. Une phrase sous les boutons : « Gardez ce fichier :
le prochain export doit reprendre toutes ses lignes à l'identique. » Rien d'autre à calculer côté
navigateur (la vérification hors ligne est un outil pour l'utilisateur qui le souhaite).

## 3. Empreintes des scripts (SRI) et page sécurité

- Chaque `<script src="/static/…">` des pages servies (`app.html`, `invite.html`, `acheteur.html`,
  `acheteur-landing.html`) porte `integrity="sha384-…"` : le navigateur refuse un fichier dont le
  contenu ne correspond pas. Les scripts en ligne et le script d'analytics (tiers, optionnel,
  chargé par `app.js`) ne sont pas couverts.
- **Ce que la SRI protège, dit exactement** : un fichier altéré ou périmé ENTRE le serveur et le
  navigateur (cache, proxy, fichier servi par erreur). Pas une modification des fichiers sur le
  serveur lui-même : le filet ci-dessous recalcule les empreintes des pages à partir des fichiers
  présents, un script modifié sur le serveur part donc avec sa propre empreinte. Cette
  modification se voit en comparant avec le manifeste versionné (`manifeste_publie_a_jour` et
  `pages_a_jour` valent alors `false`) et dans les journaux du serveur (« empreintes périmées »).
- **Règle pour tout le monde (front compris)** : après **toute** modification d'un fichier
  `app/static/*.js` ou `app/static/vendor/*`, lancer `python scripts/sri_update.py` et commiter les
  pages + `app/static/sri-manifest.json`. Sinon `tests/test_cotraitance_v4.py::test_sri_empreintes_a_jour`
  échoue en donnant la commande. Filet en production : une page servie avec une empreinte périmée
  est corrigée à la volée (et l'erreur est journalisée) — le logiciel ne se bloque jamais pour un
  oubli. `python scripts/sri_update.py --check` : contrôle sans rien modifier (code 1 si périmé).
- **Publication** : `GET /api/securite/empreintes-scripts` (public, 60/min, aucune donnée
  personnelle) — empreintes calculées à chaud sur les fichiers servis :

```json
{"schema": "adjugo-sri-v1", "algorithme": "sha384", "regeneration": "python scripts/sri_update.py",
 "verification": "openssl dgst -sha384 -binary <fichier> | openssl base64 -A  (à préfixer par « sha384- »)",
 "fichiers": {"/static/app.js": {"integrity": "sha384-zPbj…", "sha256": "faa6f075…", "octets": 195822}},
 "manifeste_publie": "/static/sri-manifest.json", "manifeste_publie_a_jour": true, "pages_a_jour": true}
```

  et le fichier versionné `/static/sri-manifest.json` (même `fichiers`, sans les deux booléens).
- **Texte proposé pour la page sécurité** (§ 4, après « Journal pour chaque membre » — à valider
  par Eliot, puis à reporter dans la source Markdown des pages légales) :
  « **Journal vérifiable par vous.** Chaque partenaire peut vérifier son journal (« Vérifier mon
  journal ») et en télécharger une preuve : si une entrée était modifiée ou supprimée, la
  vérification, ou la comparaison avec une preuve téléchargée plus tôt, le montrerait. »
  « **Empreintes des scripts publiées.** Le navigateur vérifie l'empreinte de chaque script servi
  par Adjugo (SRI) ; la liste des empreintes est publiée [ici](/api/securite/empreintes-scripts) et
  versionnée. Ce n'est pas une garantie absolue : la page elle-même est servie par Adjugo. »
- **CSP : inchangée** (`script-src 'self' 'unsafe-inline' 'unsafe-eval'`). Piste de durcissement,
  non forcée : (1) sortir les scripts en ligne (thème dans `app.html`, `invite.html`, `acheteur*.html`,
  `landing.html`, `demande-acces.html`) dans des fichiers `/static/*.js` couverts par SRI, ou les
  autoriser par empreinte (`'sha256-…'`) ; (2) retirer `'unsafe-inline'` de `script-src` ;
  (3) `'unsafe-eval'` reste nécessaire tant que Vue compile ses gabarits dans le navigateur
  (build complet `vue.prod.js`) — le retirer suppose des gabarits précompilés (étape de build,
  contraire au choix « sans build » actuel).

## 4. DPGF de lot (pièce `dpgf_lot`)

**Ce que fait le navigateur du partenaire** (le serveur ne reçoit jamais le détail en clair) :
déchiffrer `detail_chiffre` localement (code de récupération, `AdjugoCrypto`), produire la DPGF de
SON lot **au niveau du prix de vente** — désignation, unité, quantité, prix unitaire HT, montant HT,
total = `prix_lot_ht` — **sans aucun coût, marge, coefficient ni déboursé**, puis la déposer comme
pièce. Rien de tout cela ne va vers le LLM ni dans une DPGF commune.

**Route existante** : `POST /api/invite/{token}/contribution/piece` (multipart `file`,
`piece_type=dpgf_lot`, `expiration_date` ignorée pour une DPGF).

- Formats : PDF, `.xlsx`, `.xls`, `.ods`, **`.csv`** (le CSV n'est accepté que pour une DPGF ;
  ailleurs la liste blanche générale ne change pas). Autre format avec `piece_type=dpgf_lot` →
  422 « Une DPGF de lot se dépose en PDF, en tableur (xlsx, xls, ods) ou en CSV. »
- Sans `piece_type`, un nom contenant « DPGF » (ou « décomposition du prix global ») est classé
  `dpgf_lot` (et n'est plus pris pour un RIB : « DPGF_distribution.xlsx »).
- **Contrôles du CSV** (seul format lisible sans dépendance) — 422 avec message en français :
  UTF-8 obligatoire (BOM accepté) ; séparateur `;` ou `,` ; aucune formule (cellule commençant par
  `=`, `+`, `@`, ou `-` suivi d'autre chose qu'un nombre : « -150,00 » est accepté) ; aucune
  colonne de coûts ou de marges dans les lignes d'en-tête (« marge », « coût », « déboursé »,
  « prix d'achat », « frais généraux », « coefficient ») : « Une DPGF de lot ne contient que des
  prix de vente : retirez la colonne « Marge » (elle serait visible du chef de file). » ; 20 000
  lignes au plus. **Générateur recommandé** : CSV UTF-8 séparé par `;`, montants au format
  « 1 250,00 », pas de formule. Les PDF/tableurs ne sont pas inspectés (responsabilité du déposant).
- Effets : la part **reste soumise** et la convention **n'est pas rendue caduque** (le prix de
  vente du lot, seul imprimé dans la convention, ne change pas) — vrai aussi pour la suppression
  (`DELETE …/piece/{id}`) et la jonction depuis le coffre-fort.
- Visibilité : le partenaire et le chef de file (liste des pièces, téléchargement audité
  « Le mandataire a téléchargé votre pièce « dpgf_lot2.csv » ») ; **jamais les autres membres** ;
  absente du coffre-fort croisé (ce n'est pas une attestation) ; incluse dans le ZIP du dossier
  (pièces des parts soumises).
- Nouveaux drapeaux : `has_dpgf_lot` dans la part (`GET/PUT /api/invite/{token}/contribution`,
  `GET /api/projects/{id}/contributions`) et dans chaque partenaire du cockpit
  (`GET /api/projects/{id}/consortium` → `partners[].has_dpgf_lot`). Libellé du type :
  « DPGF du lot (prix de vente) ».
- `PATCH …/piece/{id}` `{"piece_type": "dpgf_lot"}` : 422 si le fichier n'est pas dans un format de
  DPGF ; la date d'expiration d'une DPGF est toujours vidée.
- **Lignes de la DPGF (ajout des écrans)** : `PUT /api/invite/{token}/contribution/detail`
  `{"detail_chiffre": <enveloppe>|null, "version": n}` (60/min) remplace **uniquement** l'enveloppe
  chiffrée. Les lignes de la DPGF y sont rangées avec le texte libre du détail (même clé, même code
  de récupération) : `AdjugoCrypto.packDetail(texte, {lignes})` → JSON marqué
  `{"format": "adjugo-detail-v2", "texte", "dpgf": {"lignes": [{designation, unite, quantite, pu}], "maj"}}`
  avant chiffrement ; un ancien détail (texte brut) se relit tel quel (`unpackDetail`). La part
  soumise **reste soumise**, l'offre reste figée, la convention reste valable (le détail n'est lu
  par personne d'autre et n'est imprimé nulle part) ; verrou optimiste identique au PUT complet
  (409 / 428), enveloppe stricte (422), 403 si le lien est en lecture seule ; route ajoutée à la
  garde démo. Le PUT complet garde sa règle (toute modification après soumission repasse en brouillon).

## 5. Étape 5 : « prêt à déposer » et « Marquer déposé »

### 5.1 Les 4 contrôles (`pret`)

Calculés par `depot_readiness` — dans `state.pret` (états 7-8, comme en vague 2) **et à tout moment**
via `GET /api/projects/{id}/groupement/depot` (240/h) :

```json
{"depose": false, "status": "nouveau",
 "pret": {
   "checks": {"parts_soumises": true, "attestations_ok": false, "convention_signee": false, "cerfa_generes": false},
   "libelles": {"parts_soumises": "Parts de tous les partenaires soumises, avec leur prix de vente",
                "attestations_ok": "Attestations de tous les membres valides à la date limite",
                "convention_signee": "Convention validée par tous les membres",
                "cerfa_generes": "Formulaires officiels (DC1, DC2, ATTRI1) préparés après la convention"},
   "pret": false, "n_ok": 1, "n_total": 4, "pct": 25,
   "manques": ["Kbis manquante : Le Gall Électricité", "…",
               "Convention de groupement à générer puis à faire valider par tous les membres",
               "Formulaire DC1 à (re)générer après la convention", "…"],
   "avertissements": []}}
```

- `pret` (booléen) = les 4 contrôles ; c'est lui (et non `pct`) qui vaut « Prêt à déposer ».
  `state.label` vaut « Prêt à déposer » seulement si `pret`, sinon « Convention validée — derniers
  contrôles avant dépôt » (inchangé).
- Nouveau contrôle `parts_soumises` : chaque **co-traitant** actif a soumis sa part avec un prix de
  vente (manque « Part de X pas encore soumise » / « Part de X : prix de vente du lot manquant »).
  Un **sous-traitant** en retard n'est qu'un avertissement (« … (sous-traitant : hors convention,
  utile pour le DC4) »).
- `cerfa_generes` exige désormais une convention **générée** : un formulaire préparé avant (ou sans)
  convention ne compte pas.
- `avertissements[]` (jamais bloquants) : date limite inconnue (« la validité des attestations est
  vérifiée à aujourd'hui seulement »), date limite dépassée, partenaires hors ligne (« Adjugo ne
  suit pas leurs attestations, vérifiez-les vous-même »), sous-traitants en retard.
- Ranger les `manques` sous leur contrôle : préfixe « Part de » → `parts_soumises` ;
  « Convention » → `convention_signee` ; « Formulaire » → `cerfa_generes` ; le reste →
  `attestations_ok`. Affichage : « 3 contrôles sur 4 » (pas de pourcentage).

### 5.2 `POST /api/projects/{id}/groupement/deposer` — « Marquer déposé » (30/h)

Corps facultatif `{"confirmer": false}`. Le marché passe au statut `envoye` (état 8 « Déposé »,
étape 5 faite), avec une entrée de journal visible de tous les membres (« Le mandataire a marqué le
dossier comme déposé »). Avertir, pas bloquer :

- dossier incomplet sans confirmation → **409** :
  `{"detail": {"code": "pas_pret", "message": "3 contrôle(s) avant dépôt ne sont pas réglés. Confirmez pour marquer le dossier comme déposé quand même.", "manques": […], "avertissements": […], "checks": {…}}}`
  → boîte de confirmation (« Le dossier n'est pas complet : le marquer déposé quand même ? Vous avez
  peut-être déposé hors d'Adjugo. »), focus sur « Annuler », puis renvoyer `{"confirmer": true}` ;
- succès → `{"ok": true, "deja_depose": false, "status": "envoye", "complet": true|false, "pret": {…}, "state": {…}}` ;
- déjà déposé (ou gagné / perdu) → 200 `{"ok": true, "deja_depose": true, "status": "envoye", "complet": null, "state": {…}}` (aucune nouvelle trace).

Après le marquage : plus aucune relance automatique (parts, attestations) pour ce marché.

### 5.3 `DELETE /api/projects/{id}/groupement/deposer` — annuler un marquage fait par erreur (30/h)

Le marché retrouve son statut d'avant (« nouveau » ou « en cours ») ; trace « Le mandataire a annulé
le marquage « déposé » ». Réponse `{"ok": true, "etait_depose": true, "status": "nouveau", "state": {…}}` ;
pas déposé → `etait_depose: false` ; gagné / perdu → 409 `{"code": "marche_clos", "message": "Le marché est déjà marqué gagné ou perdu : changez son statut depuis sa fiche."}`.

Démo : `POST` et `DELETE …/deposer` → 403 « La démo est en lecture guidée : créez votre compte
gratuit pour marquer un dossier déposé. » ; 404 « Appel d'offres introuvable » hors organisation.

### 5.4 Côté partenaire

Aucune route nouvelle : `for_member.state` passe à `depose` (stepper : étape 5 « fait ») et le
journal montre l'entrée. Ne jamais afficher au partenaire les `manques` du chef de file.

## 6. Relances automatiques (aucune action front)

Cron existant `POST /api/admin/run-cotraitance-reminders` :
- attestations manquantes / expirant avant la date limite : **une** alerte par partenaire au palier
  J-7 puis **une** au palier J-3 (avant : la même alerte repartait chaque jour du palier) ;
- un partenaire qui doit aussi soumettre sa part reçoit **un seul email** (rappel de part + liste
  des attestations) ;
- le chef de file reçoit **un récapitulatif par marché** (plus un email par partenaire) ;
- plus rien après « Marquer déposé » (statut envoyé, gagné, perdu ou abandonné).
Journal du partenaire : « Adjugo vous a alerté : une attestation manque ou expire · J-3 (date limite 20/10/2026) ».

## 7. Tableau de bord : `GET /api/groupement/tableau-de-bord` (240/h)

Données réelles de l'organisation uniquement (aucun montant, aucun nom de partenaire) :

```json
{"marches_accessibles_en_groupement": 1,
 "accessibles": [{"project_id": 12, "name": "…", "deadline": "2026-11-04", "groupement_score": 81}],
 "groupements_en_cours": 1,
 "par_etape": [{"n": 1, "key": "reperer", "label": "Repérer le marché", "count": 1},
               {"n": 2, "key": "trouver", "label": "Trouver les partenaires", "count": 0},
               {"n": 3, "key": "reunir", "label": "Réunir les parts", "count": 1},
               {"n": 4, "key": "monter", "label": "Monter le groupement", "count": 0},
               {"n": 5, "key": "deposer", "label": "Déposer", "count": 0}],
 "en_cours": [{"project_id": 7, "name": "…", "deadline": "2026-10-28", "etape": 3, "state": "parts_completes",
               "label": "Toutes les parts reçues", "n_membres": 1, "convention_status": ""}],
 "deposes": 0, "tronque": false, "calcule_le": "2026-10-08T10:19:46"}
```

- « accessibles » = verdict « Bon potentiel en groupement » (`go_decision = go_groupement`), marché
  ouvert (ni déposé, ni clos, date limite non dépassée) ; jusqu'à 10, date limite la plus proche
  d'abord. Le seul pourcentage est `groupement_score` (« avec vos partenaires : 81 % »).
- `par_etape[0]` compte les marchés au stade « Repérer » avec un potentiel de groupement ; les
  étapes 2 à 5 = groupements en cours (`en_cours`, 20 au plus) ; `deposes` à part.
- Carte proposée : « N marchés accessibles en groupement » (bulle (i) : « Marchés que vous ne
  pourriez pas viser seul, mais oui avec des partenaires. ») + mini-stepper des 5 étapes avec leurs
  compteurs ; clic → fiche du marché.

## 8. Ce qui change sur l'existant

| Élément | Changement |
|---|---|
| `integrity_label` (`/api/invite/{token}/journal`, repli dans `app.html`) | « Journal vérifiable : toute modification ou suppression d'entrée est détectable » |
| `state.pret` | 4 contrôles (+ `parts_soumises`), `libelles`, `pret`, `n_ok`, `n_total`, `avertissements` ; `pct` conservé (à ne plus afficher) |
| `project_contributions.chiffrage_note` | **supprimée** (migration `q1r2s3t4u5v6` ; contenu résiduel déplacé dans `note_au_mandataire`, préfixé « (ancienne approche prix) ») |
| Types de pièce | + `dpgf_lot` |
| Pages servies | attributs `integrity` sur les `<script src>` |
| `audit_logs.created_at` | écrit en UTC naïf (la vérification du journal ne dépend plus du fuseau de la session Postgres) |
| Alertes d'attestations | une par palier et par date limite, détail « J-7 (date limite JJ/MM/AAAA) » |
| Journal d'un **sous-traitant** | l'entrée « Le mandataire a figé l'offre commune » n'affiche plus le montant (« total … € HT ») : un non-signataire ne reçoit jamais le total (règle de la vague 2, qui fuitait par le détail du journal) |

## 9. Ce que chaque écran affiche / n'affiche JAMAIS

| Écran | Affiche | N'affiche jamais |
|---|---|---|
| Partenaire — vérification du journal | verdict, message, date de l'empreinte quotidienne, empreinte, sceaux (tronqués), exports | IP, email, identifiants internes, empreintes brutes, entrées propres des autres membres |
| Partenaire — DPGF | sa DPGF, son état « déposée » | coûts, marges ; la DPGF des autres |
| Chef de file — contrôles avant dépôt | 4 contrôles, manques, avertissements, « 3 contrôles sur 4 » | un pourcentage ; le détail chiffré |
| Chef de file — tableau de bord | nombres, noms de SES marchés, étape, score de groupement | montants, noms des partenaires, données d'une autre organisation |
| Page sécurité | empreintes publiées, limites honnêtes | « zero-knowledge », « signature électronique », « infalsifiable » |

## 10. Notes d'intégration

- Migration `q1r2s3t4u5v6` : `down_revision = "o9p0q1r2s3t4"` ; **à rechaîner après la révision de
  la vague 3**. Idempotente, testée SQLite (neuve / révision précédente avec données / rejeu) et
  Postgres 16 (neuve / production simulée / rejeu). La garde ajoutée dans `n8o9p0q1r2s3` évite
  de lire une colonne qui n'existe plus sur une base neuve.
- Après la fusion avec la vague 3 (qui modifie `app.js`), relancer `python scripts/sri_update.py`.
- `GROUP_EVENTS` (événements visibles de tous les membres) est **figé** pour `adjugo-journal-membre-v1` :
  si la vague 3 veut y ajouter une action qui a déjà des entrées en base, il faut une `v2` (sinon
  les exports conservés par les membres ne se compareraient plus). Les actions `network.*` restent
  dans le tenant du chercheur et n'entrent pas dans la projection.

## 11. Écrans livrés (08/10/2026, même branche, non déployés)

| Écran | Ce qui est livré |
|---|---|
| `invite.html` — « Mon journal » | bouton « Vérifier mon journal » (verdict en pastille, `message` en `aria-live`, entrée concernée, date du dernier horodatage ou « pas encore d'empreinte quotidienne », empreinte tronquée + « Copier ») ; « Télécharger la preuve (JSON) » et « Télécharger le journal (PDF) » (fetch → fichier, erreurs lisibles, journal rechargé) ; bulle (i) du titre = libellé exact + `limites[]` ; bulle (i) « Vérifier vous-même » (garder la preuve, comparer deux exports, recalcul des maillons possible) |
| `invite.html` — « Ma DPGF de lot » | lignes désignation / unité / quantité / prix unitaire HT, montant et total calculés dans le navigateur, comparaison au prix de vente du lot (avertir, pas bloquer) ; « Enregistrer mes lignes » (chiffré, route « détail seul ») ; « Relire et déposer la DPGF » : aperçu EXACT du fichier (CSV `AdjugoCrypto.dpgf.csv`), puis dépôt `dpgf_lot` et retrait de l'ancienne ; « Télécharger le fichier (CSV) » (local, rien n'est envoyé) ; deux lignes « Partagé avec le chef de file, au dépôt » / « Jamais partagé » ; carte verrouillée tant que le détail n'est pas déchiffré (bouton « Déverrouiller avec mon code ») ; ancre `#dpgf` |
| `app.html` / `app.js` — « Partagé avec moi » | même vérification et mêmes exports via `/api/shared/{project_id}/journal/…` ; les lignes de DPGF sont conservées à chaque enregistrement du détail ; bloc « Ma DPGF de lot » (déposée ou non, nombre de lignes chiffrées) avec « Préparer ma DPGF de lot » qui ouvre la page partenaire du dossier (`/invite/{token}#dpgf`) ; type de pièce « DPGF du lot (prix de vente) », sans date de validité |
| `app.html` / `app.js` — chef de file | bloc « Avant de déposer / Prêt à déposer » dès qu'un partenaire est invité : `GET /groupement/depot`, « N contrôles sur 4 » (aucun pourcentage), manques rangés sous leur contrôle (max 3 + « et N autres ») avec l'action qui les règle (relancer / voir les parts, voir les attestations, préparer / régénérer la convention ou voir les accords, préparer les documents), avertissements ; « Marquer déposé » avec confirmation (focus sur « Annuler » ; dossier incomplet : liste des manques et « Marquer déposé quand même ») ; état « Dossier marqué déposé » + « Retirer le marquage » (confirmation) ; pastille « DPGF du lot reçue » dans le cockpit ; journal d'accès : libellés `groupement.depose`, `groupement.depot_annule`, `guest.export_journal`, `guest.update_piece`, bulle (i) = libellé vérifiable (fin de « preuve opposable ») ; heures du journal lues en UTC puis affichées à l'heure locale |
| `app.html` — tableau de bord | carte « Réseau Adjugo » : « N marchés accessibles en groupement » (serveur, bulle (i)), « N groupements en cours · N déposés », mini-stepper des 5 étapes avec compteurs (pastilles à 375 px), lignes cliquables (vrais boutons) : groupements en cours « Étape n sur 5 » + parts reçues, puis marchés accessibles « Avec partenaires : 81 % » (seul pourcentage) ; l'ancienne jauge « prêt XX % » disparaît de cette carte |

Contrôlé dans le navigateur (serveur local, base SQLite jetable) à 1 024 px et 375 px : aucun
débordement horizontal (les bulles masquées de la convention faisaient défiler la zone de travail
de `invite.html` : corrigé par `overflow-x:hidden` sur `.work` de cette page), parcours DPGF complet
(code de récupération, enregistrement, rechargement → lignes relues, relecture, dépôt, part
toujours soumise), vérification et exports du journal, « Marquer déposé » puis retrait.