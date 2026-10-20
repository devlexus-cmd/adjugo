# Réorganisation de l'interface : vague 2b, « prise en main et partenaire »

Contrat de la vague 2b. Étude : « Réorganiser l'interface d'Adjugo : étude définitive » (12/10/2026), § 6, 7, 9
(vague 2b), 10 et 11. Base : `feat/produit-acheteur-collectivites` = `0afc1ed` (production du 20/10/2026 : vagues 0, 1
et 2a, contrats `docs/REORGANISATION_V1.md` et `docs/REORGANISATION_V2A.md`). Tête Alembic : `c4montantseul`.

Décisions de la vague (recommandations de l'étude, retenues) : D12 (a) garder le blocage tant que l'email n'est pas
confirmé et le rendre vivant ; D13 (a) un marché d'exemple entièrement fictif et dit comme tel ; D15 (a) l'espace du
partenaire sans compte réduit à sa part, avec un seul encart « Créer mon compte ». D14 (offres, tarifs) est réservée à
Eliot : aucun contrôle d'offre, aucun prix, aucune carte d'offre ni la vitrine ne changent.

La vague est menée en chantiers parallèles, chacun dans sa section ; la réunion des chantiers les assemble.

---

## B4. Le courriel d'invitation

Étude : § 6 (ligne « Le partenaire reçoit l'invitation » : « un courriel qui nomme le chef de file, le marché, la date
limite, ce qui est attendu et ce qu'il verra ; il arrive sur « Votre part dans [marché] » »), § 7.6 (vocabulaire du
partenaire), § 7.7 (les textes des courriels mis à jour avec l'écran qu'ils citent). Tests :
`tests/test_reorganisation_v2b_courriel_invitation.py` (13 tests). Postgres : `scratchpad/b4/run_b4_pg.py` de la session
(§ B4.7). Aucune migration, aucune route nouvelle, aucun texte de l'interface changé.

### B4.1 Ce qui part, et quand

Les courriels d'invitation à un groupement partent en **HTML avec leur version texte** (les deux dans le même envoi :
`send_email(…, html=…)`, Brevo `htmlContent` + `textContent`, ou SMTP `multipart/alternative`), dans le style des
courriels existants (carte de `app/services/email_templates.py`). Une seule composition :
`app/services/email_invitation.py`.

