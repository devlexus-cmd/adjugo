# Audit de cybersécurité — octobre 2026

> Audit adversarial en local (jamais contre la production) : 8 angles d'attaque (authentification, isolation entre organisations, invités et co-traitance, fichiers et injections, configuration et dépendances, IA et RGPD, résilience, attaquant boîte noire), puis chaque trouvaille reproduite par script ET attaquée par un réfutateur, puis synthèse. 109 agents. Scripts de preuve : scratchpad de la session (cyber/).

## Posture — 6/10

Le socle d'authentification et de cloisonnement d'Adjugo est réellement solide, et vérifié : JWT verrouillé (HS256 fixe, expiration obligatoire, clé forte exigée en prod), mots de passe PBKDF2 600k, anti-énumération par timing, révocation de session par token_version, séparation stricte PME/acheteur dans les deux sens, isolation entre organisations propre sur 129 tests d'accès croisés, webhook Stripe signé et idempotent, et le détail de chiffrage jamais renvoyé au mandataire côté serveur. Ce n'est pas un jouet. Ce qui n'est PAS au niveau, ce sont trois choses : la résistance aux pannes (un seul worker, et plusieurs chemins permettent à un simple utilisateur — y compris le compte démo public — de faire tomber tout le service), le cycle de vie des données personnelles (la suppression de compte peut échouer en production et laisse des résidus, plusieurs promesses de la page sécurité ne sont pas tenues à la lettre), et quelques secrets qui circulent trop librement (le lien de confirmation d'email vaut une session complète pendant 3 jours). Le risque n°1, concret et facile : une archive ZIP piégée de ~200 Ko envoyée à l'import de dossier ou à la base de connaissances décompresse des centaines de Mo en mémoire et tue l'API pour tous les clients, sans aucun quota ni vérification d'email requis, rejouable à volonté. Le risque n°2 : le mail « Confirmez votre adresse » contient un jeton qui est en réalité une session plein droit valable 3 jours et réutilisable. Le risque n°3 : un bloc de défauts autour du droit à l'effacement (RGPD) qui touche à la fois le fonctionnement et des engagements publics. Aucune faille d'isolation inter-clients exploitable n'a été trouvée — c'est important et rassurant. L'essentiel des trouvailles sont des dénis de service et des écarts de conformité, pas des fuites de données entre entreprises.

## Trouvailles confirmées (par ordre de correction)

