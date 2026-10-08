# Co-traitance v2 — architecture cible (06/10/2026)

> Produit par 6 architectes ancrés dans le code + 1 challenger adversarial + 1 synthèse. Décisions du fondateur figées : étapes 1→5, innovations A→E, doctrine de visibilité, chiffrement par membre, vrai réseau, 2 expériences. **GO vague 1 donné le 06/10/2026.**

## Statut vague 1 (07/10/2026)

**Backend livré, relu, 130 tests verts** (suite complète + `test_groupement_scoring`, `test_citation_guard`, `test_groupement_routes`, `test_cotraitance_v2_doctrine`, `test_cotraitance_v2_review`).

- Migration `n8o9p0q1r2s3` (idempotente, testée fresh / re-run / données) : la fuite `chiffrage_note` est déplacée en tête de `note_au_mandataire` préfixée « (ancienne approche prix) », colonne vidée (supprimée en vague 4). Jamais de troncature (colonne Text).
- `app/services/groupement_members.py` : membre = invitation active (`revoked=False ET declined_at IS NULL`) ; `groupement_state()` dérive les 8 états (un plan calculé automatiquement à l'analyse = « potentiel », « composition » seulement si retenue par le mandataire).
- `app/services/groupement_scoring.py` (pur, 0 LLM) + `citation_guard` dans `analysis.py` (extraits littéraux vérifiés contre le DCE intégral, sinon vidés).
- `app/services/groupement_verdict.py` + `app/routers/groupement.py` : `/besoins`, `/simulate`, `/retenir`, `/state`, `/simulations`, `DELETE /plan` ; hooks dans `/analyze`, `/analyze-upload`, `/reanalyze` (3e verdict `go_groupement`, `match_score` = seul, jamais gonflé).
- `app/routers/invites.py` : doctrine (`prix_lot_ht` clair, `detail_chiffre` enveloppe chiffrée jamais sérialisée côté mandataire), déclin, journal membre (projection sans ip/email), coffre-fort croisé (statuts seulement), figer / défiger l'offre, vue « pourquoi vous ».
- `app/static/cotraitance-crypto.js` (WebCrypto PBKDF2 600k → AES-256-GCM, code de récupération 24 caractères, copie du code sur demande explicite) ; page sécurité §4 = tableau « qui voit quoi » + limites honnêtes.
- Vitrine démo : Lorient « seul 43 → avec Breizh Désamiantage 100 » calculé par le vrai service (jamais codé en dur).

**Relecture adversariale (lecture seule) → corrigé :** score seul recalculé ≠ score d'analyse (qualifications `{name, detail}` tronquées) ; découverte SIRENE bornée (limit 4, sans enrichissement DECP par entreprise) ; `verify_chain` mis en cache 5 min sur la route invitée (DoS) ; synchronisation de l'annuaire uniquement via un partenaire RATTACHÉ au projet (jamais par nom : fausse provenance) ; figer exige la part du mandataire ; nouvelle invitation / nouveau chiffrage mandataire / changement de composition défigent AVEC trace `offer.unfrozen` (une revue du chiffrage ne défige pas) ; limites de débit sur toutes les routes ; `invite.claimed` sans email ; pas d'appariement par nom à la rétention.

**Reste (vague 1) :** front espace mandataire (`app.html`/`app.js`) et espace co-traitant (`invite.html`) — en cours ; vérification navigateur des deux expériences ; déploiement après feu vert du fondateur (migration de données en production).

## Statut vague 2 (08/10/2026) — partie serveur

**En production depuis le 8 octobre 2026** (migration `o9p0q1r2s3t4` appliquée sur Postgres, écrans chef de file + partenaire, 416 tests). Règles ajoutées après relecture : « figer » (vague 1) refusé dès qu'une convention existe (seule la génération fige l'offre) ; un non-signataire (sous-traitant) ne reçoit ni le texte, ni l'annexe, ni le total ; une convention caduque ne renvoie jamais les prix courants. Valeurs par défaut des paramètres et texte du modèle : à valider par Eliot et à faire relire par un conseil.

**Backend livré sur une branche de worktree (non déployé), 335 tests verts (3.14 et 3.12).** Contrat
d'API pour le front : `docs/COTRAITANCE_V2_VAGUE2_API.md`.

- Migration `o9p0q1r2s3t4` (idempotente, testée à neuf / rejouée / base à la révision précédente) :
  `groupement_conventions` (project_id UNIQUE, content_hash UNIQUE) et `groupement_signatures`
  (UNIQUE(convention_id, invite_id), UNIQUE(convention_id, cotraitant_link_id)).
- `app/services/groupement_convention.py` : modèle paramétré déterministe (0 LLM, empreinte sha256
  unique, aucune date dans le texte), ce que le règlement impose (citation vérifiée par
  `citation_guard`, sinon « non trouvé dans le DCE » ; relecture du dossier sans interprétation),
  avertissements (avertir, pas bloquer), péremption explicite + filet par recalcul d'empreinte,
  accords, PDF (valeurs échappées), données des CERFA.