| Courriel | Quand | Route (inchangée) | Objet |
|---|---|---|---|
| Invitation d'un **partenaire connu** | Fenêtre d'invitation, cas « partenaire connu », avec un email | `POST /api/projects/{id}/invites` | « Invitation à répondre ensemble à un marché — [marché] » (celui de la vague 1) |
| Invitation d'un **membre du réseau Adjugo** | Fenêtre d'invitation, cas « réseau » ; Adjugo remplit l'adresse | `POST /api/projects/{id}/reseau/invitations` | « Une entreprise vous propose un groupement — [marché] » (celui d'avant) |
| **Renvoi** par le chef de file | « Renvoyer l'invitation par email » (même lien) | `POST /api/projects/{id}/invites/{inv}/resend` | « Rappel : invitation à répondre ensemble à un marché — … » ou « Rappel : une entreprise vous propose un groupement — … » |
| **Rappel planifié** de la part | J-3 puis J-1 de la date limite, part non soumise | `POST /api/admin/run-cotraitance-reminders` (cron) | « Rappel — il vous reste N jours pour votre part ([marché]) » (celui d'avant) |

L'entreprise du registre officiel ne reçoit toujours rien (la PME copie le lien).

### B4.2 Ce que dit le courriel

**L'invitation et son renvoi** (`invitation(…)`) :

1. « Bonjour, » puis une phrase qui nomme le chef de file et le marché : « Breizh Couverture vous invite à rejoindre son
   groupement pour répondre ensemble au marché « … ». » ; sous-traitant : « … vous invite à intervenir comme
   sous-traitant sur le marché « … ». » ; réseau : « … a trouvé votre profil sur le réseau Adjugo et vous propose de… » ;
   renvoi : « … vous renvoie son invitation à… » / « …, qui a trouvé votre profil sur le réseau Adjugo, vous renvoie sa
   proposition : … ».
2. **L'essentiel**, un fait par ligne (libellé au-dessus de sa valeur, lisible à 375 px) : Chef de file · Marché · Date
   limite · Votre rôle (« Partenaire du groupement » ou « Sous-traitant ») · Partie proposée · Entreprise invitée.
3. **Ce qui est attendu de vous** — ce que la page du partenaire permet de faire, rien de plus :
   - part à apporter : « Renseigner votre part : la partie du marché que vous prenez et son prix, l'identité de votre
     entreprise pour les formulaires officiels, vos références et vos attestations. » puis « La soumettre à [chef de
     file], avant la date limite. » ; partenaire connu : « Si vous ne souhaitez pas y aller, déclinez l'invitation depuis
     la même page. » ; réseau : d'abord « Accepter ou décliner l'invitation, depuis le lien ci-dessous. » ;
     sous-traitant : « Comme sous-traitant, vous ne signez pas la convention de groupement. » ;
   - lien en lecture seule : « Prendre connaissance du dossier que [chef de file] partage avec vous. Ce lien est en
     lecture seule : aucune part à renseigner. »
4. **Ce que vous verrez** — ce que la page lui montre (`_invite_public`) : « Le résumé du marché, les pièces que [chef de
   file] partage avec vous et votre part. » (sans pièces si le lien ne les montre pas) ; réseau : « Avant votre réponse :
   un aperçu du marché. » puis « Une fois l'invitation acceptée : … » ; toujours « Jamais le détail des prix des autres
   entreprises. » et, s'il apporte une part, « Le détail de vos prix reste chez vous : [chef de file] reçoit le prix de
   votre partie, pas son détail. » (le détail chiffré n'est lu que par lui, `guest_save_detail`).
5. **« Votre part dans « [marché] » »** et le bouton « Ouvrir votre part » (lien en lecture seule : « Le dossier
   partagé », « Ouvrir le dossier partagé »), vers `/invite/<jeton>` ; « Ce lien est réservé à votre entreprise et valable
   jusqu'au JJ/MM/AAAA. » (date de fin du lien s'il en a une), puis l'adresse à copier-coller.
6. Réseau : « Votre adresse n'est pas communiquée au chef de file tant que vous n'avez pas accepté. » ; pied : pourquoi on
   le reçoit (profil publié) et où retirer la publication (« Partenaires › Réseau Adjugo › Mon profil partenaire »).
   Partenaire connu : « Vous recevez ce message parce que [chef de file] a indiqué votre adresse pour vous inviter sur
   Adjugo. Si vous ne connaissez pas cette entreprise, ignorez simplement ce message. »

**Le rappel planifié** (`rappel_part(…)`) : « Il vous reste 3 jours pour ajouter votre part au groupement de [chef de
file] sur le marché « … » (date limite : JJ/MM/AAAA). », « Complétez votre part et soumettez-la à [chef de file]. Sans
elle, votre entreprise ne figurera pas dans la réponse commune. », ce qu'il voit (même phrase que l'invitation), ses
attestations à mettre à jour et ses parties du dossier de présentation attendues (jointes à ce rappel, comme avant : un
seul courriel), puis « Votre part dans « [marché] » » et le lien. Avant, ce rappel disait « via votre lien Adjugo » sans
donner le lien, et commençait par une minuscule (« il vous reste… »).

**La version texte** porte les mêmes faits, dans le même ordre (`test_la_version_texte_dit_ce_que_dit_le_html`).

### B4.3 Les règles tenues