| # | Gravité | Statut | Effort | Trouvaille | Où |
|---|---|---|---|---|---|
| 1 | critique | reproduite | M | Archive ZIP piégée : un fichier de 200 Ko met tout le service hors ligne | `app/services/analysis.py:446` |
| 2 | importante | reproduite | S | Les fichiers téléversés sont chargés en mémoire AVANT le contrôle de taille | `app/routers/documents.py:36` |
| 3 | importante | reproduite | S | Le lien de confirmation d'email est une session complète réutilisable 3 jours | `app/core/security.py:113` |
| 4 | importante | reproduite | M | Le serveur va chercher une URL fournie par l'utilisateur (SSRF) | `app/routers/sourcing.py:356` |
| 5 | importante | reproduite | M | Suppression de compte (RGPD) : peut échouer en production et laisse des résidus | `app/routers/rgpd.py:158` |
| 6 | importante | reproduite | S | Le mandataire peut injecter un script qui lit le chiffrage secret du partenaire (XSS via « Avis d'origine ») | `app/static/invite.html:279` |
| 7 | moyenne | reproduite | S | Le compte démo public peut faire envoyer des emails d'invitation Adjugo à n'importe quelle adresse | `app/routers/invites.py:469` |
| 8 | moyenne | reproduite | S | Un salarié retiré de l'entreprise garde l'accès aux mémoires IA générés | `app/routers/jobs.py:15` |
| 9 | moyenne | reproduite | S | Le partenaire invité voit et télécharge les anciennes versions remplacées des pièces | `app/routers/invites.py:655` |
| 10 | moyenne | reproduite | S | Un ex-membre peut faire disparaître des traces « offre figée » du journal | `app/routers/invites.py:1907` |
| 11 | moyenne | reproduite | S | Le paiement à l'usage s'active sans abonnement ni carte → analyses IA illimitées non facturables | `app/routers/stripe_pay.py:107` |
| 12 | moyenne | reproduite | M | Les fichiers du stockage ne sont jamais supprimés à la clôture du compte | `app/routers/rgpd.py:158` |
| 13 | moyenne | reproduite | M | Sauvegardes non chiffrées par l'application, contenant des liens d'invitation encore valides | `app/services/backup.py:40` |
| 14 | moyenne | reproduite | S | Analyse d'un PDF scanné : toutes les pages sont rendues avant tout plafond | `app/services/analysis.py:367` |
| 15 | moyenne | reproduite | S | Invitation d'équipe : contrôle d'email sensible à la casse → comptes dupliqués | `app/routers/org.py:152` |
| 16 | importante | non reproduit | M | Dépendances de production figées sur des versions avec failles connues | `requirements.txt:1` |
| 17 | moyenne | reproduite | S | Rejouer un ancien lien de vérification « prouve » une adresse jamais confirmée | `app/routers/auth.py:114` |
| 18 | moyenne | non reproduit | M | OAuth Google : le paramètre anti-CSRF n'est pas lié au navigateur | `app/routers/google_auth.py:59` |

### 1. Archive ZIP piégée : un fichier de 200 Ko met tout le service hors ligne

**Impact.** N'importe quel utilisateur connecté — y compris le compte démonstration public, sans mot de passe — peut téléverser une petite archive qui, une fois ouverte, remplit toute la mémoire du serveur et fait planter l'application pour TOUS les clients (PME et collectivités) jusqu'au redémarrage. C'est rejouable autant de fois qu'on veut, et aucun quota ni email vérifié n'est exigé pour le déclencher.

**Correction.** Dans extract_dce_text (boucle ZIP), ne plus faire `data = zf.read(n)` sans borne : lire chaque membre de façon plafonnée (`with zf.open(n) as fh: data = fh.read(PLAFOND+1)`) et sauter tout membre > PLAFOND (ex. 20 Mo décompressés), avec un budget cumulé (ex. 80 Mo). Appliquer la même borne aux branches PDF/DOCX. Vaut pour tous les appelants (sourcing, amont, knowledge).

### 2. Les fichiers téléversés sont chargés en mémoire AVANT le contrôle de taille

**Impact.** Même famille de problème que le n°1 : sur le coffre-fort et les imports de dossier, le serveur lit la totalité du fichier envoyé avant de vérifier qu'il respecte la limite de 20/50 Mo. Un utilisateur qui envoie un corps de plusieurs Go fait grimper la mémoire du serveur unique et peut faire tomber l'API. Le bon patron existe déjà dans le code co-traitant (lecture bornée) ; il n'est juste pas appliqué ici.

**Correction.** Remplacer `file.file.read()` / `await file.read()` par une lecture plafonnée `read(MAX+1)` puis 413 si dépassement, dans documents.py:36, sourcing.py:430 et :530, knowledge.py:53, amont.py:123 — exactement comme invites.py:183 le fait déjà.

### 3. Le lien de confirmation d'email est une session complète réutilisable 3 jours

**Impact.** Le jeton glissé dans le mail « Confirmez votre adresse » (lien /app?verify=…) est en réalité une clé de session plein droit, valable 3 jours et réutilisable. Quiconque voit ce mail — boîte partagée, transfert, journaux de l'outil d'emailing, historique du navigateur — peut entrer dans le compte : lire toutes les données, créer des marchés, renommer l'organisation, exporter tout le compte. Ça contourne aussi le plafond de session 12h et le verrou d'inactivité (qui ne sont que côté navigateur).

**Correction.** Dans get_current_user (security.py), juste après le rejet du claim `typ`, ajouter : `if payload.get("purpose"): raise HTTPException(401, ...)`. Les jetons de session (register/login/demo) n'ont jamais `purpose`, et verify-email vérifie déjà `purpose` explicitement — aucune régression. En complément : lien de confirmation en jeton aléatoire à usage unique haché en base (comme « mot de passe oublié »), pas un JWT de session.

**Promesse publique contredite.** confidentialite.html §9 « contrôle des accès et habilitations » : un email de service vaut mot de passe pendant 3 jours.

### 4. Le serveur va chercher une URL fournie par l'utilisateur (SSRF)

**Impact.** Tout utilisateur connecté (même en essai gratuit) peut fournir un marché dont l'« adresse d'origine » pointe vers une ressource interne (métadonnées cloud, service interne, port local). Le serveur la télécharge, suit les redirections, et peut renvoyer à l'attaquant un extrait du contenu. L'impact exact (vol de secrets cloud) est sans doute moindre qu'un cas d'école, mais le principe — faire interroger par le serveur des adresses qu'il ne devrait jamais toucher — est bien réel.

**Correction.** Dans boamp.py:fetch_dce, valider la cible AVANT tout GET : imposer https et restreindre l'hôte à boamp.fr (le DCE n'y vit que là), appliquer la même vérif aux liens PDF extraits, et mettre follow_redirects=False (ou revalider l'hôte à chaque redirection). Idéalement, refuser les IP privées/loopback/link-local via un garde-fou générique dans app/sourcing/http.py.

### 5. Suppression de compte (RGPD) : peut échouer en production et laisse des résidus

**Impact.** Quand un client demande la suppression de son compte, la liste des données effacées oublie les travaux IA (jobs), les simulations de groupement, les retours (feedback) et des liaisons. Sur la base de production (PostgreSQL), cet oubli provoque très probablement une erreur 500 « Suppression impossible » pour tout client ayant déjà lancé une analyse IA : le droit à l'effacement est alors inopérant. De plus, le message d'erreur renvoie au client le détail technique brut (noms de tables, requête SQL). En environnement de test (SQLite) ça « passe » mais laisse les données en place.

**Correction.** Dans delete_account, effacer aussi Job, Feedback, GroupementSimulation, ProjectCotraitant/CoMember (enfants avant parents), remettre ProjectInvite.accepted_by_user_id à NULL, et supprimer l'utilisateur (ou mettre org_id à NULL) AVANT l'organisation. Remplacer les deux `raise HTTPException(500, f"… : {e}")` par un message générique + log serveur. Ajouter PRAGMA foreign_keys=ON dans conftest pour que les tests détectent ce type de régression.

**Promesse publique contredite.** securite.html §6 « vous pouvez les exporter ou supprimer votre compte à tout moment depuis l'application ».

### 6. Le mandataire peut injecter un script qui lit le chiffrage secret du partenaire (XSS via « Avis d'origine »)

**Impact.** Un mandataire (n'importe quel compte Adjugo) crée un marché dont l'« adresse d'origine » est un petit script déguisé, puis invite un partenaire. Dans l'espace cloisonné du partenaire, le lien « Avis d'origine » est précisément celui qu'il est censé cliquer ; au clic, le script s'exécute là où vit la clé de déchiffrement du partenaire — il peut donc lire et exfiltrer le détail de chiffrage que la page sécurité promet illisible pour tous. Vérifié jusqu'au point où le serveur renvoie le script tel quel au partenaire ; l'exécution dans le navigateur n'a pas été rejouée automatiquement (mais le mécanisme est établi : la CSP autorise les scripts en ligne).

**Correction.** Côté client (invite.html), ajouter un garde de schéma : `const safeUrl = u => /^(https?:\/\/|\/)/i.test(String(u||'').trim()) ? u : '#';` et l'appliquer aux deux liens source_url (lignes 279 et 747). Côté serveur, valider source_url dans ProjectCreate/ProjectUpdate (schemas) pour n'accepter que http(s)/relatif.

**Promesse publique contredite.** securite.html §4 « Le détail de votre chiffrage… Ni le mandataire, ni Adjugo, ni l'IA ne peuvent le lire ».

### 7. Le compte démo public peut faire envoyer des emails d'invitation Adjugo à n'importe quelle adresse

**Impact.** N'importe qui ouvre le compte démonstration (un clic, sans mot de passe) puis crée des invitations vers des adresses de son choix : Adjugo envoie alors de vrais emails depuis noreply@adjugo.pro, avec un lien fonctionnel. C'est un canal de spam/hameçonnage sous l'identité d'Adjugo, qui abîme la réputation du domaine d'envoi et traite des adresses de tiers sans base légale.

**Correction.** Dans create_invite et resend_invite, après _owned_project : si le compte courant est le compte démo, ne pas envoyer d'email (403, ou créer l'invitation avec emailed=False). Réutiliser le motif is_demo déjà présent côté sourcing/acheteur. Ajouter un plafond quotidien d'invitations par organisation.

### 8. Un salarié retiré de l'entreprise garde l'accès aux mémoires IA générés

**Impact.** Quand le propriétaire retire un membre de l'équipe, tout lui est bien retiré… sauf les résultats des générations IA (mémoires techniques, questionnaires), produits à partir du savoir-faire commun de l'entreprise. L'ex-salarié, dont le compte existe toujours, peut se reconnecter et récupérer ces livrables en devinant des numéros de job séquentiels. C'est une fuite du savoir-faire maison vers quelqu'un qui a quitté la société.

**Correction.** Dans org.py _reassign_models (ligne 34-38), ajouter Job à l'import et à la liste `mods` : Job a bien un user_id, donc il sera réassigné au propriétaire au retrait. En défense : scoper jobs.py:15 par organisation (member_ids) plutôt que par simple user_id.

**Promesse publique contredite.** org.py:195 (retrait d'un membre) « il perd immédiatement l'accès aux données de l'organisation » — contredit.

### 9. Le partenaire invité voit et télécharge les anciennes versions remplacées des pièces

**Impact.** Quand le mandataire remplace une pièce du dossier (un CCTP/DPGF corrigé, par exemple), l'ancienne version disparaît bien de son coffre-fort — mais reste visible et téléchargeable par le partenaire invité. Le mandataire croit la pièce erronée retirée alors qu'un partenaire peut encore récupérer l'ancienne (ex. un prix ou une donnée corrigée).

**Correction.** Ajouter `Document.parent_id.is_(None)` au filtre de guest_view (invites.py:655), guest_download (invites.py:680-681) et project_documents (projects.py:27-29). En complément, propager deleted_at aux anciennes versions dans delete_document.

### 10. Un ex-membre peut faire disparaître des traces « offre figée » du journal

**Impact.** Les mentions « offre figée / défigée » d'un marché sont enregistrées au nom du membre qui a créé le marché, pas de l'entreprise. Résultat : elles n'apparaissent pas dans le contrôle d'intégrité du propriétaire, et si l'ex-membre supprime son compte (RGPD), ces entrées du dossier de l'entreprise disparaissent du journal — sans que le contrôle d'intégrité ne signale rien. Un ancien salarié peut ainsi effacer la trace « offre figée le … » d'un marché de son ex-employeur.

**Correction.** invites.py:633 et :1907 : remplacer `owner_id=project.user_id` par le propriétaire canonique du tenant (data_owner_id(current_user, db) pour freeze_offer ; résolution via le propriétaire de l'org du créateur pour _unfreeze_offer_if_needed). En défense, ne jamais purger AuditLog d'un membre à l'effacement RGPD.

**Promesse publique contredite.** securite.html §4 « journal chaîné par hachage (toute modification serait détectable) ».

### 11. Le paiement à l'usage s'active sans abonnement ni carte → analyses IA illimitées non facturables

**Impact.** Un compte gratuit tout neuf, en essai 30 jours et sans moyen de paiement, peut activer le « paiement à l'usage ». Il peut alors lancer autant d'analyses IA qu'il veut au-delà du quota : chacune coûte de l'argent réel à Adjugo (Anthropic/Mistral) mais aucune n'est facturable, faute de client Stripe. C'est une fuite de coût, pas une faille de données.

**Correction.** Dans set_overage, refuser l'activation si le compte n'a pas d'abonnement payant actif (plan pro/business + stripe_customer_id) → 402. En défense dans consume_analysis:173, n'autoriser la branche overage que pour un abonnement facturable.

### 12. Les fichiers du stockage ne sont jamais supprimés à la clôture du compte

**Impact.** La suppression de compte efface les lignes en base, mais jamais les fichiers eux-mêmes dans le stockage (Kbis, attestations, DCE, PDF générés, pièces des partenaires). Ils restent dans le bucket indéfiniment, sans référence — donc difficiles à retrouver et à purger, et toujours présents bien après le délai promis. Même défaut pour la corbeille du coffre-fort, qui n'a aucune purge.

**Correction.** Dans delete_account, collecter les file_key (Document, ContributionPiece, GeneratedDoc, Project.dce_file_key) puis appeler storage.delete() APRÈS commit réussi. Ajouter une tâche quotidienne qui purge la corbeille (documents dont deleted_at > 30 j) et son fichier.

**Promesse publique contredite.** securite.html §2 « une suppression… devient définitive, y compris dans les sauvegardes, sous 14 jours ».

### 13. Sauvegardes non chiffrées par l'application, contenant des liens d'invitation encore valides

**Impact.** Les sauvegardes quotidiennes sont un export complet de toute la base, compressé mais non chiffré par Adjugo, déposé dans le même stockage que les documents avec les mêmes identifiants. Une fuite de ces identifiants (ou un accès au bucket) donne 14 jours de copies complètes et des liens de co-traitance encore utilisables tels quels. Le seul chiffrement est celui du fournisseur « au repos », pas une clé détenue par Adjugo.

**Correction.** Chiffrer le dump dans l'application avec une clé dédiée (AES-GCM / Fernet), distincte des identifiants du stockage, conservée hors du stockage et de Railway ; refuser la sauvegarde si la clé manque. À défaut, au minimum neutraliser (hacher/vider) les jetons d'invitation et OTP dans le dump.

**Promesse publique contredite.** securite.html §2 « sauvegardes quotidiennes chiffrées » (chiffrement non réalisé par Adjugo).

### 14. Analyse d'un PDF scanné : toutes les pages sont rendues avant tout plafond

**Impact.** Quand un dossier scanné est analysé, le serveur convertit en images TOUTES les pages du PDF avant de n'en garder que 15. Un PDF de plusieurs centaines/milliers de pages monopolise le processeur et la mémoire du serveur unique — un seul import suffit à le rendre lent ou indisponible pour les autres.

**Correction.** Dans _ocr_pdf, borner le rendu dès l'appel : `convert_from_bytes(content, dpi=200, first_page=1, last_page=max_pages)` (poppler ne rend alors que les premières pages). Dans extract_text_from_pdf, borner le nombre de pages et la taille cumulée.

### 15. Invitation d'équipe : contrôle d'email sensible à la casse → comptes dupliqués

**Impact.** Partout ailleurs, Adjugo traite les emails sans tenir compte des majuscules (un compte par adresse). Mais l'invitation d'un membre, elle, compare l'adresse à l'identique : en variant la casse, on peut créer une deuxième ligne pour une adresse qui a déjà un compte. La victime peut alors se retrouver avec une connexion ou une réinitialisation de mot de passe qui échoue de façon imprévisible (la base ne garantit pas quel compte répond).

**Correction.** Dans invite_member (org.py), tester l'existence avec `func.lower(User.email) == email_norm` et insérer l'email normalisé (minuscules). Idéalement, un index unique insensible à la casse sur User.email.

### 16. Dépendances de production figées sur des versions avec failles connues

**Impact.** L'image de production installe des versions anciennes de plusieurs briques (fastapi/starlette, python-multipart, pypdf) pour lesquelles des failles de déni de service sont publiquement connues et corrigées en amont. Non rejoué (impossible d'installer ces versions hors ligne, et l'environnement local tourne sur des versions plus récentes) — mais l'écart entre ce qui est testé localement et ce qui part en production est réel, et ces briques traitent justement les fichiers envoyés par les utilisateurs.

**Correction.** Monter fastapi≥0.116.1 avec starlette≥0.47.2, python-multipart≥0.0.18, pypdf≥6.4.0. Générer un lockfile avec hachages depuis la pile de prod (Python 3.12), installer avec --require-hashes, et recréer le venv local depuis ce lockfile pour que les tests valident la même pile. Ajouter pip-audit en CI.

### 17. Rejouer un ancien lien de vérification « prouve » une adresse jamais confirmée

**Impact.** Le lien de confirmation n'est rattaché qu'au compte, pas à l'adresse à prouver. Quelqu'un peut confirmer son adresse initiale, la remplacer par une adresse qu'il ne possède pas, puis rejouer son ancien lien : le compte réaffiche « adresse prouvée » sur une adresse qui n'a jamais rien reçu. Or c'est précisément cette preuve qui autorise à réclamer une invitation de co-traitance nominative — le garde-fou d'identité des liens de partage est donc contournable.

**Correction.** Mettre l'email dans le jeton de vérification (auth.py:29) et, à la consommation (verify_email), exiger que l'email du jeton corresponde à l'email courant du compte avant de passer email_verified=True.

### 18. OAuth Google : le paramètre anti-CSRF n'est pas lié au navigateur

**Impact.** Le « state » de la connexion Google prouve seulement qu'Adjugo l'a émis récemment, pas que c'est bien ce navigateur qui a lancé la connexion : il n'est stocké dans aucun cookie. Un attaquant pourrait faire aboutir une victime dans le compte Google de l'attaquant (les données saisies ensuite iraient chez lui). Le jeton de session est en plus renvoyé dans l'URL (?gtoken=), donc exposé à l'historique. Non rejoué (interdiction d'appeler Google), et la connexion Google est inactive tant que les identifiants ne sont pas configurés — c'est à vérifier/corriger avant de l'activer.

**Correction.** Poser le nonce du state dans un cookie HttpOnly/Secure/SameSite=Lax à /google/login, l'exiger et le comparer au callback, puis l'effacer. Renvoyer le jeton de session en fragment (/app#gtoken=) ou en cookie, pas en query string.

## Corrections rapides (< 1 h chacune)

- security.py get_current_user : rejeter tout jeton portant un claim `purpose` (2 lignes) — neutralise immédiatement le lien de confirmation utilisé comme session (rang 3).
- invites.py:655 et :680 + projects.py:27 : ajouter le filtre `Document.parent_id.is_(None)` — le partenaire ne voit plus les versions remplacées (rang 9).
- org.py:38 : ajouter `Job` à la liste `_reassign_models` — l'ex-membre perd l'accès aux mémoires IA (rang 8).
- invites.py:633 et :1907 : attribuer l'entrée d'audit au propriétaire du tenant, pas au créateur du marché (rang 10).
- rgpd.py:141 et :169 : remplacer le message d'erreur `: {e}` par un texte générique + log serveur (arrête la fuite de SQL au client).
- main.py:70 : docs_url/redoc_url/openapi_url = None quand ENVIRONMENT=production (ferme Swagger /docs en prod).
- invite.html:92/279/747 : garde de schéma `safeUrl()` sur source_url — coupe l'XSS « Avis d'origine » (rang 6).
- stripe_pay.py:116 : refuser l'activation du paiement à l'usage sans abonnement payant actif (rang 11).
- org.py:152/160 : contrôle d'email insensible à la casse + normalisation à l'insertion dans invite_member (rang 15).
- analysis.py:367 : `convert_from_bytes(content, dpi=200, first_page=1, last_page=max_pages)` — borne le rendu OCR (rang 14).
- auth.py:29/114 : lier le jeton de vérification à l'adresse et le comparer à la consommation (rang 17).

## Plan en vagues

### Vague 1 — Empêcher qu'un seul utilisateur fasse tomber le service, et fermer la session fantôme (à faire avant d'élargir la beta) — effort M

- Lecture bornée des membres d'archive ZIP dans extract_dce_text (rang 1) — le correctif le plus urgent.
- Lecture plafonnée des téléversements avant contrôle de taille sur les 4 routes d'upload (rang 2).
- Rejet des jetons `purpose` dans get_current_user + lien de confirmation en jeton à usage unique (rang 3).
- Borne du rendu OCR/PDF (rang 14).
- Allowlist d'hôte + follow_redirects=False sur fetch_dce (rang 4, SSRF).

### Vague 2 — Cloisonnement, promesses de co-traitance et droit à l'effacement — effort L

- Garde de schéma sur source_url côté client + validation serveur (rang 6, XSS).
- Réassignation des jobs au retrait d'un membre (rang 8).
- Filtre parent_id sur les vues invité et dossier (rang 9).
- Entrées d'audit figer/défiger rattachées au tenant (rang 10).
- Suppression de compte : enfants + ordre + purge du stockage + corbeille, et erreurs génériques (rangs 5 et 12).
- Jeton de vérification lié à l'adresse (rang 17) et blocage de l'envoi d'emails depuis le compte démo (rang 7).
- Paiement à l'usage conditionné à un abonnement actif (rang 11).

### Vague 3 — Durcissement et mise en cohérence des promesses publiques — effort M

- Montée des dépendances + lockfile avec hachages + pip-audit en CI (rang 16).
- Chiffrement applicatif des sauvegardes avec une clé hors stockage (rang 13).
- Ancrage de tête du journal d'audit (détecter la suppression des dernières entrées) et correction des docstrings.
- Masquage des jetons d'invitation et des emails dans les logs/Sentry.
- Liaison du state OAuth au navigateur avant d'activer Google (rang 18) ; jeton de session hors URL.
- Échappement des champs dynamiques dans la génération DUME (reportlab) ; type MIME dérivé de l'extension pour le coffre-fort.
- Mise à jour honnête de securite.html / confidentialite.html (voir promesses_publiques).

## Écarts avec les promesses publiques (page sécurité / confidentialité)

- securite.html §4 « Le détail de votre chiffrage… Ni le mandataire, ni Adjugo, ni l'IA ne peuvent le lire » : contredit tant que l'XSS via source_url (rang 6) n'est pas corrigé — un script injecté par le mandataire peut lire ce détail dans le navigateur du partenaire. À corriger (pas à reformuler) : c'est le cœur de l'ADN produit.
- securite.html §4 « journal chaîné par hachage (toute modification serait détectable) » : la modification d'une entrée existante est bien détectée, mais pas la suppression des entrées les plus récentes, ni la disparition d'entrées écrites au mauvais propriétaire (rang 10). Reformulation honnête : « Toute altération d'une entrée existante est détectable. L'ancrage contre la suppression des entrées les plus récentes est en cours de déploiement. »
- securite.html §2 « sauvegardes quotidiennes chiffrées » : vrai uniquement via le chiffrement au repos du fournisseur, pas par une clé détenue par Adjugo (rang 13). Reformulation : « sauvegardes quotidiennes stockées chiffrées au repos chez notre hébergeur européen » — ou mettre en place un chiffrement applicatif pour pouvoir maintenir la formule actuelle.
- securite.html §2 et §6 « suppression définitive, y compris dans les sauvegardes, sous 14 jours » / « supprimer votre compte à tout moment » : non tenu aujourd'hui (échec probable en prod + fichiers du stockage jamais purgés, rangs 5 et 12). À corriger plutôt qu'à reformuler.
- securite.html §3 « politique de non-rétention / non-entraînement de l'API » : le non-entraînement est exact (défaut des API commerciales), mais la non-rétention suppose un accord Zero Data Retention qui n'est matérialisé nulle part dans le code/config. Reformulation : retirer « non-rétention » et n'affirmer que le non-entraînement, jusqu'à signature d'un accord ZDR avec le fournisseur actif.
- confidentialite.html §6 (ligne Sentry : « journaux techniques, identifiants techniques, adresse IP ») : des jetons d'invitation et des adresses email peuvent se retrouver dans les journaux applicatifs, donc potentiellement transmis à Sentry — au-delà du périmètre déclaré. Masquer ces valeurs dans les logs (vague 3) pour que la déclaration reste exacte.

## Ce qui est prouvé solide

- Isolation entre organisations : aucun accès indu trouvé sur 129 tentatives d'accès croisés (projets, documents, factures, contacts, savoir-faire, co-traitance, jobs, exports) — un client ne voit jamais les données d'un autre.
- Cloisonnement des deux faces PME / acheteur effectif dans les deux sens : un jeton acheteur est refusé côté PME et inversement, identités chargées depuis des tables séparées.
- Jeton d'invitation (lien magique) strictement borné à sa propre contribution et à son seul marché : impossible de lire/modifier la pièce d'un autre partenaire ou un document d'un autre projet.
- Doctrine de visibilité tenue dans les réponses : le prix et le détail de chiffrage des autres ne sont jamais renvoyés ; le coffre croisé n'expose que le statut des pièces, le journal membre ni email ni IP des autres.
- Authentification robuste : JWT HS256 avec algorithme fixé et expiration obligatoire (jeton « alg=none » ou mauvais secret rejeté), mots de passe PBKDF2-SHA256 600k à temps constant, anti-énumération par timing au login et message générique sur « mot de passe oublié », jeton de réinitialisation à usage unique haché.
- Révocation de session par token_version : un ancien jeton est invalidé au changement de mot de passe, à la réinitialisation, au retrait et au transfert de propriété ; compte désactivé rejeté même avec un jeton déjà émis.
- Webhook Stripe : signature obligatoire et idempotence par clé primaire — un faux évènement de paiement forgé ne change pas le plan ; un plan inconnu rétrograde vers starter (jamais une montée).
- Garde-fous de production fail-closed : l'application refuse de démarrer en production avec une clé secrète faible, DEMO_MODE activé, ou CRON_SECRET/DCE_ACCESS_CODE manquants ; tâches cron admin protégées par secret comparé à temps constant.
- Pas d'injection SQL (requêtes paramétrées, noms de tables issus des métadonnées), en-têtes de sécurité présents (HSTS, nosniff, frame-ancestors, CSP object-src 'none'), CORS en liste blanche, aucun secret versionné dans git, image Docker en utilisateur non-root, un seul worker sans Redis (rate-limit cohérent).

## Non couvert par cet audit

- Comportement réel sur PostgreSQL (clés étrangères, verrous SELECT … FOR UPDATE) : pas de Postgres local et interdiction de toucher la prod — l'échec 500 de la suppression de compte (rang 5) est étayé par le code mais non rejoué.
- Configuration réelle de Railway (ENVIRONMENT, SECRET_KEY, CRON_SECRET, CORS, DCE_ACCESS_CODE) : non lue (règle sur les secrets) — les garde-fous fail-closed sont vérifiés dans le code, pas leur réglage en prod.
- Versions exactes de requirements.txt (rang 16) : non installables hors ligne, aucun pip-audit exécuté, exploitation DoS non rejouée.
- Chiffrement au repos et URLs signées du stockage R2/S3 : seul le backend local a été testé ; le service inline via Content-Type côté S3 (XSS sur l'origine de stockage) et les URLs présignées n'ont pas été exercés contre un vrai bucket.
- Comportement réel des modèles IA face à une injection de prompt : aucun appel LLM autorisé — seul le flux de données a été vérifié (le texte d'un partenaire entre bien dans le prompt du mandataire, sans délimiteur ni consigne).
- Flux Google OAuth de bout en bout (rang 18) et contenu réel des évènements Sentry : non rejouables sans service tiers / sans DSN.
- Exécution DOM de l'XSS source_url (rang 6) : établie côté serveur, non rejouée dans un vrai navigateur.
- Crypto navigateur de la co-traitance (cotraitance-crypto.js) : revue par lecture, non testée dynamiquement.
- Hors périmètre de cet audit code : pentest externe (réseau/DNS/TLS réels), tenue en charge (pool de threads vs pool de connexions), et la suite pytest du dépôt (non lancée, consigne respectée — tous les tests étaient des scripts isolés en SQLite dédiée).

## Décisions qui reviennent au fondateur

- Session issue de l'email : imposer que le lien de confirmation ne vaille JAMAIS une session (jeton à usage unique, expiration courte), et décider si une session doit même exiger l'email vérifié au préalable.
- Compte démonstration en production : le garder comme vitrine publique, ou le restreindre — a minima lui interdire l'envoi d'emails d'invitation et les actions coûteuses (imports lourds). C'est un choix produit vs exposition.
- Accord de non-rétention (ZDR) avec le fournisseur IA (Anthropic/Mistral) : le signer pour pouvoir tenir la promesse « non-rétention », ou adoucir la formulation de la page sécurité.
- Rétention du journal d'audit et des adresses email/IP : fixer une durée (ex. 6 mois, cohérente avec la politique de confidentialité) et une purge, plutôt qu'une conservation sans limite.
- Chiffrement applicatif des sauvegardes : décider de détenir une clé hors Railway/stockage (meilleure protection, mais à conserver précieusement pour pouvoir restaurer).
- 2FA pour les comptes (notamment propriétaires d'organisation) : à arbitrer selon le public PME.
- Overage : exiger une carte enregistrée avant d'autoriser le paiement à l'usage, pour ne jamais offrir d'IA non facturable.

## Trouvailles rejetées après vérification : 50

Rejetées par le réfutateur et non reproduites (détail dans cyber_result.json du scratchpad de session).
## Statut au 8 octobre 2026 — vagues 1 et 2 corrigées

Les vagues 1 et 2 sont corrigées. Chaque contournement a été rejoué après correctif, puis une contre-vérification finale a été faite. Elle a relevé deux bloquants, corrigés eux aussi :
- le changement d'adresse pouvait envoyer des emails sans limite ;
- la démo collectivités pouvait déclencher l'IA payante.

La suite complète passe, y compris sous Python 3.12 avec les versions épinglées de production (`requirements.txt`). Les tests de non-régression sont dans `tests/test_secu*.py`.

Corrigé lors de la passe finale (`tests/test_secu4_final.py`) :
- **Changement d'adresse.** 5 emails de confirmation au plus par compte et par jour, et 10 changements de profil par heure. Le prénom est échappé dans les emails et borné à 120 caractères.
- **Démo collectivités.** Pas de rédaction par l'IA. Le sourcing reste disponible, sans les conseils rédigés par l'IA.
- **Notifications de groupement.**
  - Elles ne partent jamais vers une adresse non confirmée.
  - Une notification au plus par invitation toutes les 30 minutes.
  - Les codes envoyés aux invités sont plafonnés par organisation.
  - Le mail de révocation et l'invitation d'équipe exigent un expéditeur confirmé.
- **PDF.**
  - Le contenu de chaque page (flux et formulaires) est mesuré avant l'analyse : une page de plus de 2 Mo est sautée, et le dossier entier est plafonné à 12 Mo.
  - Chaque page dispose d'une tranche de temps, contrôlée à chaque opérateur, y compris dans les formulaires appelés en boucle.
  - Le pire cas mesuré passe de plus de 70 s et 1,4 Go à environ 15 s et 190 Mo.
- **Effacement RGPD.** Un marché sur lequel une autre entreprise a des entrées chaînées devient une pierre tombale vide. Sa chaîne reste intacte.
- **Intégrité.** Une chaîne héritée est bornée au dernier transfert sortant, ce qui couvre les allers-retours de propriété.
- **Coffre-fort.**
  - Restaurer une ancienne version restaure la version courante.
  - La purge détache une ancienne version restaurée au lieu de l'effacer.
  - Deux remplacements simultanés ne créent plus deux versions courantes : le second reçoit un 409.
- **Liens.** `source_url` est assaini à la lecture des marchés et à l'écriture des signaux amont.

Résiduels acceptés (faibles) :
- Environ 59 Mo de petites parties multipart sont analysés en mémoire avant l'authentification, sur les 7 routes d'upload.
- Les alertes quotidiennes partent vers `user.email` même non confirmé. C'est volontaire, pour ne pas couper les alertes des membres d'équipe.
- Un compte effacé et anonymisé, ancien propriétaire, est vérifié sur toute sa chaîne. Il peut révéler un nombre d'entrées d'une autre entreprise.
- Un PDF hostile peut encore occuper environ 15 s d'un thread de travail. C'est borné, et limité à 30 envois par heure et par IP.

## Vague 3 — faite et en production le 8 octobre 2026

Quatre lots, développés en parallèle puis fusionnés. La suite passe en entier sous Python 3.12 avec les versions verrouillées de production (`requirements.lock`).
- **Dépendances (rang 16).**
  - Avant le lot, pip-audit relevait 64 failles dans 7 paquets. Il en reste 2, sans correctif publié et sans effet dans notre usage (python-jose, ecdsa), justifiées dans `docs/DEPENDANCES.md`.
  - Paquets montés : starlette 1.3, fastapi 0.133, python-multipart 0.0.31, python-jose 3.5, pillow 12.3, pypdf 6.19, sentry-sdk 2.56.
  - `requirements.lock` avec hachages, installé avec `--require-hashes` dans le Dockerfile, et pip-audit en CI chaque semaine.
  - Effet de bord : depuis fastapi 0.132, un JSON envoyé sans en-tête Content-Type reçoit un 422.
- **Durcissement (rang 18 et suivants).**
  - Connexion Google :
    - `state` lié au navigateur par un cookie HttpOnly ;
    - le jeton de session ne passe plus dans l'URL : code d'échange à usage unique de 60 s, dans le fragment.
  - Journaux et Sentry :
    - jetons d'invitation, JWT et emails masqués ;
    - `send_default_pii=False`, cookies et en-tête Authorization retirés.
  - PDF reportlab : toutes les valeurs dynamiques sont échappées (DUME, DPGF, compte-rendu).
  - Type MIME dérivé de l'extension à l'envoi comme au téléchargement, avec `nosniff` et `attachment`.
- **Sauvegardes chiffrées (rang 13).**
  - Chiffrement hybride X25519 + AES-256-GCM, par blocs authentifiés, avec une clé publique (`BACKUP_PUBLIC_KEY`). La clé privée est générée par `scripts/backup_keygen.py` et reste hors ligne.
  - Restauration avec `scripts/backup_decrypt.py`.
  - Sans clé, la sauvegarde part comme avant, avec un avertissement.
- **Ancrage du journal.**
  - Cron quotidien `POST /api/admin/run-audit-anchor` : têtes de toutes les chaînes, engagement chaîné de jour en jour, horodatage RFC 3161 par une autorité publique (freetsa.org par défaut).
  - Stockage dans `anchors/` (R2), plus une copie par email si `ANCHOR_EMAIL` est définie.
  - La vérification d'intégrité détecte maintenant la disparition des dernières entrées.
  - Exception : l'effacement RGPD légitime d'un compte n'est jamais signalé.

À faire par Eliot pour activer :
1. Générer la clé avec `python scripts/backup_keygen.py`, ranger la clé privée hors ligne, poser `BACKUP_PUBLIC_KEY` dans Railway, puis tester une restauration.
2. Créer le cron `run-audit-anchor`. Poser `ANCHOR_EMAIL` est facultatif.
3. Ensuite seulement, mettre à jour les phrases de la page sécurité §2 et §4. La procédure est dans `docs/GO_LIVE.md`.

Restent ouverts :
- la vérification de bout en bout de la connexion Google avec un vrai compte ;
- le remplacement de python-jose par PyJWT, à décider ;
- la chaîne « système » (entrées sans `owner_id`), qui n'est pas ancrée ;
- 2FA et durée de rétention du journal, décisions fondateur toujours ouvertes.
