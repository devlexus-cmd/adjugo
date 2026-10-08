# Co-traitance v2 — vague 2 « Monter le groupement » : contrat d'API pour le front

> Partie serveur livrée le 08/10/2026 (branche de worktree, non déployée). Ce document suffit pour
> écrire les écrans **sans relire le code serveur**. Code : `app/services/groupement_convention.py`
> (modèle déterministe, 0 LLM), `app/routers/convention.py` (routes), `app/services/groupement_members.py`
> (état dérivé + stepper). Tests : `tests/test_convention_groupement.py`.

## 1. Principes à respecter dans l'interface

- **Pas de conseil juridique.** Afficher en permanence (assistant, aperçu, écran de validation, PDF)
  le champ `avertissement` renvoyé par l'API : « Modèle à faire relire par un conseil (avocat,
  juriste, CCI) : ce n'est pas un conseil juridique. »
- **On ne survend pas la signature.** Ce que fait un membre est un **accord enregistré**, pas une
  signature électronique qualifiée. Vocabulaire UI : « Valider la convention », « Donner mon accord »,
  « Accord enregistré le … ». Jamais « signé électroniquement ». Afficher `nature_accord` sous le
  bouton de validation.
- **Termes légaux toujours accompagnés de la phrase simple** (les deux viennent de l'API) :
  « Groupement conjoint — chacun est responsable de sa part », « Groupement solidaire — tous sont
  responsables de tout », « Mandataire solidaire — le chef de file répond aussi de la part de
  chaque partenaire ».
- **Zéro jargon** : « groupement », « partenaire », « chef de file » ; jamais « consortium ».
  « DCE » → « le dossier du marché » ; DC1/DC2/ATTRI1 → « les formulaires officiels » (codes en
  gris ou dans une bulle « c'est quoi ? »).
- **Avertir, pas bloquer** : `avertissements[]` s'affichent en bandeau orange, ils n'empêchent rien.
  Seuls `manques[]` (données indispensables au texte) empêchent la génération.
- **UI sobre** : zéro émoji, explications dans une bulle (i), rythme 16 px.
- **Texte de la convention** : `content_md` / `apercu_md` sont du Markdown simple (titres `#`/`##`,
  listes `- `, gras `**…**`, italique `*…*`). Les valeurs saisies (noms, lots) y sont **échappées**
  (`\*`, `\_`, `` \` ``, `\\`, `\#`, `\[`, `\]`) : un rendu Markdown les affiche littéralement.
  **Ne jamais injecter ce texte en `v-html` sans échapper le HTML d'abord** (les noms peuvent
  contenir `<`, `&`). Le plus sûr : afficher le PDF (`/pdf`) ou un rendu maison qui échappe le HTML
  puis applique `#`, `**`, `*`, `- `, et retire les `\` d'échappement.

## 2. Statuts

### Convention (`status`)

| Valeur | Libellé UI recommandé (`status_label`) | Sens |
|---|---|---|
| `aucune` | Pas encore préparée | Aucun brouillon enregistré (GET renvoie quand même les défauts) |
| `draft` | Brouillon | Choix en cours ; texte pas figé ; offre pas figée par la convention |
| `a_signer` | Générée — accords en attente | Texte figé (empreinte unique), total révélé aux membres, accords attendus |
| `signee` | Validée par tous les membres | Tous les accords enregistrés (ou cochés hors ligne) |
| `perimee` | Plus à jour — à régénérer | Une part, un prix, la composition ou une donnée imprimée a changé |

### Accord d'un membre (`signatures[].status`)

| Valeur | Libellé UI (`status_label`) |
|---|---|
| `pending` | En attente |
| `signed` | Accord enregistré |
| `hors_ligne` | Accord recueilli hors ligne (coché par le chef de file) |
| `perimee` | Caduc : la convention doit être régénérée |

### Niveau d'identité (`identity_level`, imprimé dans le PDF)

| Valeur | Libellé (`identity_label`) | Quand |
|---|---|---|
| `compte_verifie` | accord enregistré depuis son compte Adjugo (adresse email vérifiée) | Mandataire ; partenaire connecté au compte qui a réclamé le lien |
| `email_verifie` | accord enregistré via le lien, adresse email vérifiée par code | Partenaire par lien après code reçu par email (OTP existant) |
| `lien_seul` | accord enregistré via le lien (identité non vérifiée) | Lien seul (email non configuré ou destinataire sans adresse) |
| `""` | accord recueilli hors ligne, déclaré par le mandataire | Membre hors ligne coché par le chef de file |

### Ce que le règlement impose (`forme_imposee.code`)

| Code | Libellé (`libelle`) | Affichage |
|---|---|---|
| `non_verifie` | Non vérifié : le dossier du marché (DCE) n'a pas encore été analysé. *(ou : phrases trouvées à lire, sans interprétation)* | Bouton « Relire le dossier du marché » si `dossier_disponible` |
| `non_specifie` | Non trouvé dans le DCE (le dossier du marché). | Texte gris |
| `libre` | Le règlement laisse le choix de la forme du groupement. | + citation |
| `conjoint` | Le règlement impose un groupement conjoint (chacun responsable de sa part). | + citation |
| `solidaire` | Le règlement impose un groupement solidaire (tous responsables de tout). | + citation |

`extrait` est **toujours** une citation littérale vérifiée contre le texte intégral du dossier
(`citation_guard`), sinon vide. Afficher entre guillemets français, en italique, avec « Extrait du
dossier du marché ». `clauses[]` : jusqu'à 3 phrases littérales (relecture). Ne jamais reformuler.

### État du groupement et stepper (`state`, dérivé, jamais stocké)

Les 8 états de la vague 1 sont inchangés (`steps`, `index`, `state`) ; seul le libellé de
`convention_a_signer` devient « Convention à valider ». Nouveaux champs :

- `etape` (1→5) et `etapes[]` = `{n, key, label, states[], status: fait|en_cours|a_faire}` :
  1 « Repérer le marché » (seul, potentiel) · 2 « Trouver les partenaires » (composition, invitation)
  · 3 « Réunir les parts » (parts_completes) · 4 « Monter le groupement » (convention_a_signer)
  · 5 « Déposer » (pret_a_deposer, depose).
- `convention` = `{id, status, version, forme, n_signataires, n_accords, toutes_validees, frozen_at}` ou `null`.
- `pret` (vue mandataire, quand la convention est validée) = `{checks: {convention_signee,
  attestations_ok, cerfa_generes}, pct, manques[]}`. Tant que `pct < 100`, `label` vaut
  « Convention validée — derniers contrôles avant dépôt » (sinon « Prêt à déposer »).

## 3. Routes côté chef de file (mandataire)

Authentification : `Authorization: Bearer <jwt>`. Portée organisation (un coéquipier voit le même
marché). 404 « Projet introuvable » si le marché n'est pas à l'organisation. Toutes les écritures
renvoient **403** pour le compte démo : `{"detail": "La démo est en lecture guidée : créez votre
compte gratuit pour monter un groupement."}`. Erreurs de validation : 422 avec `detail` texte en
français (ou `{message, missing[]}`). Limites : GET 240/h, PUT 120/h, générer 20/h, valider 30/h,
hors ligne 60/h, relire 10/h, PDF 60/h (429 au-delà).

### 3.1 `GET /api/projects/{id}/groupement/convention` — assistant + état + texte

Réponse (statut `aucune` ou `draft`) — champs principaux :

```json
{
  "project_id": 7,
  "status": "draft", "status_label": "Brouillon", "version": 0,
  "avertissement": "Modèle à faire relire par un conseil (avocat, juriste, CCI) : ce n'est pas un conseil juridique.",
  "nature_accord": "Votre accord est enregistré par Adjugo (date, empreinte du texte, niveau d'identité) : ce n'est pas une signature électronique qualifiée. Les formulaires officiels (DC1, ATTRI1) restent à signer au moment du dépôt.",
  "forme": "conjoint",
  "forme_label": {"value": "conjoint", "terme": "Groupement conjoint", "phrase": "Chacun est responsable de sa part",
                  "explication": "Chaque entreprise s'engage sur la part qui lui revient dans la répartition, et n'en répond devant l'acheteur que pour cette part."},
  "mandataire_solidaire": true,
  "forme_imposee": {"code": "non_verifie", "libelle": "Non vérifié : le dossier du marché (DCE) n'a pas encore été analysé.",
                    "extrait": "", "clauses": [], "source": "aucune", "relu_le": null, "dossier_disponible": false},
  "habilitation": {"representer": true, "signer_candidature_offre": true, "negocier": true, "signer_modifications": false},
  "params": {"decision": "unanimite", "delai_reponse_jours": 5, "defaillance": "remplacement",
             "sortie_preavis_jours": 15, "confidentialite_annees": 5, "pi": "chacun_garde",
             "penalites": "responsable_paie", "assurances_travaux": true, "litiges": "amiable_puis_tribunal",
             "part_mandataire_ht": 60000.0, "lot_mandataire": "Lot 1 — Couverture", "mandataire_qualite": "Président"},
  "membres_hors_ligne": [],
  "candidats_hors_ligne": [{"link_id": 12, "company": "Kerjean Menuiserie", "siret": "55566677700088", "lot": "Lot 5", "representant_legal": "Anne Kerjean"}],
  "options": { "…": "voir 3.1 bis" },
  "membres": [
    {"membre": "mandataire", "company": "Breizh Couverture", "role": "mandataire", "lot": "Lot 1 — Couverture", "prix_lot_ht": 60000.0},
    {"membre": "partenaire", "company": "Le Gall Électricité", "role": "cotraitant", "lot": "Lot 2 — Électricité", "prix_lot_ht": 40000.0},
    {"membre": "partenaire", "company": "Morvan Plomberie", "role": "cotraitant", "lot": "Lot 3 — Plomberie", "prix_lot_ht": null}
  ],
  "total_offre_ht": null,
  "total_estime_ht": null,
  "manques": ["Morvan Plomberie n'a pas encore soumis sa part"],
  "peut_generer": false,
  "avertissements": ["À 2 membres, le total de l'offre révèle à chacun la part de l'autre."],
  "content_hash": null, "frozen_at": null,
  "signatures": [], "n_signataires": 0, "n_accords": 0,
  "state": { "…": "groupement_state, cf. § 2" },
  "content_md": null,
  "masquer_repartition": false,
  "apercu_md": "# Convention de groupement momentané d'entreprises\n\n*Brouillon : ce texte n'est pas encore figé…*",
  "ma_signature": {"status": null, "peut_valider": false, "signataire_nom": "Eliot Viegas", "signataire_qualite": "Président", "email_verifie": true}
}
```

- `total_offre_ht` : total **figé** (seulement `a_signer`/`signee`). `total_estime_ht` : somme des prix
  connus en brouillon (mandataire seul), `null` si une part manque.
- `membres[].prix_lot_ht` : prix de **vente** de chaque part (le mandataire les voit tous). Jamais de
  détail chiffré, coûts ou marges (ils n'existent pas dans cette réponse).
- `masquer_repartition` et `apercu_md` n'existent **qu'en brouillon**. En `a_signer`/`signee`/`perimee`,
  c'est `content_md` (texte figé) qui est renvoyé.
- `manques[]` (bloquants pour générer) peut contenir : forme à choisir ; « Votre part (chef de file) :
  montant € HT à indiquer » ; « X n'a pas encore soumis sa part » ; « X : prix de lot manquant » ;
  « Aucun partenaire… » ; « Profil entreprise à compléter… » ; partenaire hors ligne sans prix ou
  plus rattaché.
- `avertissements[]` (jamais bloquants) : forme différente de celle imposée ; citation qui parle de
  mandataire solidaire ; part non précisée ; représentant légal manquant ; même part attribuée deux
  fois ; même SIRET deux fois ; sous-traitant (hors groupement, DC4) ; « votre part reprend votre
  estimation » ; « à 2 membres le total révèle la part de l'autre » ; partenaire rattaché ni invité
  ni hors ligne.

#### 3.1 bis `options` (tout ce qu'il faut pour dessiner l'assistant)

```json
{
  "formes": [
    {"value": "conjoint", "terme": "Groupement conjoint", "phrase": "Chacun est responsable de sa part", "explication": "…"},
    {"value": "solidaire", "terme": "Groupement solidaire", "phrase": "Tous sont responsables de tout", "explication": "…"}
  ],
  "mandataire_solidaire": {"terme": "Mandataire solidaire", "phrase": "Le chef de file répond aussi de la part de chaque partenaire",
                           "explication": "…", "disponible_si": "conjoint"},
  "habilitation": [
    {"key": "representer", "libelle": "Représenter le groupement auprès de l'acheteur et coordonner le travail de tous", "terme": "…", "defaut": true, "obligatoire": true},
    {"key": "signer_candidature_offre", "libelle": "Signer et déposer la candidature et l'offre au nom de tous", "terme": "…", "defaut": true, "obligatoire": false},
    {"key": "negocier", "libelle": "Négocier avec l'acheteur au nom de tous (sans changer la part ou le prix d'un membre sans son accord écrit)", "terme": "…", "defaut": true, "obligatoire": false},
    {"key": "signer_modifications", "libelle": "Signer les avenants (modifications du marché) au nom de tous", "terme": "…", "defaut": false, "obligatoire": false}
  ],
  "params": [
    {"key": "decision", "type": "choix", "defaut": "unanimite", "libelle": "Comment le groupement prend ses décisions communes",
     "choix": [{"value": "unanimite", "libelle": "À l'unanimité : tous les membres doivent être d'accord"},
               {"value": "majorite", "libelle": "À la majorité des membres (une voix par membre)"}]},
    {"key": "delai_reponse_jours", "type": "entier", "defaut": 5, "min": 1, "max": 30, "unite": "jours", "libelle": "…"},
    {"key": "defaillance", "type": "choix", "defaut": "remplacement", "choix": ["…"]},
    {"key": "sortie_preavis_jours", "type": "entier", "defaut": 15, "min": 0, "max": 90, "unite": "jours"},
    {"key": "confidentialite_annees", "type": "entier", "defaut": 5, "min": 0, "max": 10, "unite": "ans"},
    {"key": "pi", "type": "choix", "defaut": "chacun_garde", "choix": ["…"]},
    {"key": "penalites", "type": "choix", "defaut": "responsable_paie", "choix": ["…"]},
    {"key": "assurances_travaux", "type": "oui_non", "defaut": true, "aide": "Par défaut : oui si le marché ressemble à des travaux, non sinon."},
    {"key": "litiges", "type": "choix", "defaut": "amiable_puis_tribunal", "choix": ["…"]}
  ],
  "mandataire": [
    {"key": "part_mandataire_ht", "type": "montant", "libelle": "Votre part : prix de vente HT de ce que vous réalisez"},
    {"key": "lot_mandataire", "type": "texte", "libelle": "Votre part : lot ou prestations que vous réalisez"},
    {"key": "mandataire_qualite", "type": "texte", "libelle": "Qualité du signataire (ex. gérant, président)"}
  ]
}
```

Afficher **tels quels** `libelle` (texte principal) et `terme` (sous-texte gris ou bulle (i)).

### 3.2 `PUT /api/projects/{id}/groupement/convention` — enregistrer le brouillon

Mise à jour partielle : n'envoyer que les champs modifiés. Crée le brouillon s'il n'existe pas
(pré-rempli avec la forme imposée si une citation la prouve).

```json
{
  "forme": "conjoint",
  "mandataire_solidaire": true,
  "habilitation": {"signer_modifications": true},
  "params": {"part_mandataire_ht": 60000, "lot_mandataire": "Lot 1 — Couverture", "mandataire_qualite": "Président",
             "confidentialite_annees": 5, "pi": "chacun_garde"},
  "membres_hors_ligne": [{"link_id": 12, "prix_lot_ht": 15000, "lot": "Lot 5 — Menuiserie",
                          "representant_legal": "Anne Kerjean", "signataire_qualite": "Gérante"}],
  "masquer_repartition": false,
  "confirmer_modification": false
}
```

Réponse : même forme que le GET (3.1).

- `forme` : `""` | `conjoint` | `solidaire`. Passer à `solidaire` remet `mandataire_solidaire` à `false`
  (l'option n'existe qu'en conjoint).
- `habilitation.representer` est toujours `true` (non décochable).
- `membres_hors_ligne` : **remplace** la liste. Seuls les `link_id` de `candidats_hors_ligne`.
- Erreurs : 422 valeur invalide (« … doit être entre 0 et 10 ans. », « Forme inconnue … »,
  « Pouvoir inconnu … ») ; 404 partenaire hors ligne introuvable ; 422 doublon hors ligne ;
  **409** `{"code": "convention_generee", "message": "…confirmez."}` si la convention est générée et
  que `confirmer_modification` n'est pas `true` (le front affiche une confirmation : « Modifier la
  convention annule les accords déjà enregistrés. Continuer ? », puis renvoie avec
  `confirmer_modification: true` → la convention repasse en `draft`, les accords deviennent caducs) ;
  **422** si l'on ne change que `masquer_repartition` sur une convention générée.

### 3.3 `POST /api/projects/{id}/groupement/convention/relire-dce` — relire le dossier du marché

Sans corps. Relit le texte intégral du dossier archivé (dossier « DCE » du marché ; extraction bornée,
0 LLM), re-vérifie la citation de l'analyse, sinon propose les phrases littérales qui parlent de la
forme du groupement, **sans interprétation**.

```json
{"forme_imposee": {"code": "non_verifie",
  "libelle": "Le dossier du marché parle de la forme du groupement : lisez la phrase citée (Adjugo ne l'interprète pas à votre place).",
  "extrait": "En cas de groupement conjoint, le mandataire sera solidaire de chacun des membres du groupement.",
  "clauses": ["En cas de groupement conjoint, le mandataire sera solidaire de chacun des membres du groupement."],
  "source": "dossier_relu", "relu_le": "2026-10-08T01:30:10", "dossier_disponible": true}}
```

Erreur : 404 « Aucun dossier du marché lisible n'est archivé pour ce marché : importez-le depuis la
fiche du marché. » Afficher le bouton seulement si `forme_imposee.dossier_disponible`.

### 3.4 `POST /api/projects/{id}/groupement/convention/generer` — figer l'offre et générer

Corps facultatif : `{"regenerer": false}`. **Fusion avec « Figer l'offre »** : total figé et révélé
aux membres, texte figé, une empreinte unique, une ligne d'accord par membre, email « Convention de
groupement à valider » à chaque partenaire invité (jamais depuis la démo, seulement si l'adresse du
chef de file est confirmée, au plus 1 email par partenaire toutes les 30 min, 3 par partenaire et
60 par organisation sur 24 h). Les **sous-traitants** invités ne sont pas membres du groupement :
ni signataires, ni dans l'annexe, leur prix n'entre pas dans le total (avertissement affiché), et
leur part ne rend pas la convention caduque.

Réponse : même forme que le GET, avec `status: "a_signer"`, `version`, `content_md`, `content_hash`,
`total_offre_ht`, `frozen_at`, `signatures[]` (toutes `pending`) et `emails_envoyes` :

```json
{
  "status": "a_signer", "status_label": "Générée — accords en attente", "version": 1,
  "content_hash": "e6bd840fcaf0d8ddadbf25d799351c0d54a0d1598960f2a8fcbcdffcb4dc3d05",
  "total_offre_ht": 125000.5, "frozen_at": "2026-10-08T01:30:10.964024",
  "signatures": [
    {"membre": "mandataire", "company": "Breizh Couverture", "status": "pending", "status_label": "En attente",
     "signed_at": null, "identity_level": null, "identity_label": null, "signataire_nom": "", "signataire_qualite": "",
     "invite_id": null, "link_id": null},
    {"membre": "partenaire", "company": "Le Gall Électricité", "status": "pending", "…": "…", "invite_id": 2, "link_id": null}
  ],
  "n_signataires": 3, "n_accords": 0,
  "ma_signature": {"status": "pending", "peut_valider": true, "signataire_nom": "Eliot Viegas", "signataire_qualite": "Président", "email_verifie": true},
  "emails_envoyes": 2
}
```

Erreurs :
- 422 `{"message": "Choisissez d'abord la forme du groupement.", "missing": ["Forme du groupement : …"]}`
- 422 `{"message": "Impossible de générer la convention : il manque des éléments.", "missing": ["Le Gall Électricité n'a pas encore soumis sa part"]}`
- 409 `{"code": "deja_generee", "message": "La convention est déjà générée (version 1). La régénérer annule les accords déjà enregistrés : confirmez."}` → confirmation, puis `{"regenerer": true}` (version + 1, nouvelle empreinte, accords remis à « En attente »).

### 3.5 `POST /api/projects/{id}/groupement/convention/valider` — accord du chef de file

```json
{"content_hash": "e6bd840f…", "signataire_nom": "Eliot Viegas", "signataire_qualite": "Président", "accepte": true}
```

Réponse : même forme que le GET (la ligne `mandataire` passe à `signed`, `identity_level:
compte_verifie`). Idempotent. Erreurs : 403 `{"code": "email_non_verifie", …}` (adresse du compte non
confirmée) ; 409 `{"code": "texte_modifie", …}` (empreinte différente : recharger) ; 409
`{"code": "pas_generee"|"perimee", …}` ; 422 « Cochez « J'ai lu la convention et je donne mon
accord ». » ; 422 nom manquant.

### 3.6 `POST /api/projects/{id}/groupement/convention/hors-ligne/{link_id}` — accord hors ligne

```json
{"accord_recueilli": true, "signataire_nom": "Anne Kerjean", "signataire_qualite": "Gérante"}
```

Coche (ou décoche avec `accord_recueilli: false`) l'accord d'un partenaire rattaché **sans
invitation**. Statut `hors_ligne`, imprimé « accord recueilli hors ligne, déclaré par le mandataire ».
Erreurs : 404 si ce partenaire n'est pas dans la convention ; 409 si la convention n'est pas générée
ou est caduque. Si c'était le dernier accord → `status: "signee"`.

### 3.7 `GET /api/projects/{id}/groupement/convention/pdf`

PDF du texte figé + section « Accords enregistrés » (empreinte SHA-256, version, date de figement,
chaque membre avec nom, qualité, niveau d'identité et date). En brouillon : PDF « brouillon »
(sans prix si `masquer_repartition`). Une convention caduque porte en tête « PLUS À JOUR ».
Nom de fichier : `Convention_groupement_<marché>_v<n>.pdf`.

## 4. Routes côté partenaire (lien magique)

Portée stricte : `invite.project_id`. Lien révoqué → 404 « Lien invalide ou révoqué » ; décliné →
410 « Vous avez décliné cette invitation… » ; expiré → 410. Si le partenaire a un compte et a
réclamé le lien (« Partagé avec moi »), le front **ajoute son Bearer** : son niveau d'identité devient
`compte_verifie`. Limites : GET 120/min, PDF 30/min, valider 20/h.

### 4.1 `GET /api/invite/{token}/convention`

Pas encore préparée :

```json
{"status": "aucune", "status_label": "Pas encore préparée", "avertissement": "…", "nature_accord": "…",
 "message": "Le chef de file n'a pas encore préparé la convention de groupement."}
```

Brouillon (le partenaire ne voit **que son propre prix**, jamais ceux des autres ni le total) :

```json
{
  "status": "draft", "status_label": "Brouillon", "version": 0,
  "forme": "conjoint", "forme_label": {"terme": "Groupement conjoint", "phrase": "Chacun est responsable de sa part", "…": "…"},
  "mandataire_solidaire": true,
  "habilitation": [{"key": "representer", "libelle": "Représenter le groupement auprès de l'acheteur et coordonner le travail de tous", "terme": "…"}],
  "params": [{"key": "decision", "libelle": "Comment le groupement prend ses décisions communes", "valeur": "unanimite",
              "valeur_libelle": "À l'unanimité : tous les membres doivent être d'accord"}],
  "content_md": null, "content_hash": null, "total_offre_ht": null,
  "membres": [
    {"membre": "mandataire", "company": "Breizh Couverture", "role": "mandataire", "lot": "Lot 1 — Couverture"},
    {"membre": "partenaire", "company": "Le Gall Électricité", "role": "cotraitant", "lot": "Lot 2 — Électricité"},
    {"membre": "partenaire", "company": "Morvan Plomberie", "role": "cotraitant", "lot": "Lot 3 — Plomberie", "prix_lot_ht": 25000.5}
  ],
  "apercu_md": "# Convention de groupement…\n…prix de vente : affiché à la génération de la convention…",
  "ma_signature": {"status": null, "signataire": false, "peut_valider": false, "identite_prevue": "lien_seul",
                   "identite_libelle": "accord enregistré via le lien (identité non vérifiée)",
                   "verification_requise": false, "compte_requis": false,
                   "signataire_nom": "Paul Morvan", "signataire_qualite": "Gérant", "signed_at": null}
}
```

Générée (`a_signer` / `signee`) : **même texte et même empreinte pour tous**, annexe complète :

```json
{
  "status": "a_signer", "version": 1,
  "content_md": "# Convention de groupement momentané d'entreprises\n\nVersion n°1 — …",
  "content_hash": "e6bd840f…", "total_offre_ht": 125000.5, "frozen_at": "2026-10-08T01:30:10.964024",
  "membres": [{"membre": "partenaire", "company": "Le Gall Électricité", "role": "cotraitant", "lot": "Lot 2 — Électricité", "prix_lot_ht": 40000.0}],
  "signatures": [{"membre": "mandataire", "company": "Breizh Couverture", "status": "signed", "status_label": "Accord enregistré",
                  "signed_at": "2026-10-08T01:30:11", "identity_level": "compte_verifie",
                  "identity_label": "accord enregistré depuis son compte Adjugo (adresse email vérifiée)",
                  "signataire_nom": "Eliot Viegas", "signataire_qualite": "Président"}],
  "n_signataires": 3, "n_accords": 1, "warning_two_members": false,
  "ma_signature": {"status": "pending", "signataire": true, "peut_valider": true, "identite_prevue": "lien_seul", "…": "…"}
}
```

Caduque (`perimee`) : un membre qui était signataire revoit l'ancien texte (bandeau « plus à jour ») ;
sinon, vue brouillon. `ma_signature.peut_valider` est alors `false`.

Champs de `ma_signature` à utiliser pour l'écran de validation :
- `peut_valider` : afficher le bouton « Valider la convention » ;
- `verification_requise` : d'abord le code reçu par email (routes OTP **existantes**
  `/api/invite/{token}/otp/status|request|verify`), puis valider ;
- `compte_requis` : le lien est rattaché à un compte → « Connectez-vous avec le compte qui a reçu ce
  dossier pour valider » ;
- `identite_libelle` : à afficher sous le bouton (ce qui sera imprimé dans le PDF) ;
- `signataire_nom` / `signataire_qualite` : pré-remplissage (venant de la part du partenaire) ;
- `signataire: false` + `message` : partenaire non signataire (sous-traitant, ou ajouté après génération).

### 4.2 `GET /api/invite/{token}/convention/pdf`

PDF du texte figé + accords (journalisé « Vous avez téléchargé la convention »). 409
`{"code": "pas_generee", …}` tant que la convention n'est pas générée.

### 4.3 `POST /api/invite/{token}/convention/valider`

```json
{"content_hash": "e6bd840f…", "signataire_nom": "Jean Le Gall", "signataire_qualite": "Gérant", "accepte": true}
```

Réponse : même forme que 4.1 (`ma_signature.status: "signed"`). Idempotent. Erreurs :
- 403 `{"code": "identity_unverified", "message": "Vérifiez votre adresse email avant de valider la convention."}` → lancer le flux OTP existant ;
- 403 `{"code": "compte_requis", …}` ; 403 `{"code": "pas_signataire", …}` ;
- 403 « La démo est en lecture guidée… » (lien de la démo) ;
- 409 `{"code": "texte_modifie" | "pas_generee" | "perimee", …}` ; 422 case non cochée / nom manquant.

Quand le dernier accord arrive : `status: "signee"`, email au chef de file « Convention validée par
tous les membres » (règles anti-spam habituelles), notification in-app.

## 5. Ce qui change sur les routes existantes (vague 1)

| Route | Changement |
|---|---|
| `GET /api/projects/{id}/groupement/state` | + `etape`, `etapes[]`, `convention{}`, `pret{}` ; label « Convention à valider » ; filet de péremption avant calcul |
| `GET /api/projects/{id}/consortium` (cockpit) | `state` enrichi (idem) |
| `GET /api/invite/{token}` → `for_member.state` | + `etape`, `etapes`, `convention` (statuts et compteurs seulement) |
| `GET /api/shared` (« Partagé avec moi ») | chaque élément + `groupement: {state, label, index, etape, etapes, convention_status, a_valider}` — badge « Convention à valider » si `a_valider` |
| `GET /api/invite/{token}/journal` | nouvelles entrées : « Le mandataire a généré la convention de groupement » (détail « version n — empreinte … »), « Vous avez validé la convention (accord enregistré) », « Un partenaire a validé la convention (accord enregistré) », « Le mandataire a validé la convention (accord enregistré) », « La convention n'est plus à jour… », « Votre modification a rendu la convention caduque… », « Le mandataire a enregistré l'accord hors ligne d'un partenaire », « Vous avez téléchargé la convention ». Toujours sans IP ni email. |
| `GET /api/notifications` | action `convention.signed` → « a validé la convention de groupement » |
| `POST /api/projects/{id}/offre/figer` | **409** `{"code": "convention_generee"}` si une convention est générée (figer = générer désormais). `DELETE` défige toujours et rend la convention caduque. |
| `GET /api/checklist/{id}` | nouvel item `convention_groupement` « Convention de groupement validée par tous les membres » (`ok` si validée, sinon `manquant` + `context_note` : « Générée : 1/3 accords… », « Plus à jour… », « Brouillon… ») |
| `GET /api/projects/{id}/dossier-preview` | + `convention_groupement.pdf` quand elle est générée |
| `POST /api/sourcing/documents` (dossier) | ZIP : la vraie convention (texte figé + accords) remplace le modèle à compléter ; CERFA alignés ; avertissements « pas encore validée par tous (x/y accords) » / « plus à jour : régénérez-la » / « en brouillon » |
| `POST /api/export/{id}` (ZIP complet) | + `03_Groupement/Convention_de_groupement_v<n>.pdf` ; CERFA alignés ; sommaire « Montant de l'offre commune du groupement » |
| `POST /api/cerfa/{id}/{dc1|dc2|attri1}` | si convention générée : membres = ceux de la convention (sous-traitants gardés pour le DC4), DC1 forme + mandataire solidaire cochés, tableau des membres corrigé (lot, prestations), désignation du mandataire ; DC2 « nom, qualité » du signataire, CA vide si inconnu ; ATTRI1 « l'ensemble des membres s'engagent », montant = total de l'offre commune, répartition conjointe avec prix de vente par membre, mandataire + habilitation (C2), tableau des signataires |

Péremption automatique (aucune action front) : nouvelle invitation, retrait, déclin, part modifiée
ou repassée en brouillon (prix, lot, pièce…), chiffrage du chef de file modifié, défigement, retrait
du plan, partenaire hors ligne détaché, ou toute donnée imprimée modifiée (nom, SIRET, adresse,
représentant…) détectée en recalculant l'empreinte.

## 6. Parcours chef de file (mandataire), étape par étape

1. **Fiche du marché → onglet « Monter le groupement »** (visible dès l'étape 2 du stepper).
   `GET …/convention`. Afficher le stepper 1→5 (`state.etapes`).
2. **Ce que le règlement impose** : `forme_imposee` (libellé + citation entre guillemets, ou « Non
   trouvé dans le DCE »). Bouton « Relire le dossier du marché » → `POST …/relire-dce`.
3. **Forme** : deux grandes cartes « Chacun est responsable de sa part » (petit : Groupement
   conjoint) / « Tous sont responsables de tout » (petit : Groupement solidaire). Si conjoint : case
   « Le chef de file répond aussi de la part de chaque partenaire (mandataire solidaire) ».
   `PUT …/convention {forme, mandataire_solidaire}`. Afficher `avertissements` en bandeau.
4. **Votre part** : montant HT, lot/prestations, qualité du signataire (`params.part_mandataire_ht`,
   `lot_mandataire`, `mandataire_qualite`).
5. **Pouvoirs du chef de file** : cases `options.habilitation` (la première cochée et grisée).
6. **Règles du groupement** : `options.params` repliées par défaut (« Valeurs proposées par Adjugo —
   modifiables »), un contrôle par type (`choix` = boutons radio avec `libelle`, `entier` = champ
   numérique borné avec unité, `oui_non` = interrupteur).
7. **Partenaires hors ligne** (si `candidats_hors_ligne` non vide) : ajouter + prix de vente du lot.
8. **Aperçu** : `apercu_md` (bouton « Télécharger le brouillon » → `/pdf`), option « Masquer la
   répartition dans le brouillon ».
9. **Générer** : si `peut_generer` → bouton « Figer l'offre et générer la convention » (+ texte : « Le
   total de l'offre sera révélé à tous les partenaires. Chacun recevra la convention à valider. »),
   sinon la liste `manques`. `POST …/generer` ; sur 409 `deja_generee` → confirmation → `regenerer: true`.
10. **Suivi des accords** : tableau `signatures` (entreprise, statut, niveau d'identité, date) + compteur
    `n_accords/n_signataires`. Bouton « Valider la convention » pour soi (`POST …/valider`, avec case
    « J'ai lu la convention et je donne mon accord » + `nature_accord`). Pour un partenaire hors ligne :
    « Marquer l'accord comme recueilli » (`POST …/hors-ligne/{link_id}`).
11. **Validée par tous** : `state.pret` → liste des derniers contrôles (attestations, formulaires à
    régénérer) ; boutons vers les formulaires officiels et l'export du dossier.
12. **Caduque** : bandeau « La convention n'est plus à jour (une part, un prix ou la composition a
    changé) » + bouton « Régénérer » (même route).

## 7. Parcours partenaire, étape par étape

1. **Espace du partenaire** (`invite.html` ou « Partagé avec moi », même composant) : stepper
   (`for_member.state.etapes`), badge « Convention à valider » si `groupement.a_valider` (liste) ou
   `ma_signature.peut_valider`.
2. **Brouillon** : « Le chef de file prépare la convention » + forme (terme + phrase), pouvoirs
   (`habilitation`), règles (`params[].valeur_libelle`), répartition avec **son** prix seulement
   (les autres : « affiché à la génération »), aperçu `apercu_md`.
3. **Générée** : texte complet (`content_md` ou PDF), annexe avec tous les prix et le total
   (avertissement si `warning_two_members`), liste des accords. Rappel permanent `avertissement`.
4. **Valider** : nom + qualité pré-remplis, case « J'ai lu la convention et je donne mon accord »,
   `nature_accord` + `identite_libelle` sous le bouton. Si `verification_requise` : code email
   d'abord (flux OTP existant). Si `compte_requis` : se connecter. `POST …/valider` avec le
   `content_hash` affiché ; sur 409 `texte_modifie` → recharger et relire.
5. **Après** : « Accord enregistré le … » ; téléchargement du PDF ; le journal montre l'entrée.
6. **Caduque** : « La convention n'est plus à jour : le chef de file va la régénérer. » (pas de bouton).

## 8. Ce que chaque écran affiche / n'affiche JAMAIS

| Écran | Affiche | N'affiche jamais |
|---|---|---|
| Assistant chef de file (brouillon) | prix de vente de chaque part, total estimé, avertissements, citation du règlement | détail chiffré, coûts, marges (absents de l'API) ; « conseil juridique » ; un pourcentage concurrent |
| Suivi des accords (chef de file) | statut, niveau d'identité, date, nom/qualité une fois l'accord donné | IP, email vérifié des partenaires (non renvoyés) |
| Partenaire — brouillon | forme, pouvoirs, règles, membres + lots, **son** prix | prix des autres membres, part du chef de file, total, score seul du chef de file |
| Partenaire — générée | texte intégral identique pour tous, tous les prix de vente, total, accords | detail_chiffre de quiconque, emails, IP, score seul du chef de file |
| Liste « Partagé avec moi » | étape, statut de convention, « à valider » | tout montant |
| Journal membre | événements de convention en français simple | IP, email, identifiants internes |
| PDF | texte figé, empreinte, version, accords + niveaux d'identité, avertissement | IP, emails, détail chiffré |

Rappels : le LLM ne reçoit jamais la convention ; aucune route ne renvoie `detail_chiffre` au chef de
file ; un partenaire révoqué ou qui a décliné n'est ni dans l'annexe ni signataire, et son lien ne
renvoie plus rien (404/410).