- **Échappement** : toute donnée saisie (nom de l'entreprise du chef de file, de l'entreprise invitée, du marché, partie
  proposée, lignes d'attestations et de parties) est aplatie (`net` : retours à la ligne, caractères de contrôle, de
  format et de sens d'écriture retirés, blancs réunis) puis échappée (`html.escape`, guillemets compris) dans le HTML,
  pré-en-tête et lien compris. L'objet ne porte jamais de retour à la ligne (aucun en-tête glissé par un nom de marché).
- **Aucun pixel de suivi** : aucune image, aucun `background`/`url(` ; un seul lien, celui de l'invitation (bouton et
  adresse à copier). Le logo reste le mot « adjugo » en texte. (Le suivi que Brevo ajouterait au niveau du compte : § B4.9.)
- **Aucune adresse** dans le courriel : ni celle du destinataire, ni celle du chef de file ; l'adresse d'un membre du
  réseau reste remplie par le serveur et jamais renvoyée au chef de file (inchangé, testé de bout en bout).
- **Aucun fait inventé** : sans nom d'entreprise, le chef de file est « Une entreprise » / « le chef de file » / « au chef
  de file » (jamais « à le ») et la ligne « Chef de file » n'apparaît pas ; une date limite inconnue est « pas encore
  indiquée sur ce marché » ; la partie n'est dite que si elle est connue.
- **L'acheteur n'est jamais cité** : pour le réseau, l'aperçu le cache tant que l'invitation n'est pas acceptée
  (`_network_pending`) ; une seule règle pour les deux cas.
- **Vocabulaire** : « partenaire », « partie », « groupement » ; aucun mot banni (garde-fou : `tests/textes_visibles.py`
  sur le rendu, et sur toutes les chaînes du module), aucun « vérifié », zéro émoji.
- **Les liens des courriels déjà envoyés marchent toujours** : même chemin `/invite/<jeton>` ; le renvoi garde le jeton.
- **Quotas et anti-spam inchangés** : `DAILY_INVITE_CAP` (30 par organisation et par 24 h), `RESEND_MIN_INTERVAL`
  (15 minutes), `@limiter.limit("20/hour")` du renvoi, `NETWORK_INVITES_PER_PROFILE_DAY` (10), `NOTIFY_MIN_INTERVAL_S`,
  expéditeur à l'adresse confirmée, verrou « déjà invité » (`test_quotas_et_anti_spam_d_invitation_inchanges`).
- **Jamais d'envoi depuis la démonstration** : refus de la démo inchangés (`_refuse_demo_sender`, `_demo_user_ids` du
  rappel planifié), testés sur l'invitation, l'invitation réseau, le renvoi et le rappel planifié d'une invitation de la
  démo à J-2 (`test_jamais_d_envoi_depuis_la_demo`).
- Les autres courriels gardent leur pied d'avant, à l'octet près (`_shell(…, pied=None)`).

### B4.4 Les courriels qui citaient l'ancien espace du partenaire (§ 7.7)

L'espace du partenaire devient « Votre part dans [marché] » (étude, § 7.6). Relevé de toutes les chaînes des fonctions
qui envoient un courriel (`tests/textes_visibles.py`, `textes_courriels`) :