- `app/routers/convention.py` : assistant / brouillon / relecture / génération (= figer l'offre) /
  accord du mandataire / accord hors ligne / PDF ; côté partenaire : vue, PDF, accord via le gate
  d'identité existant (`_binding_required` + OTP) ou le compte après claim ; niveau d'identité stocké
  et imprimé. Démo bloquée (garde central + liens démo).
- Cohérence : DC1 (forme, mandataire solidaire, tableau des membres corrigé, désignation du
  mandataire), DC2 (nom + qualité du signataire, CA vide si inconnu), ATTRI1 (engagement du
  groupement, total de l'offre commune, répartition conjointe avec prix de vente, habilitation C2,
  signataires) ; convention dans le ZIP, le dossier, l'aperçu du dossier ; item de checklist.
- `groupement_state()` : `etape`/`etapes` (stepper 1→5), `convention`, `pret` (état 7 = convention
  validée + attestations + CERFA régénérés après la convention).
- RGPD / organisation : nouvelles tables dans l'export, l'effacement, la purge de corbeille et le
  transfert de propriété.

**Reste (vague 2) :** front mandataire (`app.html`/`app.js`) et partenaire (`invite.html` + vue
« Partagé avec moi ») à partir du contrat ; relecture du modèle de convention par un conseil ;
validation par le fondateur des valeurs par défaut et des libellés juridiques ; déploiement.

## Statut vague 3 (08/10/2026) — partie serveur

**Backend livré sur une branche de worktree (non déployé), 440 tests verts (Python 3.12, versions de
production), migration et parcours rejoués sur Postgres 16.** Contrat d'API pour le front :
`docs/COTRAITANCE_V2_VAGUE3_API.md`.

- Migration `p0q1r2s3t4u5` (idempotente, testée à neuf / base à `o9p0q1r2s3t4` sans la table /
  rejouée, SQLite et Postgres) : `partner_profiles` conforme au modèle ci-dessous (opt-in :
  `visible` = false par défaut) + `public_id` opaque (UNIQUE, anti-énumération), `references_publiques`
  (références choisies par l'entreprise), `declared_at` (date des capacités déclarées), `published_at`.
- `app/services/partner_matching.py` (PUR, 0 LLM) : classement 35/25/15/15/10 → **rang + critères
  sourcés et datés, jamais de total ni de %** ; badges et capacités avec source et date ; fiche
  publique = sous-ensemble strict. `app/services/partner_network.py` : vérifications SIRENE / BODACC /
  DECP tri-état (une erreur réseau = « non vérifié », ne remplace jamais une vérification réussie),
  visibilité (réciprocité, `hidden_from_sirens` dans les deux sens, aucun profil démo), compteur
  anonyme d'apparitions, historique COUNT, RGPD, cron borné.
- `app/routers/reseau.py` : profil (GET pré-rempli Company + `lookup_company` / PUT / DELETE),
  vérifier, publier (admin, SIRET 14 chiffres, SIRENE actif < 30 j, un seul profil publié par SIREN),
  retirer ; annuaire + fiche ; historique ; invitations reçues ; `partner-matches` (≤ 3 lots SIRENE par
  appel, cache 10 min, 60/h + plafond par organisation) ; mise en relation en 1 clic
  (`_create_invite` factorisé sans changer POST /invites ; adresse remplie côté serveur et masquée au
  chef de file jusqu'à la réponse ; lien jamais remis ; 409 si déjà invité ; annuaire rattaché) ;
  invitation SIRENE hors réseau (lien à transmettre). Cron `POST /api/admin/run-partner-network`.
- Pool `reseau` branché dans le score de groupement : `/simulate` (`kind: 'reseau'`, profil relu
  côté serveur, CA/effectif inconnus) et `/besoins` (`candidats.reseau`, ordre du classement B).
- Invitation réseau pas encore acceptée : aperçu minimal côté partenaire (ni acheteur, ni pièces,
  ni composition du groupement). Boucle de croissance : `suggest_profile` après inscription et claim
  (suggestion d'interface, aucun email).
- Écart assumé avec le plan initial : **aucun profil `is_demo` n'est créé** (démo publique supprimée,
  règle anti-hallucination) ; la colonne est conservée et toujours filtrée.

**Écrans (08/10/2026, même branche, non déployés)** — `app.html`, `app.js`, `styles.css`, `invite.html` :
entrée « Réseau » (Mon profil partenaire · Annuaire · Mon historique · Invitations reçues), panneau
« Partenaires pour ce marché » sur la fiche du marché (bouton « Qui me complète ? », lot par lot, rang +
critères + badges sourcés et datés, repli SIRENE, « Simuler le groupement » = seul %), modale
d'invitation en 1 clic (adresse jamais affichée, 409 « déjà invité » / « sur le réseau » gérés), statut
« a décliné » sur les cartes, la composition retenue et les candidats, source et adresse masquée dans
la liste des invitations, suggestion « publiez votre profil » après inscription et acceptation, aperçu
minimal dans `invite.html`. Garde-fous : `tests/test_reseau_ecrans.py`. Détail : § 13 du contrat.

**Reste (vague 3) :** cron hebdomadaire à ajouter dans Railway ; validation par le fondateur des
choix listés dans le contrat (poids du classement, aperçu minimal, plafonds) et des choix d'écran
(§ 13 du contrat).

## Statut vague 4 (08/10/2026) — partie serveur

**Backend livré sur une branche de worktree (non déployé), 439 tests verts (3.12, versions de
production) ; tests de la vague rejoués sur Postgres 16.** Contrat d'API pour le front :
`docs/COTRAITANCE_V2_VAGUE4_API.md`. Hors périmètre (vague 3 en parallèle) : fiche partenaire de
l'annuaire, historique réseau.

- Journal vérifiable par chaque membre (`app/services/journal_membre.py`, `app/routers/journal_membre.py`) :
  `GET /api/invite/{token}/journal/integrity` et `/api/shared/{project_id}/journal/integrity`
  recalculent la sous-chaîne (empreinte + lien au maillon précédent) et citent la date du dernier
  ancrage horodaté ; exports JSON / PDF ; vérification hors ligne par sceaux (sha256 à sens unique
  de l'empreinte, pour ne jamais exposer de quoi retrouver une IP) et maillons propres au membre.
  Libellé : « Journal vérifiable : toute modification ou suppression d'entrée est détectable ».
- SRI : `integrity="sha384-…"` sur les `<script src="/static/…">`, manifeste publié
  (`/static/sri-manifest.json`, `GET /api/securite/empreintes-scripts`), test + `scripts/sri_update.py`,
  correction à la volée en production. CSP inchangée (piste de durcissement documentée).
- DPGF de lot : pièce `dpgf_lot` (CSV contrôlé : formules et colonnes de coûts/marges refusées),
  visible du chef de file seulement, part et convention intactes.
- Étape 5 : `depot_readiness` (4 contrôles fiables, dont les parts), `GET /groupement/depot`,
  `POST/DELETE /groupement/deposer` (journal, avertir puis confirmer) ; relances sans doublon
  (un palier = une alerte, un seul email part + attestations, récapitulatif unique au chef de
  file, rien après dépôt) ; tableau de bord `GET /api/groupement/tableau-de-bord`.
- Migration `q1r2s3t4u5v6` (à rechaîner après la vague 3) : suppression de `chiffrage_note`.
- Correctif transverse : `audit_logs.created_at` écrit en UTC naïf (sur une base Postgres réglée
  hors UTC, toute la chaîne semblait altérée à la relecture).

**Écrans livrés (même branche, non déployés)** — détail : `docs/COTRAITANCE_V2_VAGUE4_API.md` § 11 :
« Vérifier mon journal » + exports (page partenaire et « Partagé avec moi »), « Ma DPGF de lot »
produite dans le navigateur (lignes rangées dans le détail chiffré, route
`PUT /api/invite/{token}/contribution/detail` qui ne touche ni la part soumise ni la convention),
« Avant de déposer » en « N contrôles sur 4 » + « Marquer déposé » / « Retirer le marquage »,
carte du tableau de bord (marchés accessibles en groupement, étapes 1→5).

**Reste (vague 4) :** texte de la page sécurité, point cyber (revue externe du schéma de
chiffrement et du journal, différée par le fondateur), déploiement.

## Vision en une phrase

Adjugo devient le seul outil où une PME voit en un coup d'œil « seul 54 % → avec Le Gall Électricité 81 % », monte le groupement en cinq minutes (convention générée, signée par chacun depuis son espace) et répond à plusieurs sans que personne — ni le mandataire, ni le serveur Adjugo, ni l'IA — ne voie jamais autre chose que le prix de vente de chaque lot et le total de l'offre commune.

## Machine à états du groupement (dérivée, jamais stockée)

- 1. seul — marché analysé, verdict seul (go / a_etudier / no_go), aucune simulation retenue ; déclencheur de sortie : auto_alliance pose go_groupement ou détecte des manques (A)
- 2. potentiel — « Bon potentiel en groupement » ou manques listés (« le marché exige X que vous n'avez pas ») ; aucune composition retenue ; sortie : POST /groupement/retenir
- 3. composition — simulation retenue, partenaires rattachés (ProjectCotraitant.invite_id NULL = candidats) ; sortie : invitations créées (lien magique / réseau) ; retour en 2 si tous retirés
- 4. invitation — ≥ 1 invitation active (revoked=false, declined_at NULL) ; sous-état par membre : invitée → a consulté → part soumise | a décliné (déclin ⇒ le membre sort, retour en 3 si plus aucun actif) ; capacités déclarées par le membre relancent la simulation
- 5. parts_completes — toutes les parts actives soumises avec prix_lot_ht renseigné ; le mandataire voit les prix de lot, les membres ne voient pas encore le total ; sortie : « Figer l'offre et générer la convention »
- 6. convention_a_signer — total_offre_ht figé et révélé à tous les membres, convention générée (content_hash unique, annexe de répartition visible par tous les signataires), signatures en attente depuis chaque espace ; toute part modifiée après génération ⇒ convention 'perimee' → retour en 5
- 7. pret_a_deposer — convention signée par tous (ou hors_ligne coché), grille du coffre croisé entièrement verte à la date limite (aucune attestation manquante ni expirant avant), CERFA DC1/DC2/ATTRI1 générés ; % prêt = 100
- 8. depose — project.status = envoye (puis gagne/perdu, hors périmètre) ; composition figée, groupements_deposes des profils réseau incrémenté, journal clos. ÉTAT DÉRIVÉ par groupement_state(project, db), jamais stocké.

## Modèle de données consolidé

### `projects` — modifiée (migration n8o9p0q1r2s3)

groupement_score INTEGER NULL (score cumulé ; match_score reste le score SEUL, jamais gonflé) ; groupement_plan JSON NULL {members:[{kind, id, invite_id, name, siret, apporte[]}], breakdown, gaps, warnings, offre:{total_ht, frozen_at, convention_id}, computed_at} ; go_decision String(20) existant accepte 'go_groupement' (pas de schéma). PAS de colonne d'état : l'étape du groupement est DÉRIVÉE par un service unique groupement_state(project, db) (une seule source de vérité, rien à resynchroniser).

*Sert à :* A (3e verdict, pastille « seul → avec X »), C (offre figée), machine à états (stepper 1→5), dashboard « N marchés accessibles en groupement »

### `groupement_simulations` — nouvelle

id ; project_id FK idx ; owner_id FK users idx (= data_owner_id) ; created_by_user_id ; members JSON [{kind:'lead'|'attached'|'annuaire'|'reseau'|'sirene'|'saisi', id, name, siret, source, as_of}] — pour kind 'sirene' le serveur ne conserve que le SIRET et RE-FETCH via registre.lookup_company (toute capacité envoyée par le client est ignorée) ; 'saisi' = étiquette « déclaré par vous le … » ; score_seul INT ; score_groupement INT ; decision String(20) ; breakdown JSON (6 critères × {points,status,detail,apporte_par[]}) ; cumul JSON ; gaps JSON ; warnings JSON ; retained BOOL default false ; created_at

*Sert à :* A (what-if, historique « pourquoi GO en groupement »), C (membres pré-remplis de la convention), journal D (groupement.simulate / groupement.retenue)

### `cotraitants (annuaire « Mes partenaires »)` — modifiée

+ references JSON default [] ; + capacites_source String(20) default 'declare' ('declare'|'rne'|'contribution'|'reseau') ; + capacites_updated_at DateTime NULL. Colonnes existantes (ca_n1, effectif, qualifications String, departement, specialites, siret) réutilisées telles quelles.

*Sert à :* A (capacités étiquetées « déclaré par vous le … » vs « vérifié SIRENE » vs « déclaré par le partenaire »), B (badge « déjà dans vos partenaires » par siret)

### `project_cotraitants (rattachement au marché)` — modifiée

+ invite_id Integer FK project_invites NULL idx (posé quand l'invitation est créée → le rattachement devient une CANDIDATURE, l'invitation active devient LE membre) ; source existant accepte 'reseau_adjugo' | 'discover' | 'reseau' | 'simulation'. UNIFICATION : « membre du groupement » = invitation active (revoked=false ET declined_at IS NULL) + le mandataire ; un ProjectCotraitant sans invite_id = candidat retenu, pas membre.

*Sert à :* Résout les 4 notions de membre (Cotraitant / ProjectCotraitant / ProjectInvite+Contribution / partner_profile) : checklist, cockpit, cerfa, redaction, convention et signatures lisent tous active_invites(project_id)

### `project_invites` — modifiée

+ declined_at DateTime NULL (traité EXACTEMENT comme revoked partout via helper active_invites) ; + source String(20) default 'manuel' ('manuel'|'reseau_adjugo'|'sirene') ; + partner_profile_id FK partner_profiles NULL idx. recipient (email) rempli côté serveur pour 'reseau_adjugo' et JAMAIS sérialisé/journalisé tant que accepted_by_user_id est null. Gate d'identité (_binding_required/OTP/claim) INCHANGÉ.

*Sert à :* B (mise en relation 1-clic, déclin), C (signature depuis le lien), D (journal membre indexé par invite)

### `project_contributions` — modifiée

+ prix_lot_ht Float NULL (PRIX DE VENTE du lot — le seul montant que voit le mandataire) ; + detail_chiffre JSON NULL (enveloppe chiffrée {ciphertext, iv, alg:'A256GCM', kdf:'PBKDF2-SHA256', kdf_salt, kdf_iter, key_fingerprint, updated_at} — décomposition/coûts/marges/méthode, illisible côté serveur) ; + representant_legal String(255) ; + signataire_qualite String(120) ; + capacites JSON NULL {ca_n1, effectif, declared_at} (déclaré par le partenaire → alimente A avec capacites_source='contribution') ; chiffrage_note DÉPRÉCIÉ : retiré de _serialize_contribution côté owner, du PDF consortium_report, du dict build_dossier et de has_chiffrage ; migration : contenu existant déplacé en tête de note_au_mandataire avec le préfixe « (ancienne approche prix) », colonne vidée, supprimée en vague 4.

*Sert à :* Doctrine de visibilité (prix de lot clair / détail chiffré), C (annexe de répartition, signataire DC2), A (capacités déclarées par le partenaire lui-même)

### `contribution_pieces` — modifiée

+ piece_type String(20) default '' (kbis|fiscale|sociale|assurance|rib|qualification|autre — pré-classé par _classify_partner_pieces existant, modifiable par le déposant) ; + expiration_date Date NULL (saisie par le déposant ou copiée du Document source) ; + source_document_id Integer NULL (Document.id du coffre-fort PERSONNEL du partenaire quand il « joint depuis mon coffre-fort » : copie du fichier dans le tenant mandataire, le Document d'origine n'est jamais exposé).

*Sert à :* E (coffre croisé : grille membres × pièces en STATUT seulement — présent / valide jusqu'au / expire avant la date limite / manquant — visible par tous les membres ; fichier téléchargeable uniquement par son déposant et par le mandataire, audité)

### `groupement_conventions` — nouvelle

id ; project_id FK UNIQUE ; owner_id FK idx ; forme String(12) ''|'conjoint'|'solidaire' ; mandataire_solidaire BOOL ; forme_imposee String(16) 'non_verifie'|'non_specifie'|'libre'|'conjoint'|'solidaire' ; forme_imposee_extrait Text (passé par citation_guard : sous-chaîne du DCE intégral sinon vidé) ; habilitation JSON ; params JSON (decision, delai_reponse_jours, defaillance, sortie_preavis_jours, confidentialite_annees, pi, penalites, assurances_travaux, litiges) ; status 'draft'|'a_signer'|'signee'|'perimee' ; content_md Text (texte figé, annexe de répartition INCLUSE : nom, lot, rôle, prix_lot_ht par membre, total — jamais la décomposition) ; content_hash sha256 UNIQUE pour tous les signataires ; total_offre_ht Float ; version INT ; frozen_at ; created_at, updated_at. L'option « masquer la répartition » n'existe qu'en brouillon.

*Sert à :* C (étape 3) : convention générée par modèle paramétré déterministe (0 LLM), cohérente avec DC1/DC2/ATTRI1 ; figer l'offre = révéler le total aux membres

### `groupement_signatures` — nouvelle

id ; convention_id FK idx ; project_id ; owner_id ; invite_id FK NULL (NULL = mandataire) ; cotraitant_link_id FK project_cotraitants NULL (membre rattaché sans invitation → status 'hors_ligne' coché par le mandataire) ; user_id NULL ; company_name ; siret ; signataire_nom ; signataire_qualite ; content_hash (hash du texte approuvé = celui de la convention) ; identity_level 'compte_verifie'|'email_verifie'|'lien_seul' (imprimé dans le PDF : « accord enregistré via le lien (identité non vérifiée) » en lien_seul) ; status 'pending'|'signed'|'perimee'|'hors_ligne' ; verified_email ; signed_at ; ip ; UNIQUE(convention_id, invite_id), UNIQUE(convention_id, cotraitant_link_id)

*Sert à :* C : validation depuis l'espace de chaque membre via le gate existant (_binding_required) sans survendre une « signature électronique »

### `partner_profiles` — nouvelle (vague 3)

id ; user_id FK UNIQUE (= data_owner_id : 1 profil par organisation) ; visible BOOL default false ; name ; siren idx ; siret ; postal_code ; city ; departement ; metiers JSON (clés TRADES) ; codes_cpv JSON ; departements JSON ; roles_acceptes JSON ; disponibilite ; dispo_jusqua ; lot_max_eur ; presentation String(300) (UI : « présentation en une phrase », pas « pitch ») ; hidden_from_sirens JSON ; verified_sirene JSON {etat, date_creation, categorie, est_rge, est_qualiopi, est_personne_physique, checked_at, source} ; verified_bodacc JSON {found, ongoing, nature, date, url, checked_at} (None = « non vérifié », absence = « aucun avis trouvé au JJ/MM ») ; verified_decp JSON {count, last_date, checked_at} (« au moins N ») ; verified_at ; groupements_deposes INT (COUNT recalculé, jamais saisi) ; last_groupement_at ; appearances_count INT + appearances_period String(7) ; is_demo BOOL ; created_at, updated_at. Fiche publique = sous-ensemble strict, jamais email/téléphone/CA/effectif exact/références/documents/résultats.

*Sert à :* B (étape 2) : réseau opt-in vérifié, matching par lot, mise en relation 1-clic ; pool 'reseau' du simulateur A

### `audit_logs` — modifiée

+ invite_id Integer NULL idx (l'invitation concernée par l'entrée → projection membre = simple filtre). Nouvelles actions : owner.view_contribution / owner.view_piece (dédoublonnées par heure), owner.freeze_offer, groupement.simulate / groupement.retenue, convention.generated / convention.signed, invite.declined, piece.expiring, network.* (tenant du chercheur uniquement). Règle : actor = company_name (jamais l'email) pour tout invité, à partir de la vague 1.

*Sert à :* D : journal « qui a vu quoi » visible par chaque membre (projection sans ip ni email), chaîne de hash existante conservée

### `projects.ai_analysis (JSON, sans migration)` — modifiée

details.references_requises, effectif_minimum_requis, capacites_groupement, forme_groupement{imposee, extrait}, exigences_sources{ca_minimum_requis, qualifications_requises, references_requises, effectif_minimum_requis, capacites_groupement} ; CHAQUE extrait passe par citation_guard(text_integral, extrait) : normalisé et sous-chaîne du DCE intégral sinon '' (jamais affiché) ; _RISK_TERMS étendu (groupement, conjoint, solidaire, mandataire, chiffre d'affaires, capacit, référence, effectif) pour que la clause entre dans la fenêtre LLM ; 'Non specifie dans le DCE' ⇒ ni critère ni manque.

*Sert à :* A (citations au survol, zéro exigence inventée), C (forme imposée)

## Matrice de visibilité (qui voit quoi)

| Donnée | Mandataire | Co-traitant | Serveur Adjugo | LLM |
|---|---|---|---|---|
| Prix de vente du lot d'un membre (prix_lot_ht) | OUI (nécessaire pour consolider et remplir l'ATTRI1) | le sien OUI ; ceux des autres NON en brouillon, OUI après génération de la convention (annexe de répartition signée par tous — exigé en groupement conjoint) | en clair | JAMAIS |
| Décomposition, coûts, marges, méthode de chiffrage (detail_chiffre) | JAMAIS | le sien seulement (déchiffré dans son navigateur) | enveloppe chiffrée AES-256-GCM uniquement (clé jamais stockée, seul key_fingerprint) | JAMAIS (impossible techniquement) |
| Prix total de l'offre commune | OUI dès que calculable | OUI après « Figer l'offre » ; avertissement affiché : à 2 membres, le total révèle la part de l'autre | en clair (groupement_plan.offre) | NON |
| Paragraphe de mémoire technique d'un membre | OUI | le sien seulement | en clair | OUI (fusion existante, tenant_scope du mandataire) |
| Références, qualifications, CA/effectif déclarés par un membre | OUI (DC2, simulation) avec étiquette « déclaré par le partenaire le … » | les siens ; pour les autres : booléens seulement (« CA cumulé ✓ », « Qualifications ✓ »), jamais les chiffres | en clair | références OUI (mémoire) ; CA/effectif NON |
| Pièces administratives d'un membre (fichier) | OUI (téléchargement nécessaire au dépôt, audité owner.view_piece) | les siennes seulement | stockage tenant mandataire | JAMAIS |
| Statut des attestations de chaque membre (présent / valide jusqu'au / expire avant la date limite / manquant) | OUI | OUI pour tous les membres (grille du coffre croisé, statut seulement, jamais le fichier) | dérivé (piece_type, expiration_date) | NON |
| Coffre-fort personnel du partenaire (Document de son tenant) | JAMAIS (seule la copie que le partenaire choisit de joindre) | le sien | tenant du partenaire | NON |
| Score de groupement (%) et apports par membre | OUI complet (seul → avec X, 2 colonnes, apporte_par) | score commun + SON apport + booléens de seuils ; jamais le score seul du mandataire | calcul pur (score_dce réappliqué) | NON (0 LLM) |
| Analyse interne du mandataire (résumé, verdict seul, risques, ai_analysis) | OUI | JAMAIS (_invite_public bridé existant : objet, lots, critères, échéance) | en clair | OUI (analyse, tenant mandataire) |
| Liste des membres (nom d'entreprise, lot, rôle) | OUI | OUI | en clair | OUI (DC1) |
| Email, IP, jeton des membres | email d'un invité manuel OUI (il l'a saisi) ; email d'un partenaire réseau MASQUÉ tant qu'il n'a pas répondu ; IP : journal tenant | JAMAIS ceux des autres | en clair (sécurité) | JAMAIS |
| Journal « qui a vu quoi » | complet pour son tenant (existant) | projection : entrées où invite_id = le sien + événements de groupement (convention générée/signée, offre figée, simulation retenue) ; acteur = « le mandataire » / nom d'entreprise ; SANS ip, SANS email | chaîne de hash par tenant (existant) ; vague 4 : sous-chaîne vérifiable par le membre | NON |
| Convention de groupement (texte + annexe de répartition) | OUI | OUI, texte identique pour tous (un seul content_hash) | en clair | JAMAIS (modèle paramétré déterministe) |
| Documents du marché (DCE) partagés | OUI | OUI si can_view_docs (existant) | tenant mandataire | OUI (analyse) |
| Recherches réseau (qui cherche qui) | voit ses résultats | ne sait JAMAIS qu'il a été cherché ; compteur mensuel anonyme d'apparitions | audit network.match_query sur le tenant du chercheur uniquement | NON |
| Clé de chiffrement du membre | JAMAIS | navigateur (IndexedDB) + code de récupération affiché une fois | JAMAIS (seulement sel KDF + fingerprint) | JAMAIS |

## Schéma de chiffrement (honnête)

Chiffrement PAR MEMBRE ET PAR MARCHÉ, dans le navigateur, du seul champ detail_chiffre de ProjectContribution (décomposition, coûts, marges, méthode). Mécanique : WebCrypto natif (aucune lib) — à la première saisie, le navigateur génère un code de récupération de 24 caractères (base32, affiché UNE fois, à noter) ; clé = PBKDF2-SHA256(code, kdf_salt 16 o aléatoire, 600 000 itérations) → AES-256-GCM 256 bits (Argon2 n'est pas natif WebCrypto : on ne charge pas de WASM depuis un CDN pour ça) ; clé mise en cache en IndexedDB du navigateur (non exportable) ; chaque sauvegarde produit {ciphertext, iv 12 o neuf, alg:'A256GCM', kdf:'PBKDF2-SHA256', kdf_salt, kdf_iter, key_fingerprint = sha256(clé publique dérivée tronquée), updated_at} envoyé tel quel ; le serveur stocke l'enveloppe, vérifie seulement sa forme, ne possède ni le code ni la clé. Le prix de vente du lot (prix_lot_ht) reste EN CLAIR : c'est la donnée que le mandataire doit voir. Invité par lien magique (sans compte) : la clé vit dans SON navigateur ; autre poste = ressaisie du code de récupération ; code perdu = détail définitivement perdu (écrit noir sur blanc dans l'UI et dans la page sécurité). Conséquences produit assumées : le détail chiffré n'alimente JAMAIS le LLM ni une DPGF commune — chaque membre produit la DPGF de son lot localement (déchiffrement navigateur, vague 4) et la dépose comme pièce visible du mandataire (prix unitaires = niveau prix de vente, sans coûts ni marges). LIMITES HONNÊTES : (1) ce n'est PAS du zero-knowledge — Adjugo sert le JavaScript (app.js, invite.html, Vue via CDN) ; un serveur compromis pourrait livrer un script exfiltrant la clé ; formulation retenue partout : « chiffré dans votre navigateur avec une clé qu'Adjugo ne stocke pas », jamais « Adjugo ne peut pas le lire » sans cette précision ; mitigations cheap en vague 4 : SRI sur les scripts CDN, CSP stricte, hash des scripts publié sur la page sécurité ; (2) le mandataire et les autres membres déduisent le prix de lot de chacun à la génération de la convention (annexe de répartition, exigée par l'ATTRI1 en conjoint) et, à 2 membres, le total révèle la part de l'autre : la doctrine le prévoit (prix de vente visible), l'UI le dit ; (3) la protection porte sur coûts/marges/méthodes, pas sur le prix de vente ; (4) PBKDF2 600k itérations ≈ 0,5-1 s sur mobile : acceptable, exécuté une fois par navigateur ; (5) pas de partage de clé entre deux personnes de la même PME invitée sans ressaisir le code (limite assumée, pas de gestion de clés serveur).

## Vagues de livraison

### Vague 1 — « Répondre à plusieurs ? » : score de groupement + doctrine de visibilité + coffre croisé

**Objectif.** Dès cette vague, l'utilisateur voit « Seul 54 % → avec Le Gall Électricité 81 % », sait ce que le marché exige qu'il n'a pas et qui l'a (preuves datées), et le cloisonnement est enfin CONFORME à la doctrine : le mandataire ne voit plus jamais l'approche prix d'un partenaire, chaque membre a son journal, et tout le monde voit le statut des attestations de tous sans voir les fichiers.

- citation_guard(text_integral, extrait) unique + SYSTEM_PROMPT enrichi (references_requises, effectif_minimum_requis, capacites_groupement, forme_groupement, exigences_sources) + _RISK_TERMS étendus ; citations affichées au survol, '' si non vérifiable
- app/services/groupement_scoring.py PUR (member_capacities, cumulate, score_groupement = score_dce sur l'entreprise virtuelle, gaps, auto_alliance glouton ≤ 4 membres) + tests déterministes (idempotence, CA inconnu = 0, « chaque membre » annule le cumul, jamais go_groupement sans partenaire réel)
- Accroche /analyze, /analyze-upload, /reanalyze ; 3e verdict go_groupement (sourcing._verdict, decLabel/decColor) ; colonnes projects.groupement_score/plan ; pastille « Bon potentiel en groupement · 81 % » (pipeline + fiche marché) ; grep des usages go_decision=='go' (dashboard, rgpd, filtres, demo_seed) adaptés
- GET /groupement/besoins + filtre gap sur /api/sourcing/cotraitants + panneau « Ce que le marché exige et que vous n'avez pas → Trouver qui l'a » (rattachés → Mes partenaires → SIRENE re-fetché côté serveur, preuves {source, as_of}, « CA non publié — à demander », « à confirmer auprès du partenaire » pour Qualibat/SS3) ; warning proéminent si le verdict repose sur des capacités déclarées par vous
- POST /groupement/simulate (kind 'sirene' = SIRET re-fetché, 'saisi' étiqueté) + table groupement_simulations + /retenir (attach existant, source 'simulation') + UI chips / 2 colonnes Seul | En groupement ; annuaire : references, capacites_source, capacites_updated_at
- DOCTRINE : prix_lot_ht (clair) + detail_chiffre (enveloppe chiffrée, WebCrypto dans invite.html et app.js, code de récupération) ; chiffrage_note retiré de _serialize_contribution owner, du PDF consortium_report, de build_dossier et de has_chiffrage ; migration de l'existant vers note_au_mandataire préfixée ; « Figer l'offre » minimal (groupement_plan.offre.total_ht/frozen_at) → le total apparaît aux membres seulement après, avec l'avertissement « à 2 membres »
- active_invites(project_id) (revoked OR declined_at) utilisé PARTOUT (checklist._is_groupement, cockpit, my_consortiums, cerfa, redaction, report) + POST /api/invite/{token}/decline + statut « a décliné » ; project_cotraitants.invite_id
- JOURNAL MEMBRE : audit_logs.invite_id ; owner.view_contribution / owner.view_piece dédoublonnés par heure ; actor = company_name pour tout invité ; GET /api/invite/{token}/journal et /api/shared/{id}/journal = projection (ses entrées + événements de groupement, « le mandataire » comme acteur, sans ip/email) ; libellé « journal infalsifiable tenu par Adjugo »
- COFFRE CROISÉ v1 : contribution_pieces.piece_type / expiration_date / source_document_id ; grille membres × pièces (statut seulement) dans le cockpit ET dans l'espace de chaque membre ; « Joindre depuis mon coffre-fort » pour le partenaire avec compte (copie, Document d'origine jamais exposé) ; alertes « attestation manquante / expirant avant la date limite » aux paliers J-7 / J-3 via run-cotraitance-reminders existant
- Vue co-traitant « Pourquoi vous dans ce groupement » (projection for_member dans /api/shared et invite.html) + bloc « Vos capacités pour ce marché » (capacites JSON, capacites_source='contribution') + notification in-app au mandataire « X a mis à jour ses capacités »

**Effort :** L — environ 3 semaines (A est un L, pas un M : scoring pur 3 j, accroche/verdict 2 j, besoins/candidats 3 j, simulateur 3 j, doctrine + crypto navigateur 3 j, journal 2 j, coffre croisé 3 j, vue co-traitant 1 j)  
**Valeur client :** Très haute : c'est la promesse « Consortium as a Service » rendue visible (le % en groupement) et crédible (cloisonnement réellement conforme, journal pour chaque membre, attestations des partenaires surveillées avant dépôt). Démontrable en vitrine dès la fin de la vague.  
**Dépendances :** Aucune externe. Migration n8o9p0q1r2s3 idempotente (revises m7n8o9p0q1r2). Les projets déjà analysés restent « inconnu » jusqu'à ré-analyse (bouton existant). B non requis : pool = rattachés + annuaire + SIRENE.

### Vague 2 — Monter le groupement : assistant juridique et convention signée depuis chaque espace (C)

**Objectif.** Le mandataire choisit « chacun responsable de sa part » ou « tous responsables de tout » (avec ce que le règlement impose, cité), obtient une convention prête à relire, chaque membre la valide depuis son espace ; DC1/DC2/ATTRI1/convention disent partout la même chose.

- Tables groupement_conventions + groupement_signatures (migration) ; extraction forme imposée via citation_guard (déjà en place depuis la vague 1)
- Assistant conjoint / solidaire : termes légaux TOUJOURS accompagnés de la phrase simple, « ce que le règlement impose » cité ou « non précisé », habilitation du mandataire (cases), paramètres (décision, défaillance, sortie, confidentialité, PI, pénalités, litiges) ; avertissement « à faire relire par un conseil » ; jamais de conseil juridique
- Génération déterministe (modèle paramétré, 0 LLM) → content_md + md_pdf ; « Figer l'offre » fusionné avec la génération : total_offre_ht figé, annexe de répartition (nom, lot, rôle, prix_lot_ht) visible par tous les signataires, UN seul content_hash ; convention 'perimee' si une part change ensuite
- Signature depuis l'espace de chaque membre (lien magique via _binding_required inchangé, ou compte après claim) avec identity_level imprimé ; 'hors_ligne' pour les membres rattachés sans invitation ; mail « convention à signer » (Brevo) + notification ; journal membre : convention.generated / convention.signed
- Cohérence CERFA : representant_legal, signataire_qualite, prix_lot_ht alimentent cerfa (DC1/DC2/ATTRI1) et remplacent _groupement_convention de redaction.py ; convention signée dans export ZIP et dossier ; item checklist « convention signée »
- Machine à états affichée : stepper 1→5 (seul → potentiel → composition → invitation → parts complètes → convention → prêt → déposé) dans la vue AO et dans « Partagé avec moi », dérivé par groupement_state()

**Effort :** M — environ 2 semaines  
**Valeur client :** Haute : c'est l'étape 3 (montage juridique/financier) que personne n'outille pour les TPE ; supprime le blocage « on ne sait pas rédiger la convention » et le risque de dossier incohérent (DC1 ≠ convention).  
**Dépendances :** Vague 1 (prix_lot_ht, active_invites, journal membre, citation_guard). Modèle de convention à valider par un conseil (texte, pas code).

### Vague 3 — Vrai réseau de partenaires Adjugo (B)

**Objectif.** Sur un marché trop gros, la PME voit lot par lot les entreprises vérifiées (SIRENE, BODACC, RGE, dépôts réels sur Adjugo) qui la complètent, les invite d'un clic sans voir leur email, et se fait trouver sans révéler ce qu'elle vise.

- Table partner_profiles (migration) ; GET/PUT /api/reseau/profil pré-rempli depuis Company + lookup_company ; POST verifier (SIRENE/BODACC/DECP, formulations honnêtes : « aucun avis trouvé au JJ/MM », « au moins N marchés dans DECP », None = « non vérifié ») ; POST publier (admin, siret 14 chiffres, etat actif < 30 j)
- app/services/partner_matching.py déterministe (classement 35/25/15/15/10, badges sourcés et datés) + GET /api/projects/{id}/partner-matches (≤ 3 lots SIRENE par appel, cache in-process 10 min, limiter 60/h) ; bouton « Qui me complète ? » ; RÈGLE : un seul % affiché à l'utilisateur = le score de groupement de A (score_dce) ; le barème B classe et explique (critères + sources) mais n'affiche pas de second pourcentage ; pool 'reseau' branché dans groupement_scoring
- Mise en relation 1-clic : _create_invite factorisé (comportement inchangé), recipient rempli côté serveur et masqué, actor = company_name, source 'reseau_adjugo', attach annuaire ; invitation SIRENE hors réseau (lien à transmettre) ; 409 si invitation active existante
- Annuaire réseau (réciprocité : « Publiez votre profil pour voir les N partenaires correspondants »), hidden_from_sirens dans les deux sens, compteur anonyme d'apparitions, GET /api/reseau/historique (COUNT réel sur invitations actives + parts soumises + projet envoyé/gagné/perdu, dans les deux sens)
- Cron POST /api/admin/run-partner-network borné (25 profils les plus anciens, timeouts courts, dépublication UNIQUEMENT sur réponse positive « cessé », jamais sur erreur) ; RGPD : partner_profiles dans export_my_data et delete_account + UPDATE project_invites SET recipient='' ; boucle de croissance suggest_profile après claim/inscription ; profils is_demo dans demo_seed
- Front : nav « Réseau » (Mon profil partenaire / Annuaire / Mon historique), panneau « Partenaires pour ce marché » par lot, modale d'invitation, statut « a décliné »

**Effort :** L — environ 3 semaines  
**Valeur client :** Haute à terme (effet réseau = moat), moyenne au lancement (réseau vide : le repli SIRENE et l'annuaire font le travail en attendant). Placée en 3 parce que A+E+C délivrent la valeur sans elle et que les profils publiés se construisent via la boucle d'invitation déjà active.  
**Dépendances :** Vagues 1 et 2 (invitations, journal, prix de lot, historique de dépôts = project.status). Ajout d'un cron Railway hebdomadaire.

### Vague 4 — Prouvabilité, dépôt (étape 5) et finitions

**Objectif.** Passer de « journal infalsifiable tenu par Adjugo » à « vérifiable par vous », produire la DPGF de lot localement depuis le détail chiffré, et boucler l'étape 5 avec un état « prêt à déposer » fiable.

- GET /api/invite/{token}/journal/integrity + /api/shared/{id}/journal/integrity : sous-chaîne des entry_hash me concernant recalculée ; export du journal (JSON/PDF) par membre ; SRI + CSP sur les scripts, hash des scripts publié sur la page sécurité
- DPGF de lot générée dans le navigateur depuis detail_chiffre (déchiffrement local) → déposée comme ContributionPiece ; jamais de détail chiffré vers le LLM ni la DPGF commune
- Checklist de dépôt commune : état pret_a_deposer = parts soumises + attestations valides à la date limite + convention signée + CERFA générés ; bouton « Marquer déposé » → project.status envoye → historique réseau ; relance automatique au membre dont l'attestation expire avant la date limite
- Suppression définitive de la colonne chiffrage_note ; dashboard : « N marchés accessibles en groupement », groupements en cours par étape ; fiche partenaire annuaire : références + date/source des capacités
- Point cyber (différé par le fondateur) : revue externe du schéma de chiffrement et du journal, listée comme suite, pas incluse

**Effort :** M — environ 1 à 2 semaines  
**Valeur client :** Moyenne : consolide la confiance (preuve vérifiable par le membre) et ferme l'étape 5 ; valeur commerciale de la promesse « prouvable » dans les pages sécurité.  
**Dépendances :** Vagues 1 à 3. Aucune dépendance externe.

## Risques majeurs

- Gonflement perçu du verdict : go_groupement posé sur des capacités que le mandataire a lui-même déclarées sur ses partenaires (annuaire) → match_score seul conservé, pastille distincte, warning citant le DCE, et exigence capacites_source ∈ {rne, contribution} ou avertissement proéminent (décision 5)
- Fuite déjà présente dans l'existant : chiffrage_note en clair visible du mandataire (serialize l.537, cockpit l.1061, report, build_dossier) — tant que la vague 1 n'est pas déployée, la doctrine est violée ; la migration doit être livrée en premier dans la vague
- Chiffrement par membre survendu : pas de zero-knowledge (Adjugo sert le JS) ; perte du code de récupération = détail perdu ; un invité sans compte changeant de poste doit ressaisir son code → friction réelle à documenter, et jamais écrire « le serveur ne peut pas lire » sans la précision « clé non stockée »
- Fuite par différence inhérente à la doctrine : à 2 membres le total révèle la part de l'autre ; en conjoint, l'annexe de répartition (prix par membre) est vue par tous les signataires — à assumer en UI, sinon la promesse « cloisonné » sera perçue comme fausse
- Citations LLM fabriquées : sans citation_guard contrôlé contre le DCE INTÉGRAL (pas la fenêtre _focus), A afficherait des « preuves » inventées ; et un 'Non specifie' peut signifier « hors fenêtre » → _RISK_TERMS étendus, et libellé « non trouvé dans le DCE »
- Quatre notions de membre : si active_invites() n'est pas appliqué partout (13 occurrences de revoked), un partenaire ayant décliné reste compté dans checklist, cockpit, CERFA, convention et signatures → dossier bloqué ou incohérent
- Journal membre : exposer project_audit tel quel ferait fuiter emails + IP de tous les invités ; et sans owner.view_contribution le journal du membre serait vide (perte de crédibilité) ; actor doit devenir company_name dès la vague 1 (les anciennes entrées gardent l'email : à masquer en projection)
- Process unique : matching réseau et cron de re-vérification font des appels HTTP externes synchrones sur l'unique worker → plafonds (3 lots SIRENE/appel, 25 profils/cron, timeouts courts, cache in-process) obligatoires, jamais de dépublication sur erreur réseau
- Qualifications non vérifiables par registre (Qualibat, SS3, OPQIBI) : risque de faux « couvert » par recoupement de mots (hérité de score_dce) → étiquette « à confirmer auprès du partenaire » + pièce attendue dans le coffre croisé
- Effet de bord sur stats/filtres/export RGPD/demo_seed qui testent go_decision == 'go' ; et sur les projets déjà analysés (champs d'exigences absents → traités inconnus jusqu'à ré-analyse qui débite le quota)
- Réseau vide au lancement + réciprocité mal expliquée = frein ; mitigé par repli SIRENE, annuaire, profils is_demo et boucle « publier votre profil » après chaque invitation reçue
- Effort global : A est un L (pas M), D (doctrine + crypto + journal) est un L réparti dans la vague 1 ; vague 1 ≈ 3 semaines, total ≈ 9-10 semaines pour les 4 vagues

## Décisions à valider par le fondateur

- 1. chiffrage_note existant (approche prix saisie par les partenaires, aujourd'hui en clair chez le mandataire) : A) déplacer en tête de note_au_mandataire avec le préfixe « (ancienne approche prix) » (lisible, aucune perte) ou B) effacer après avertissement de 30 jours. Recommandation : A, puis suppression de la colonne en vague 4.
- 2. UN SEUL pourcentage affiché à l'utilisateur : le score de groupement (A, score_dce réappliqué à l'entreprise virtuelle, « seul 54 % → avec X 81 % »). Le barème de matching réseau (B) sert à classer et explique par critères sourcés (badges), sans second « % » concurrent. Valider ce choix (sinon deux chiffres différents pour le même partenaire sur le même marché).
- 3. Annexe de répartition visible par tous les signataires à la génération de la convention (nom, lot, rôle, prix de vente du lot, total) — imposé par la cohérence avec l'ATTRI1/DC1 en groupement conjoint — et total révélé aux membres seulement après « Figer l'offre », avec l'avertissement « à 2 membres, le total révèle la part de l'autre ». Assumer cette fuite par différence en UI.
- 4. Chiffrement : accepter les limites écrites noir sur blanc — pas de zero-knowledge (formulation « chiffré dans votre navigateur avec une clé qu'Adjugo ne stocke pas »), code de récupération 24 caractères affiché une fois, code perdu = détail perdu, détail jamais utilisé par le LLM ni par la DPGF commune (DPGF de lot produite localement en vague 4).
- 5. Verdict « Bon potentiel en groupement » fondé sur des capacités que le mandataire a DÉCLARÉES LUI-MÊME sur ses partenaires (annuaire) : A) autorisé avec avertissement proéminent « verdict fondé sur vos propres déclarations » ou B) réservé aux capacités vérifiées (SIRENE/RNE) ou confirmées par le partenaire dans sa contribution (plus lent, plus honnête). Recommandation : A en vague 1, basculer vers B quand le réseau (vague 3) fournit des profils vérifiés.
- 6. Ordre des vagues : A + doctrine + coffre croisé (1) → convention (2) → vrai réseau (3) → prouvabilité et dépôt (4). Le « vrai réseau » est une décision figée mais passe en 3 parce qu'il n'apporte rien tant qu'il est vide, alors que A/E/C délivrent immédiatement avec l'annuaire + SIRENE ; et « cloisonnement prouvable par vous » est libellé « journal infalsifiable tenu par Adjugo » jusqu'à la vague 4. Confirmer ou imposer B en vague 2.

## Verdict du challenger

Conceptions A/B/C solides sur le papier (0 LLM dans A/B/C-génération, réutilisation réelle de ProjectInvite/Contribution/score_dce, audit chaîné), mais le dossier reçu est TRONQUÉ : C s'arrête à « POST /api/sourcing/document », D et E ne sont pas fournis — je les challenge à partir des décisions figées et des renvois que A/B/C leur font. Trois problèmes de fond, vérifiés dans le code : (1) la doctrine « le partenaire voit le total, jamais la décomposition » est déjà violée par l'existant (ProjectContribution.chiffrage_note en clair, affiché au mandataire dans list_contributions, imprimé dans le PDF « partageable » consortium_report.py l.102, copié dans le dict build_dossier) et C/D ne disent pas comment ce champ migre ; (2) C est juridiquement incohérent avec la doctrine : dans un groupement conjoint, l'ATTRI1/DC1 que TOUS les membres signent liste la répartition avec les montants par membre, donc « SA seule ligne d'annexe » fait signer des documents différents (hash différent) et contredit « le dossier dit partout la même chose » ; (3) la promesse « journal qui a vu quoi visible par chaque membre » et « cloisonnement prouvable » n'ont aucun support : project_audit est owner-only, aucun audit n'est écrit quand le mandataire LIT une contribution, le journal contient emails+IP de tous les invités, et verify_chain est par tenant. S'ajoutent : deux « % » concurrents (A réapplique score_dce, B invente un barème 35/25/15/15/10) pour le même partenaire sur le même marché ; un gonflage anti-hallucination possible via POST /simulate kind:'sirene' avec des capacités fournies par le client ; quatre notions de « membre » non unifiées (Cotraitant, ProjectCotraitant, ProjectInvite/Contribution, partner_profile) alors que checklist._is_groupement ne compte que les invitations. Effort globalement sous-estimé d'un cran (A = L, pas M ; D = L). Ordre réaliste : A (service pur + 3e verdict) → C (sans signature « électronique » survendue) → D (migration chiffrage_note + journal membre) → B → E.

### Violations d’invariants détectées (corrigées dans la synthèse)

- ANTI-HALLU (A) — A promet des « CITATIONS LITTÉRALES du DCE » (details.exigences_sources.*) affichées au survol, mais seul C prévoit la garde serveur « extrait ⊂ texte DCE sinon vidé ». Sans cette garde, A affiche des citations fabriquées par le LLM comme preuves. De plus analysis.py tronque le DCE (_focus/_RISK_TERMS : « extraits ciblés des clauses sensibles ») : la clause CA/qualifs/forme de groupement peut ne jamais être dans la fenêtre envoyée au LLM → 'Non specifie' signifie parfois « hors fenêtre », pas « absent ». Correction : helper unique citation_guard(text, extrait) appliqué à exigences_sources ET forme_groupement, contrôlé contre le texte INTÉGRAL ; ajouter groupement|conjoint|solidaire|mandataire|chiffre d'affaires|capacit|référence|effectif à _RISK_TERMS.
- ANTI-HALLU (A) — POST /groupement/simulate accepte members[{kind:'sirene', company:{NormalizedCompany}}] fourni par le CLIENT, avec save:true. Un utilisateur (ou un bug front) injecte ca=2 M€, est_rge=true, et la simulation est persistée avec source 'SIRENE'. Fausse provenance = violation directe. Correction : pour kind 'sirene' le serveur ne garde que le SIRET et RE-FETCH via registre.lookup_company (SIREN exact exigé) ; toute valeur non issue du fetch est ignorée ; si l'utilisateur saisit lui-même, kind='saisi' et source 'déclaré par vous le …'.
- ANTI-HALLU (B) — « [BODACC] aucune procédure collective publiée au JJ/MM » : l'absence de résultat d'une requête `registre like siren` (bodacc.py l.34, homonymes possibles, API parfois indisponible → None) n'est pas une preuve d'absence. Formuler « aucun avis trouvé au JJ/MM (recherche BODACC) » et, sur None, « non vérifié ». Même chose pour « N marchés remportés (DECP) » : DECP est partiel et en retard ; dire « au moins N marchés publiés dans DECP ».
- ANTI-HALLU / TENANT (A) — Les capacités de l'annuaire (Cotraitant.ca_n1, qualifications String) sont saisies par l'utilisateur SUR son partenaire ; A les fait contribuer au « 81 % » avec étiquette « déclaré par vous ». Acceptable, mais le 3e verdict go_groupement est alors posé sur des chiffres auto-déclarés par le simulant lui-même, pas par le partenaire. Exiger pour go_groupement : capacites_source ∈ {'rne','contribution'} OU avertissement proéminent « verdict fondé sur vos propres déclarations sur vos partenaires » dans ai_analysis.groupement.warnings.
- AVERTIR-PAS-BLOQUER (B) — « declined_at » : un partenaire qui décline reste revoked=False → checklist._is_groupement, consortium_cockpit, build_dossier, my_consortiums, C.signatures, cerfa _groupement_members le comptent encore comme membre (part « non soumise » dans les manques, signature 'pending' bloquant status 'signee'). Correction : traiter declined_at IS NOT NULL exactement comme revoked dans TOUTES les requêtes (helper active_invites(project_id)).
- MAGIC LINK / OTP DIFFÉRÉ (C) — Signature de la convention gatée « exactement comme submit » (_binding_required). Quand l'email n'est pas configuré ou recipient n'est pas une adresse, _binding_required=False → n'importe quel porteur du lien « signe » sans aucune preuve d'identité, et la signature est présentée comme « enregistrée ». Correction : réutiliser le gate tel quel (pas de nouveau flux), MAIS stocker signature.identity_level ∈ {'compte_verifie' (accepted_by_user_id), 'email_verifie' (verified_at), 'lien_seul'} et l'imprimer dans le PDF ; en 'lien_seul', libellé « accord enregistré via le lien (identité non vérifiée) ».
- ZÉRO JARGON — B : champ et libellé « pitch » → « présentation en une phrase » ; A : « Simulateur d'alliance » → « Répondre à plusieurs ? » ; B : « pull-only », « réciprocité » ne doivent pas apparaître en UI (« Publiez votre profil pour voir les partenaires »). C : « conjoint / solidaire » sont des termes légaux obligatoires sur les CERFA, à garder mais TOUJOURS accompagnés de la phrase simple (« chacun responsable de sa part » / « tous responsables de tout »). Les noms de routes /consortium existants restent (non UI).
- PROCESS UNIQUE (B) — POST /api/admin/run-partner-network re-vérifie SIRENE+BODACC+DECP de TOUS les profils visibles dans UNE requête synchrone sur l'unique worker (3 appels HTTP externes × N profils). Correction : lot borné par exécution (max 25 profils, les plus anciens verified_at d'abord) comme run_document_expiry_alerts, timeouts courts, et JAMAIS de dépublication sur erreur réseau (B le dit, à rendre obligatoire dans le code).
- PROCESS UNIQUE (B) — GET /partner-matches appelle _company_service().discover (SIRENE externe) par lot « à trouver » (< 3 matches réseau = tous les lots au lancement) → 5 lots = 5 appels externes synchrones sur le seul worker, à 60/h/IP. Plafonner à 3 lots SIRENE par appel + cache mémoire 10 min par (metier, departement) (process unique = cache in-process cohérent).
- RGPD / TENANT (B) — ProjectInvite.recipient reçoit l'email du partenaire RÉSEAU côté serveur, stocké dans le tenant du MANDATAIRE. Fuites concrètes vérifiées : consortium_cockpit nomme le partenaire via `or inv.recipient`, audit.record écrit actor=(inv.recipient or company_name) dans AuditLog lisible par project_audit, _notify_part_submitted peut l'inclure. Et rgpd.delete_account du partenaire n'efface pas ces lignes (delete_by ProjectInvite owner_id=uid seulement). Correction : pour source='reseau_adjugo' → actor=company_name partout, recipient jamais sérialisé ni journalisé, et à la suppression de compte/profil : UPDATE project_invites SET recipient='' WHERE partner_profile_id IN (mes profils). Ajouter partner_profiles à export_my_data et delete_account.

### Failles de sécurité

- CHEMIN OUBLIÉ (existant, à corriger par D) — ProjectContribution.chiffrage_note (Text, « Votre approche prix pour votre lot (ex. forfait 18 000 € HT) » dans invite.html l.227) est stockée EN CLAIR, renvoyée telle quelle au mandataire (list_contributions → _serialize_contribution), imprimée dans le PDF « partageable » (consortium_report.py l.102 « Approche prix : … ») et copiée dans le dict contributions de build_dossier. C'est exactement la décomposition/méthode que la doctrine interdit au mandataire. D DOIT : (1) scinder en prix_lot_ht (clair, = C) + detail_chiffre {ciphertext, iv, alg, key_id} ; (2) retirer chiffrage_note de _serialize_contribution côté owner, du PDF consortium_report et du dict build_dossier ; (3) migration : chiffrage_note existante → déplacée dans note_au_mandataire avec préfixe « (ancienne approche prix) » ou effacée après avertissement.
- JOURNAL « QUI A VU QUOI » — project_audit (invites.py l.411) est réservé au mandataire et renvoie actor (= email du co-traitant !), ip, détail de TOUS les invités. L'exposer tel quel à chaque membre (D) fait fuiter emails+IP des autres membres. Il manque aussi l'événement principal : aucun audit n'est écrit quand le mandataire LIT une contribution (list_contributions, consortium_cockpit, consortium_report, owner_download_piece est audité ? à vérifier) → le journal du membre serait vide. Correction : audit 'owner.view_contribution'/'owner.view_piece' (dédoublonné par heure), et projection membre : seulement les actions ciblant SA contribution/SES pièces + les événements de groupement (convention générée/signée), actor réduit à company_name/« le mandataire », SANS ip, SANS email.
- PROUVABILITÉ — verify_chain est par owner tenant ; un membre ne peut rien vérifier. « Cloisonnement prouvable » = overclaim tant qu'on ne lui donne pas (a) la liste des entry_hash des entrées le concernant et (b) GET /api/invite/{token}/journal/integrity qui recalcule la sous-chaîne. Sinon reformuler : « journal infalsifiable tenu par Adjugo » (pas « prouvable par vous »).
- FUITE PAR DIFFÉRENCE (C, inhérente) — Le partenaire voit total_offre_ht et SA ligne : à 2 membres il déduit exactement le prix du lot du mandataire ; à 3, deux membres qui se parlent déduisent le troisième. La doctrine (« chaque partenaire voit le prix total ») l'implique : il faut l'ASSUMER en UI (« dans un groupement à 2, le total révèle la part de l'autre ») et ne montrer le total qu'après « générer » (figé), jamais pendant le brouillon.
- INCOHÉRENCE JURIDIQUE = FAILLE DE CONFIANCE (C) — Groupement conjoint : l'ATTRI1 (généré par cerfa.generate_attri1 à partir de project_data.cotraitants) et le DC1 listent la répartition par membre ; tous signent l'acte d'engagement. Donc les prix de lot de chacun SONT vus par tous au dépôt. C avec repartition_visible_membres=False fait signer des conventions à annexes différentes (annexe_hash par membre) tout en prétendant « le dossier dit partout la même chose ». Correction : à /generer, l'annexe de répartition (lot + prix_lot_ht par membre, JAMAIS la décomposition) est visible par tous les signataires ; un seul content_hash ; l'option « masquer » n'existe que pour le brouillon avant génération. La protection D porte sur coûts/marges/méthodes, pas sur le prix de vente du lot.
- CHIFFREMENT PAR MEMBRE — schéma honnête vs promesse : « le serveur Adjugo ne peut pas le lire » n'est vrai qu'au repos. Adjugo SERT le JavaScript (app.js/invite.html via CDN Vue) : un serveur compromis ou malveillant peut livrer un script qui exfiltre la clé. Ce n'est PAS zero-knowledge. Formulation honnête : « chiffré dans votre navigateur avec une clé qu'Adjugo ne stocke pas ». Schéma recommandé : WebCrypto AES-GCM 256, clé par membre ET par projet dérivée (PBKDF2/Argon2 côté navigateur) d'un code de récupération de 24 car. affiché UNE fois + stockée en IndexedDB du navigateur ; côté serveur uniquement {ciphertext, iv, alg:'A256GCM', kdf_salt, key_fingerprint}. Invité sans compte (magic link) : la clé vit dans SON navigateur → changement de poste = ressaisie ou code de récupération ; perte du code = détail perdu (à écrire noir sur blanc). Conséquence produit : le détail chiffré ne peut JAMAIS alimenter le LLM ni la DPGF commune — chaque membre produit sa DPGF de lot localement (déchiffrement dans le navigateur) et la dépose comme ContributionPiece (visible du mandataire, c'est ce que l'acheteur recevra de toute façon). Publier le hash SRI des scripts et, à terme, un audit tiers.
- CLÉS / ORG — partner_profiles.user_id UNIQUE = data_owner_id ; org.py transfère la propriété (owner_id change) sans toucher ce profil → profil orphelin/inéditable. Même risque pour groupement_simulations.owner_id et groupement_conventions.owner_id. Ajouter ces tables à _reassign_models() / au transfert.
- ESPIONNAGE DE MARCHÉS (B) — Le matching est pull-only ✓, mais l'INVITATION révèle le marché (nom, acheteur, échéance via _send_invite_email et _invite_public) à un profil qui peut être un concurrent déguisé. hidden_from_sirens n'aide que si le mandataire a lui-même un profil (la liste vit sur partner_profiles). Correction : stocker hidden_from_sirens aussi côté Company/org (sans profil), et proposer à l'invitation un mode « aperçu minimal » (objet + lot + dépt + échéance, sans acheteur ni source_url) tant que le partenaire n'a pas accepté (declined/accepted_at).
- ÉNUMÉRATION / SCRAPING (B) — limiter slowapi = clé IP (ratelimit.client_key), pas utilisateur : un scraper multi-IP ou une org derrière un NAT contournent/saturent 60/h. GET /api/reseau/partenaires/{profile_id} par id séquentiel = énumération. Ajouter un compteur par data_owner_id (AuditLog network.* du jour) avec plafond, et ids opaques (uuid) pour les fiches.
- COFFRE-FORT CROISÉ (E, et déjà B critère Qualifications c) — B lit les Document (category=qualifications, expiration_date) du PARTENAIRE pour afficher « justificatif présent (valide jusqu'au …) » : lecture inter-tenant de métadonnées du coffre-fort d'un autre tenant, sans consentement projet. Le nom de fichier peut contenir des infos (« Qualibat_1312_perdu_2025.pdf »). Correction : consentement explicite à la publication du profil (« Adjugo pourra indiquer que vous détenez un justificatif valide, sans le montrer ni nommer le fichier ») ; n'exposer que {type normalisé, présent, expire_le} via _PARTNER_PIECE_TYPES/_norm, jamais Document.name ni file_key ; pour E, consentement PAR projet depuis l'espace du co-traitant (invite.share_vault_status=true), audité.
- CROSS-TENANT COUNT (B) — n_avec_moi joint ProjectInvite de mon org aux users de l'org du profil par verified_email/accepted_by_user_id : requête sur users.email d'un autre tenant. OK côté serveur si le résultat n'est qu'un COUNT ; interdire tout retour des emails/ids et couvrir par un test d'isolation (tests/test_isolation.py).
- DÉMO — Profils is_demo « visibles uniquement par le compte démo » : rien n'empêche le compte démo (DEMO_MODE, demo@adjugo.fr partagé publiquement) d'INVITER un vrai profil ou d'être invité. Le compte démo ne doit jamais pouvoir publier/inviter hors is_demo.

### Incohérences entre innovations

- DEUX % POUR LE MÊME PARTENAIRE — A affiche « avec Le Gall 81 % » (score_dce réappliqué à l'entreprise virtuelle) ; B affiche « Complémentarité 81 % » (barème 35/25/15/15/10). Même partenaire, même marché, deux chiffres différents étiquetés en % → contredit « verdict en % » unique. Décision : le seul % montré comme verdict est le score de groupement (A) ; B devient un CLASSEMENT (« meilleur complément pour ce lot », badges vérifiés, détail critère par critère sans total en %) ou se renomme « compatibilité » avec un autre visuel. Et A doit consommer le tri de B pour son pool 'reseau' (pas recalculer un ranking).
- DÉPENDANCE CIRCULAIRE A↔B — A : « fonctionne dès le jour 1 sans B » ; B : « A consomme partner_matching.score_partner : B doit être livrée avant ou en même temps ». Trancher : A d'abord (pool annuaire+rattachés+SIRENE), B ensuite ajoute le pool 'reseau'.
- QUATRE NOTIONS DE MEMBRE — A.members {lead, annuaire, attached, reseau, sirene} ; B via ProjectInvite.partner_profile_id ; C.signatures via invite_id OU cotraitant_link_id ; existant : ProjectCotraitant (role défaut 'sous_traitant', source 'reseau' = carnet perso) vs ProjectInvite/Contribution ; checklist._is_groupement ne compte QUE les invitations, cerfa._groupement_members ne voit que le dict fourni, consortium_cockpit que les invites. Il faut UN résolveur app/services/groupement_members.py → [{member_key, kind:'lead'|'invite'|'link', invite_id?, link_id?, profile_id?, cotraitant_id?, siret, company_name, role, lot, status, declined, revoked}] utilisé par A (pool/retenir), C (signatures), le cockpit, cerfa, checklist et E. Sinon un partenaire rattaché sans invitation sera membre pour C/DC1 mais invisible pour le cockpit et la checklist.
- SOURCE ProjectCotraitant — existant : 'reseau' = carnet d'adresses perso, 'discover' = SIRENE. B ajoute 'reseau_adjugo' ; A propose source 'reseau'|'discover' pour /retenir. Avec B, 'reseau' devient ambigu en UI (« réseau »). Renommer l'affichage : 'reseau' → « Mes partenaires », 'reseau_adjugo' → « Réseau Adjugo », 'discover' → « Registre SIRENE ».
- PRIX DU LOT — C crée project_contributions.prix_lot_ht (« seul montant que voit le chef de file ») mais chiffrage_note existe toujours, en clair, visible du chef de file, et D (non fourni) est supposé chiffrer « la décomposition ». Sans migration explicite de chiffrage_note, C et D se contredisent avec l'existant.
- TOTAL DE L'OFFRE — C : total_offre_ht = « somme des prix de lot connus + part mandataire ». La part mandataire est prise où ? project.estimate.total_ht est le chiffrage du mandataire POUR LE MARCHÉ (souvent tous lots, cf. ATTRI1 budget=_real_ht dans build_dossier) → double comptage si l'estimate couvre déjà les lots des partenaires. Ajouter params.part_mandataire_ht explicite, pré-remplie depuis estimate seulement en lot unique, sinon vide + avertissement.
- SYSTEM_PROMPT MODIFIÉ DEUX FOIS — A ajoute references_requises/effectif_minimum_requis/capacites_groupement/exigences_sources ; C ajoute forme_groupement{imposee, extrait}. Deux PR sur le même prompt JSON et les mêmes projets « à ré-analyser (quota) ». Faire UNE évolution du prompt (A+C ensemble) + garde citation unique + une seule ré-analyse.
- EXPÉRIENCE CO-TRAITANT ÉCLATÉE — A : GET /api/shared/{token}/groupement ; B : « Partagé avec moi » (_shared_item = 7 champs) + /decline ; C : GET /api/invite/{token}/groupement ; D : journal ; E : statut coffre-fort. Cinq endpoints et deux surfaces (invite.html sans compte, vue sharedao avec compte). Pour une « expérience de premier rang », un seul GET /api/invite/{token}/espace renvoyant {marche(faits), ma_part, pourquoi_vous(A), convention(C), journal(D), attestations(E), actions:{decliner,signer,…}} rendu par invite.html ET par la vue sharedao (même composant). Sinon l'expérience co-traitant sera incohérente entre les deux surfaces.
- ÉTATS — B.ProjectInvite.declined_at ; C.groupement_signatures.status 'perimee' ; A.groupement_simulations.retained ; existant Contribution.status draft|submitted ; Project.status. Aucune machine d'états commune : un partenaire peut être « a décliné » (B) et « signature pending » (C) et « retenu » (A) en même temps. Définir l'état membre dérivé dans le résolveur : invité → consulté → part soumise → convention validée | a décliné | retiré, et le faire respecter par A/C/E.
- HISTORIQUE RÉEL (B) — compte les Project.status ∈ (envoye, gagne, perdu) posés manuellement par le mandataire ; beaucoup ne mettent jamais à jour le statut → compteur ≈ 0 pendant des mois. Dériver aussi « déposé » de l'export du dossier (export_dossier → audit 'dossier.exported' / GeneratedDoc) pour le même projet.
- ALERTES E vs alerts.py — run_document_expiry_alerts est par tenant (Document.user_id). « Alertes avant dépôt » (E) exige un croisement projet.deadline × membres × documents d'AUTRES tenants, qui n'existe nulle part ; à concevoir avec consentement (voir failles).

### Surestimations

- « Le serveur Adjugo ne peut pas lire le détail » — vrai au repos seulement ; Adjugo sert le code client. Dire « chiffré dans votre navigateur, clé jamais stockée par Adjugo », jamais « zero-knowledge ». Et accepter la contrepartie : perte du code de récupération = détail perdu ; aucun support ne pourra le restaurer.
- « Cloisonnement prouvable » / « journal visible par chaque membre » — rien ne le permet aujourd'hui : pas d'audit des lectures du mandataire, journal owner-only avec emails/IP, chaîne par tenant. Sans les ajouts listés, c'est un slogan.
- « Matching qui me complète » sur réseau vide — B l'admet, mais le teaser « 4 partenaires Adjugo correspondent, publiez pour les voir » affichera « 0 » pendant des mois et le compteur « votre profil est apparu dans 12 recherches » restera à 0 : démotivant. Masquer ces compteurs sous un seuil (ex. < 5 profils publiés dans le département) et faire du repli SIRENE/DECP la vue PRINCIPALE au lancement, avec « pas encore sur Adjugo — invitez-les par lien ».
- « Historique RÉEL de co-traitance » — dépend de Project.status renseigné et de verified_email/claim ; OTP désactivé sans SMTP → beaucoup d'invités jamais rattachés. Le signal sera rare et le dire (« N groupements déposés via Adjugo — compteur en construction »).
- « Seul 54 % → avec X 81 % » — avec des capacités d'annuaire auto-déclarées PAR l'utilisateur sur son partenaire, le 81 % est l'opinion de l'utilisateur sur son partenaire. Étiquette obligatoire sur la pastille (« fondé sur vos déclarations »), et seuil : go_groupement seulement si au moins une capacité décisive vient de 'rne' ou 'contribution'.
- « Convention signée par chaque membre » — clic + hash + IP ≠ signature électronique (eIDAS). Ne jamais écrire « signée électroniquement » ; écrire « validée depuis son espace (accord enregistré le …, email vérifié : oui/non) » et rappeler que la signature manuscrite/qualifiée reste à la charge des membres au dépôt. Le modèle de convention « paramétré » reste un modèle : l'avertissement « à faire relire par un conseil » doit être dans le PDF, dans l'email et dans l'écran de validation.
- « RGE vérifié (API Recherche-entreprises) » — booléen issu de la liste ADEME avec latence et sans domaine RGE (un RGE « isolation » ne vaut pas un RGE « PAC ») : afficher « inscrit au registre RGE (ADEME) au JJ/MM — domaine à vérifier ».
- « Aucun chiffrement requis pour A/B » — vrai pour les prix, mais A persiste groupement_simulations.cumul.detail (CA nominatifs des partenaires) et B expose « tranche effectif »/catégorie : données d'entreprise, pas secrètes, mais à inclure dans l'export RGPD et le droit à l'effacement.
- Effort — A « M » : 7 lots dont 3 panneaux UI, prompt, migration, vue co-traitant → L. B « L » : + cron, growth loop, seeds, masquage email, décline partout → L+. C (tronqué) : 2 parcours de validation, PDF, emails, cockpit, checklist, verrou optimiste → L. D : crypto navigateur sur 2 surfaces + migration chiffrage_note + journal membre + intégrité → L. E : M. Total ≈ 4L + 1M ; pas livrable « jusqu'à E » en une vague.

### Ajouts manquants

- D et E ne sont pas dans le dossier reçu (texte tronqué après C « POST /api/sourcing/document ») : les faire produire/relire avant tout codage, avec les contraintes ci-dessus (migration chiffrage_note, journal membre, schéma WebCrypto honnête, consentement coffre-fort).
- Résolveur unique des membres (app/services/groupement_members.py) consommé par A, C, cockpit, cerfa, checklist, E — et correction de checklist._is_groupement pour compter aussi ProjectCotraitant role≠sous_traitant.
- Helper active_invites() : revoked=False AND declined_at IS NULL AND non expiré, utilisé partout (build_dossier, dossier_preview, cockpit, my_consortiums, consortium_report, checklist, C).
- citation_guard() partagé (A exigences_sources + C forme_groupement) + extension de _RISK_TERMS dans analysis.py ; test : citation absente du texte intégral → champ 'Non specifie' + extrait vidé.
- Audit des LECTURES du mandataire (owner.view_contribution, owner.view_piece, owner.export_dossier, owner.view_convention) dédoublonnées par heure, sinon le journal « qui a vu quoi » du membre est vide.
- Projection membre du journal : GET /api/invite/{token}/journal (ses événements seulement, actor réduit, sans IP/email) + intégrité de sous-chaîne.
- Migration explicite de project_contributions.chiffrage_note → prix_lot_ht (clair) + detail_chiffre (JSON ciphertext) ; retrait du champ de _serialize_contribution (owner), consortium_report PDF, build_dossier ; invite.html : champ « Prix de vente de votre lot (HT) » distinct de « Détail (chiffré, visible de vous seul) ».
- Tests d'isolation à étendre (tests/test_isolation.py, test_org_cotraitance_scope.py) : fiche réseau sans email/CA/références ; projection for_member sans score seul ni CA des autres ; convention partenaire sans décomposition ; journal membre sans IP ; /simulate kind:'sirene' ignore les valeurs client ; declined == revoked dans cockpit/checklist/dossier ; go_groupement impossible sans partenaire réel.
- RGPD : partner_profiles, groupement_simulations, groupement_conventions/signatures dans export_my_data et delete_account (ordre FK), scrub de ProjectInvite.recipient des invitations réseau à la suppression du partenaire, et ajout de ces tables à _reassign_models()/transfert d'org.
- Rate-limit par data_owner_id (pas seulement IP) sur annuaire/matching/vérification ; ids opaques pour les fiches réseau.
- Compte démo : interdiction de publier un profil non is_demo, d'inviter hors is_demo, et d'être invité par un vrai compte (DEMO_MODE).
- i18n : l'app charge i18n.js — toutes les nouvelles chaînes UI (A/B/C) doivent y passer, sinon régression sur les comptes non-FR.
- Migration Alembic : le modèle Cotraitant est défini dans app/routers/cotraitants.py (pas dans app/models) — la migration cotraitants.references/capacites_* doit l'importer de là ou utiliser op.add_column pur ; pattern sa.inspect idempotent + test sur SQLite (conftest) ET Postgres (JSON vs JSONB, Boolean default).
- E minimal viable : GET /api/projects/{id}/attestations (mandataire) → par membre {type∈_PARTNER_PIECE_TYPES, statut: 'fourni'|'manquant'|'expire_avant_depot', expire_le} calculé depuis (a) ContributionPiece de sa part (déjà dans le tenant) et (b) SI consentement invite.share_vault_status, ses Document.category/expiration_date via _norm/_PARTNER_PIECE_TYPES, jamais name/file_key ; alerte J-7/J-3 avant project.deadline au mandataire ET au membre via le cron existant run_cotraitance_reminders (reminder_stage) ; audit 'guest.share_vault_status' et 'owner.view_attestations'.
- Ordre de livraison réaliste : A1 (service pur + tests + 3e verdict + pastille) → A2 (besoins + preuves) → C-core (forme + convention + validation via gate existant, annexe commune) → D (migration prix + chiffrement navigateur + journal membre) → B1 (matching classement + bouton « Qui me complète ? » sur repli SIRENE) → B2 (profils/réseau) → E → A3 (vue co-traitant unifiée /espace).
