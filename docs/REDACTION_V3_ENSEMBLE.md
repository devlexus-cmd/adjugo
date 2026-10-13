# Rédaction, vague 3 — l'ensemble : I, E1 et A sur le socle « Mes preuves »

Étude « rédaction », § 6.5 à 6.7, doctrine § 7, § 8 (V3), décisions 7 et 8. Ce document dit comment les
quatre morceaux de la vague 3 se branchent les uns sur les autres. Le détail de chacun est dans son
contrat :

| morceau | ce qu'il fait | contrat |
|---|---|---|
| socle | le modèle `preuves`, les règles, les routes `/api/preuves` | `docs/REDACTION_V3_PREUVES.md` |
| I « Partir de vos anciens dossiers » | lit un ancien document une fois et PROPOSE des fiches avec leur passage exact | `docs/REDACTION_V3_IMPORT.md` |
| E1 « Mes preuves » | les écrans, la reprise du profil, « Insérer une fiche » dans l'atelier | `docs/REDACTION_V3_E1_ECRANS.md` |
| A « Chaque fait a sa source » | faits numérotés remis à l'IA, contrôle sans IA phrase par phrase, libellés | `docs/REDACTION_V3_SOURCES.md` |

Migration : une seule, `v6w7preuves` (après `u5v6essaigardefou`, la tête de la production). I, E1 et A
n'en ajoutent aucune.

## 1. Le parcours d'une TPE

Test de bout en bout : `tests/test_redaction_v3_ensemble.py`.

1. **« Mon savoir-faire »** : elle importe un ancien mémoire. « Proposer des fiches » (I) lit le
   document une fois et propose des fiches, chacune avec son passage. Elles sont enregistrées avec le
   statut « proposée ». Elle coche celles qui sont justes (routes du socle `accepter` / `retirer`), ici
   ou dans « Mes preuves ». Le lien « Les fiches cochées rejoignent « Mes preuves » » mène à l'écran
   E1.
2. **« Mes preuves »** (E1, sous « Mon entreprise ») : elle reprend ce qu'elle a déjà saisi (profil,
   réseau, justificatifs du coffre-fort) et ajoute ce qui manque (« déclaré par vous » par défaut).
   Les propositions d'I s'y cochent aussi.
3. **Atelier** (A) : « Rédiger avec Adjugo » remet à l'IA les preuves UTILISABLES (`pv.faits_autorises`)
   en `[F#]`, avec leur type de source ; le reste du profil en `[P#]` / `[E#]`, le chiffrage en `[C#]`,
   les extraits en `[S#]`. Le contrôle relie chaque fait à sa source, sans IA.
4. **Libellés** : « trouvé dans vos documents » (lien vers le passage), « justificatif déposé »,
   « déclaré par vous », « source publique », « votre estimation ». Jamais « vérifié ».
5. **« Insérer une fiche »** (E1) recopie une fiche telle quelle ; le contrôle (A, texte écrit par vous)
   relie ses faits à la fiche. **« Ajouter une source »** (A) relie un fait à une preuve qui le
   contient ou le déclare dans « Mes preuves » ; pour un passage ou un justificatif, le lien
   « ouvrir « Mes preuves » » y mène, puis « Recontrôler ».
6. **Export Word** : aucun renvoi `[F#]`, `[P#]`, `[CV F#]`, aucun libellé interne.

Ce qui devient un fait `[F#]` : une preuve ACCEPTÉE (cochée après I, saisie ou reprise dans E1, déclarée
par « Ajouter une source »), de l'organisation, encore valable, dont le document existe encore. Une
proposition (I) n'est jamais remise tant qu'elle n'est pas cochée. Une preuve retirée, expirée, ou dont
le document a disparu ne l'est plus. Un texte déjà rédigé qui s'y appuyait la montre « à relire » dès
la lecture, et l'export est bloqué.

## 2. Règles d'assemblage (ajoutées en réunissant les morceaux)