| Courriel | Avant | Après |
|---|---|---|
| Invitation (`invites.py`) | « Accédez à votre espace dédié (cloisonné à ce seul dossier) », « jamais les données des autres partenaires » | § B4.2 (« les données des autres » était faux : il voit le nom des membres et leur partie dans le dossier commun) |
| Convention à valider (`convention.py`) | « donnez votre accord depuis votre espace » | « … depuis votre part dans ce marché » |
| Offre commune figée (`invites.py`) | « Retrouvez le détail dans votre espace » | « Votre part dans ce marché : » (le partenaire voit le total, jamais le détail des autres) |
| Attestations à mettre à jour (`alerts.py`) | « Déposez-les depuis votre espace Adjugo (votre lien d'invitation). » | « Déposez-les depuis votre part dans ce marché : » et le lien |
| Rappel de part (`alerts.py`) | « via votre lien Adjugo » (sans lien) | § B4.2 |

Relus et justes, inchangés : « menu Réglages, puis Mon compte » (collègue invité), « Adjugo (Mes documents) » (pièces à
renouveler), « Trouver des marchés, onglet « Projets à venir » » (veille amont, si `PROJETS_A_VENIR=1`), « l'atelier,
onglet « Qui écrit quoi » » (partie envoyée), « la page de ce marché » (déclin, attestations des partenaires, convention
validée), « menu Réglages › Administration › Profils du réseau à valider » (administrateur), « Votre lien Adjugo »
(parties du dossier de présentation).

### B4.5 Le code

- `app/services/email_invitation.py` (nouveau) : `invitation(…)`, `rappel_part(…)`, `net`, `jour`, `ROLES`,
  `CHEMIN_PROFIL_RESEAU`.
- `app/services/email_templates.py` : `_shell(…, pied=None)` ; sans `pied`, le pied d'avant (`_PIED`), inchangé.
- `app/routers/invites.py` : `_send_invite_email(inv, project, base_url, relance=False)` compose par `invitation` ;
  `chef_de_file_nom` (profil entreprise du propriétaire de l'organisation, comme la vue du partenaire) ; `_partie_invitee`
  (rattachement au marché) ; le renvoi passe `relance=True` ; texte de l'offre figée.
- `app/routers/reseau.py` : `_network_mailer(lot, chef, relance=False)` compose par `invitation(reseau=True)`.
- `app/services/alerts.py` : le rappel planifié par `rappel_part`, avec le lien (`APP_BASE_URL`) ; le lien dans l'alerte
  des attestations.
- `app/services/atelier_groupement.py` : `lignes_relance` (les parties sans tiret) ; `liste_relance` rend le même texte.
- `app/routers/convention.py` : « depuis votre part dans ce marché ».

### B4.6 Tests

Nouveau : `tests/test_reorganisation_v2b_courriel_invitation.py` — partenaire connu de bout en bout (HTML et texte,
chef de file, marché, date limite, attendu, vu, « Votre part dans … », lien qui s'ouvre), échappement (nom du marché, du
chef de file, de l'invitée, retour à la ligne dans l'objet), rien d'inventé sans nom ni date, attendu selon le rôle et les
droits du lien, parité texte et HTML, membre du réseau (adresse jamais révélée, aperçu, acheteur absent, renvoi), renvoi
d'un partenaire connu (même jeton, 429 avant 15 minutes), quotas inchangés, rappel planifié (HTML, lien, échappement),
démonstration, mots bannis du module, « votre part » au lieu de « votre espace », pied des autres courriels inchangé.

Mis à jour, chacun avec sa raison en commentaire : `test_cotraitance_v4.py` (2 relevés de `send_email` acceptent
`html=`), `test_vocabulaire_chef_de_file.py` (idem), `test_reorganisation_v1_socle.py` (l'objet se lit dans le module
de composition), `test_reorganisation_v1_relecture.py` (le chemin « Partenaires › Réseau Adjugo › Mon profil
partenaire » aussi).

### B4.7 Vérifications

- **Suite complète** verte (SQLite, TZ=UTC) : 2 218 tests ; `scripts/sri_update.py --check` et
  `scripts/i18n_ajouter.py --check` (636 clés) inchangés : aucun fichier servi ni libellé de l'interface n'a changé
  (pas de `node --check` ni de gabarit à recompiler).
- **Les nouveaux tests sur le code de production `0afc1ed`** (copie par `git archive`) : 11 sur 13 échouent, chacun sur
  ce qu'il décrit ; les 2 autres gardent un comportement inchangé et passent des deux côtés (quotas et anti-spam,
  aucun envoi depuis la démonstration).
- **Postgres 16.2 depuis l'état exact de la production** (`scratchpad/b4/run_b4_pg.py`, 21 contrôles sur 21) : base
  montée par le code `0afc1ed` (tête `c4montantseul`) et remplie par lui (chef de file, marché « Réfection de la toiture
  <école> & préau » avec date limite, invitation d'un partenaire avec adresse, invitation en lecture seule sans pièces,
  invitation d'un sous-traitant) ; code nouveau : une seule tête, « upgrade head » ne change rien, schéma identique ;
  sur ces données : renvoi refusé avant 15 minutes (429) puis accepté, objet « Rappel : … », HTML et texte, un seul lien
  (celui de l'invitation, jeton inchangé), nom du marché échappé, aucune adresse ni image, chef de file, marché, date
  limite, « Votre part dans … » ; le lien du courriel ouvre la part (page 200, API) ; lecture seule et sous-traitant
  disent ce qui est attendu de chacun ; rappel planifié à J-2 en HTML avec le lien ; le code de production relancé lit
  et écrit. Vrais tests sur Postgres : 12 fichiers communs, mêmes échecs avec le code de production et le code nouveau
  (15 contre 15, tous dans `test_secu_rgpd.py` : son `PRAGMA foreign_keys=ON` propre à SQLite, déjà noté en vague 2a) ;
  le fichier du chantier, sur une base à part : 13 sur 13.
- **Navigateur réel** (serveur local sur le code du chantier, base jetable, démonstration par lien privé avec une clé
  jetable de 48 caractères écrite dans un fichier, jamais affichée, `DEMO_PUBLIC=0`, réseau sortant, courriels et IA
  coupés) : les trois courriels rendus (partenaire connu à 800 px, réseau et rappel à 375 px : aucun défilement
  horizontal, aucune image, un seul lien, `<script>` du nom du marché affiché comme du texte) ; la démonstration
  (« Espace entreprises », accueil, page de Kerhel à 1 280 et 375 px, aucun défilement horizontal) : « Inviter un
  partenaire » › « Un partenaire que je connais » avec une adresse, puis « Renvoyer l'invitation par email » : refus
  de la démonstration affichés, aucun envoi tenté (journal du serveur sans ligne d'envoi), console sans erreur de script
  (les deux 403 des refus).

### B4.8 Pour la réunion des chantiers

- **Le titre de la page du partenaire** (« Votre part dans [marché] ») vient du chantier de l'espace partenaire
  (`sharedao` et `invite.html`) : le courriel y mène par le même lien `/invite/<jeton>`. Si ce chantier retient un autre
  titre, le changer dans `_bloc_part` (un seul endroit) et dans les tests.
- **« Voir ce que verra [partenaire] »** : la liste « Ce que vous verrez » du courriel décrit la même page ; les deux
  doivent rester d'accord.
- **Confirmation d'email vivante** : `email_templates.py` est aussi touché par ce chantier-là ; ici seul `_shell` reçoit
  un paramètre (`pied`), sans changer le rendu des courriels existants.

### B4.9 Pour Eliot

- **Brevo** : vérifier dans le compte Brevo (Transactionnel › Paramètres) que le suivi des ouvertures et des clics est
  coupé. Le gabarit n'a ni image ni pixel, mais Brevo peut en ajouter un et réécrire les liens au niveau du compte : le
  code ne peut pas le garantir.
- Rien d'autre à régler : pas de variable, pas de migration.

### B4.10 Laissé, avec sa raison

- **La partie proposée au premier envoi d'un partenaire connu** : le rattachement au marché qui la porte est posé après
  l'envoi (`create_invite` : `lien_a_inviter` après `_create_invite`) ; changer cet ordre toucherait la création d'une
  invitation. Le renvoi la dit ; l'invitation réseau aussi.
- **Les courriels de suivi** (part soumise, accusé de réception, convention à valider ou validée, offre figée, partie du
  dossier de présentation, accès retiré, code de vérification) restent en texte : ce ne sont pas des invitations ; leurs
  mots sont relus (§ B4.4).
- **Langues** : les courriels d'Adjugo sont en français ; aucun libellé de l'interface ne change (traductions inchangées).