- **« Mes preuves » gouverne le profil une fois repris.** Un élément du profil a parfois sa fiche du
  même intitulé, acceptée (quelle que soit son origine), ou retirée alors que c'était la déclaration de
  l'utilisateur lui-même (reprise du profil ou saisie dans « Mes preuves » : origine `profil` ou `saisie`)
  (`preuves_reprise.cles_gerees`). C'est le cas d'une personne,
  d'une référence, d'une qualification, de l'effectif ou d'un chiffre d'affaires. L'atelier ne le
  remet alors plus depuis le profil (`atelier.Contexte.fiches`), et sa fiche décide :
  - utilisable : remise en `[F#]` ;
  - retirée ou expirée : rien n'est remis.

  On évite ainsi deux lignes pour le même fait (économie d'IA sans perte). On évite aussi qu'une
  fiche retirée ou expirée revienne par le profil. Une personne reprise n'est plus remise que par sa
  fonction. Sa qualification et ses chantiers font partie de son CV : ils ne partent plus à l'IA
  (décision 8a). Une fiche seulement PROPOSÉE ne gouverne rien : la déclaration du profil reste remise
  tant que l'utilisateur n'a pas coché. Une proposition d'un ancien dossier ÉCARTÉE (« Retirer »,
  acceptée avant ou non) ne gouverne rien non plus : « Effectif : 8 » d'un mémoire de 2019 retiré, l'effectif
  de 12 du profil reste remis en `[P#]`, et la reprise le propose encore (`preuves_reprise._existant`).
  Le profil lui-même n'est jamais modifié.
- **Une qualification du profil expirée** (date d'expiration dépassée, jour de Paris) n'est pas
  remise.
- **Un seul format de CV.** Il y a deux façons d'insérer un CV :
  - « [CV F2] », écrit par l'IA (A) ;
  - « Insérer une fiche » (E1).

  Dans les deux cas, ce sont les mêmes lignes (`preuves_atelier.lignes_cv`). Le garde-fou de
  « Raccourcir » (`preuves_atelier.refuser_cv_pour_ia`, 409 `cv_dans_la_partie`) les reconnaît donc
  toutes les deux. Il agit avant tout appel et tout débit, même pour une fiche qui n'a que des
  qualifications.

## 3. Ce qui reste fermé, et pourquoi

- **Libellés positifs et compteur « Faits avec une source : 7 sur 8 »** : `ATELIER_LIBELLES_SOURCES=1`,
  éteint par défaut. Le jeu de 60 phrases piégées passe : aucune n'est présentée comme « trouvé dans
  vos documents », et c'est vérifié en CI. Il reste la mesure des fausses alertes sur 20 vrais
  mémoires, avec l'accord écrit des PME. C'est à Mathys de la faire :
  `scripts/mesure_fausses_alertes.py preparer` / `bilan`. L'objectif est de moins d'une fausse alerte
  par page. Tant que la mesure n'est pas faite, l'atelier garde l'affichage d'A0 (« à relire »
  seulement).
- Les écrans de « Mes preuves » et les fiches proposées par I montrent le libellé de la source d'une
  fiche, par exemple « trouvé dans vos documents : Mémoire 2024.pdf ». Ils disent où la fiche a été
  trouvée. Ils ne disent rien d'une phrase du mémoire.

## 4. À faire ensuite

- Mathys : la mesure des fausses alertes, puis allumer les libellés si l'objectif est atteint. Sinon,
  on ne les allume pas, et on ne baisse pas l'exigence sans le dire.
- Vague 4 : les preuves d'un partenaire, `proprietaire_kind = invitation`, déjà prévu dans le socle.
  Côté chef de file, le compteur « 6 faits trouvés dans les documents du couvreur ».
- Vague 5 (E2) : « Retrouver mes marchés publics » (DECP, titulaires 1 à 3), proposé puis coché
  (décision 7b), avec l'origine `import_public`. Ensuite, les qualifications RGE.
