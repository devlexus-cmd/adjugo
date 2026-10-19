"""
L'ENTRETIEN CHANTIER : « Adjugo demande au lieu de deviner » (rédaction, vague 5 — D de l'étude, § 6.9).

Contrat : docs/REDACTION_V5.md (section D). Ce module est le SEUL point d'écriture de l'entretien (table
entretien_questions) ; les routeurs ne font que contrôler l'accès et traduire les erreurs (`AtelierError`).

Ce que fait l'entretien, SANS IA :
  • avant la rédaction des parties notées, « n questions sur ce chantier » (8 au plus) tirées de la banque
    (app/services/entretien_banque.py, environ 40 questions BTP), déclenchées par des mots du dossier de
    l'acheteur ; chaque question montre la PHRASE du dossier qui la motive, retrouvée mot pour mot
    (citation_guard) ; une phrase niée (« aucune présence d'amiante ») ne déclenche rien ;
  • classées par le poids, TEL QU'ÉCRIT dans « Comment vous serez noté », du critère qu'elles concernent :
    d'abord la meilleure question de chaque critère (du plus lourd au plus léger), puis les suivantes ;
    l'environnement déclenche toujours une question (§ 6.9) ;
  • « Qui sera le chef de chantier ? » propose la liste « Équipe » de « Mes preuves » : la fiche choisie est
    un fait dont le nom est masqué avant l'IA (étiquette) et dont le CV n'est jamais remis à l'IA ;
  • les réponses forment la FICHE CHANTIER : des faits « déclaré par vous » numérotés [R3] (numéro STABLE dans
    le dossier, jamais réutilisé) remis à l'IA et au contrôle des faits de l'atelier (faits_sources) ;
  • une question PASSÉE laisse « [À compléter : … ] » dans la PARTIE CONCERNÉE (consigne de l'IA, puis contrôle
    sans IA : le passage est ajouté s'il manque), jamais un texte de remplissage ; une question encore sans
    réponse : l'IA n'écrit aucun fait à son sujet et laisse le même passage si la partie doit en parler (l'écran
    prévient avant de rédiger) ; « Sans objet sur ce chantier » ne laisse rien.

Avec l'IA, en option (bouton, compte sur le plafond de l'atelier — décision 6a, comme « Harmoniser le ton ») :
quelques questions SUPPLÉMENTAIRES, chacune gardée seulement si sa phrase du dossier est retrouvée mot pour
mot (citation_guard), sans nombre absent de cette phrase ; rien de retenu ou IA en panne : rien n'est décompté.
`tenant_scope` (espace facturé du chef de file) et `pii_scope` posés sur l'appel.

Groupement (vague 4, cloisonnement intact) : une question qui relève du lot d'un partenaire (ou de la partie
qui lui est confiée) lui est ADRESSÉE ; elle est posée dans SON espace (lien + clé, ou compte), il y répond
chez lui (même exigence d'identité qu'un envoi), et le chef de file lit la réponse comme un fait « déclaré par
votre partenaire » (T_PARTENAIRE : il n'appuie qu'une phrase qui nomme ce partenaire). Sa réponse est SA
donnée : le chef de file ne la modifie pas, elle sort de la fiche chantier si la question est adressée à un
autre, et elle est effacée au retrait ou au déclin de son invitation. L'IA du partenaire ne reçoit que SES
réponses ; jamais celles du chef de file.
"""
import hashlib
import json
import logging
import re
from collections import OrderedDict, defaultdict
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.models import DossierPresentation, DossierSection, EntretienQuestion, Job, Project, ProjectInvite, User, utcnow
from app.services import atelier as at
from app.services import dce_pieces as dp
from app.services import faits_sources as fs
from app.services import entretien_banque as eb

logger = logging.getLogger("adjugo")

AtelierError = at.AtelierError

# ── Vocabulaire ───────────────────────────────────────────────────────────────────────

MAX_QUESTIONS = 8             # questions de la banque (§ 6.9 : 8 au plus)
MAX_IA = 4                    # questions supplémentaires proposées par l'IA, au plus
REPONSE_MAX = 1500
QUESTION_MAX = 300
MOTIF_MAX = 400
IA_DOSSIER_MAX = 60000        # caractères du dossier de l'acheteur remis à l'IA (option)

A_REPONDRE, REPONDUE, SAUTEE, SANS_OBJET = "a_repondre", "repondue", "sautee", "sans_objet"
STATUTS = {A_REPONDRE: "À répondre", REPONDUE: "Répondue", SAUTEE: "Passée", SANS_OBJET: "Sans objet"}
BANQUE, IA = "banque", "ia"
ORG, INV = at.AUTEUR_ORG, at.AUTEUR_INVITATION
PROPOSE, MANUEL = "propose", "manuel"
JOB_ENTRETIEN = at.JOB_ENTRETIEN

LIB_ORIGINE = {BANQUE: "Posée par Adjugo d'après le dossier, sans IA",
               IA: "Proposée par Adjugo avec l'IA, d'après une phrase du dossier"}
MSG_SANS_MOTIF = "Question posée pour tout chantier : aucune phrase du dossier lu n'en parle."
MSG_SANS_DCE = ("Aucun dossier du marché importé : Adjugo ne peut pas repérer les contraintes du chantier. Importez-le "
                "pour recevoir les questions qui le concernent.")
BULLE = ("Adjugo cherche dans le dossier de l'acheteur, sans IA, les contraintes du chantier qui méritent une réponse "
         "précise : site occupé, école, travaux de nuit, amiante, voirie, phasage, déchets… Chaque question montre la "
         "phrase du dossier qui la motive. Vos réponses forment la fiche chantier : Adjugo s'en sert pour rédiger, comme "
         "des faits « déclaré par vous ». Une question passée laisse « [À compléter] » dans la partie concernée.")
BULLE_EQUIPE = ("Choisissez une personne de « Mes preuves » (rubrique Équipe) : son nom n'est jamais envoyé à l'IA, et son "
                "CV s'insère tel quel dans le dossier. Vous pouvez aussi écrire la réponse.")
BULLE_IA = ("Adjugo demande à l'IA d'autres questions sur ce chantier. Une question n'est gardée que si la phrase du "
            "dossier qui la motive y est retrouvée mot pour mot. Cela compte comme une refonte du dossier ; si rien "
            "n'est retenu, rien n'est décompté.")
AVERTISSEMENT_REPONSE = ("Votre réponse sera lue par le chef de file, qui s'en servira pour rédiger le dossier commun "
                         "comme un fait déclaré par votre entreprise.")
MSG_PARTENAIRE = ("Le chef de file vous pose ces questions sur le chantier. Vos réponses servent à rédiger le dossier "
                  "commun ; elles comptent comme déclarées par votre entreprise.")
MSG_QUESTION_PARTENAIRE = "Cette question est posée à {nom} : il y répond depuis son espace. Reprenez-la pour y répondre vous-même."
MSG_IA_PANNE = ("La recherche de questions n'a pas abouti : le service d'IA est indisponible pour le moment. Rien n'a "
                "été décompté.")


def _flat(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _iso(dt) -> Optional[str]:
    return at._iso(dt)


def _fold(s) -> str:
    return dp.fold(str(s or ""))


def _debut(texte_replie: str, stem: str) -> bool:
    """`stem` (replié, éventuellement plusieurs mots) au début d'un mot de `texte_replie`."""
    if not stem:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(stem), texte_replie) is not None


# ── Le dossier de l'acheteur, pièce par pièce (lecture déjà faite, sans IA) ────────────

# Ordre de recherche de la phrase qui motive une question : le cadre de réponse (ce que l'acheteur demande),
# le CCTP (les contraintes du site), le règlement, le CCAP, les autres pièces ; jamais d'abord un bordereau.
_ORDRE = {dp.CADRE: 0, dp.CCTP: 1, dp.REGLEMENT: 2, dp.CCAP: 3, dp.AUTRE: 4, dp.ACTE_ENGAGEMENT: 5, dp.BORDEREAU: 6}


def pieces_du_marche(db, project: Project, member_ids: list) -> tuple:
    """([{type, libelle, nom, texte}], clé de lecture). Lecture intégrale rangée si elle existe (toutes les
    pièces lues), sinon l'ancienne lecture bornée, sinon l'extrait de l'analyse ; ([], "") sans dossier."""
    try:
        lu = at.lire_dossier_acheteur(db, project, member_ids)
    except Exception as e:      # noqa: BLE001 — l'entretien ne casse jamais l'atelier
        logger.warning("entretien : dossier du marché illisible (projet %s) : %s", project.id, type(e).__name__)
        return [], ""
    pieces = []
    if lu.get("integral"):
        from app.services import dce_texte
        try:
            payload = dce_texte.charger(project)
        except Exception:       # noqa: BLE001
            payload = None
        for p in (payload or {}).get("pieces") or []:
            t = p.get("texte") or ""
            if t.strip():
                k = p.get("type") or dp.AUTRE
                pieces.append({"type": k, "libelle": p.get("libelle") or dp.label(k), "nom": p.get("nom") or "",
                               "texte": t})
        if not pieces:
            lu = at.lire_dossier_acheteur(db, project, member_ids, integrale=False)
    if not pieces and (lu.get("texte") or "").strip():
        for p in dp.typed_pieces(lu["texte"]):
            if (p.get("texte") or "").strip():
                pieces.append({"type": p["type"], "libelle": p["libelle"], "nom": p.get("nom") or "",
                               "texte": p["texte"]})
    pieces.sort(key=lambda p: _ORDRE.get(p["type"], 4))
    return pieces, f"{lu.get('cle') or ''}|{lu.get('lecture_cle') or ''}"


# ── Déclenchement sans IA ─────────────────────────────────────────────────────────────

_RX = {}
# Une phrase qui NIE ce qu'elle nomme (« aucune présence d'amiante », « sans travaux de nuit », « les travaux de nuit
# ne sont pas prévus ») ne déclenche rien.
_NEG = re.compile(r"(?:\bpas d[e']\s?|\baucune?\b|\babsence d[e']\s?|\bsans\b|\bni\b|\bnon\b|\bexclu\w*)[^.;:!?\n]{0,30}$")
_NEG_APRES = re.compile(r"^[^.;:!?\n]{0,40}?\b(?:ne|n')\s?(?:\w+\s){0,2}?(?:pas|jamais|aucun\w*|plus)\b")
_MOTS_PHRASE = 4              # une vraie phrase (préférée) ; à défaut une ligne courte (un critère, un intitulé)
_MOTS_LIGNE = 2
_NUMEROTATION = re.compile(r"^\s*(?:#{1,6}\s*)?(?:(?:article|art\.|chapitre|titre|section)\s*[\dIVXivx]+[\d.]*|"
                           r"\d+(?:\.\d+)*)\s*[-–—:.)]?\s*", re.IGNORECASE)
_FIN = re.compile(r"[.!?](?=\s|$)")
_TITRE = re.compile(r"^\s*(?:#{1,6}\s|(?:article|art\.|chapitre|titre|section)\s*[\dIVXivx]+\b|\d+(?:\.\d+)*\s+\S)",
                    re.IGNORECASE)
LIGNE_COURTE = 60             # une ligne plus courte, sans ponctuation finale, est un intitulé (pas un retour de ligne)


def _mots(phrase: str) -> int:
    """Mots d'une phrase, sans sa numérotation (« Article 2 - Amiante » : un mot)."""
    return len(re.findall(r"[^\W\d_]{2,}", _NUMEROTATION.sub("", phrase or "", count=1)))


def _est_titre(ligne: str) -> bool:
    """Un intitulé, un critère, une question numérotée : une ligne courte sans ponctuation finale, ou numérotée."""
    x = (ligne or "").strip()
    if not x:
        return False
    return bool(_TITRE.match(x)) or (len(x) < LIGNE_COURTE and not re.search(r"[.;:!?,]$", x))


def _dernier(rx, t: str, a: int, b: int):
    m = None
    for m in rx.finditer(t, a, b):
        pass
    return m


def phrase_du_dossier(t: str, a: int, b: int, max_len: int = MOTIF_MAX - 20) -> tuple:
    """(phrase, est_un_intitulé) autour de [a, b) dans le texte d'une pièce. Un texte lu dans un PDF a ses retours
    à la ligne au milieu des phrases : une phrase va de la fin de la précédente (« . », « ! », « ? ») à sa propre
    fin, à travers les retours de ligne, sans traverser un intitulé ni une ligne vide. Une ligne qui est elle-même
    un intitulé (« Moyens humains et encadrement : 10 % ») est rendue seule. Trop longue : coupée autour du mot, sur
    des mots entiers. Une suite exacte du texte (blancs réduits) : vérifiable par citation_guard."""
    ls = t.rfind("\n", 0, a) + 1
    le = t.find("\n", b)
    le = len(t) if le < 0 else le
    if _est_titre(t[ls:le]):
        return re.sub(r"\s+", " ", t[ls:le]).strip(), True
    # Début : la fin de la phrase précédente, sans remonter au-delà d'un intitulé ou d'une ligne vide.
    m = _dernier(_FIN, t, ls, a)
    debut = m.end() if m is not None else ls
    i = ls
    while m is None and i > 0:
        ps = t.rfind("\n", 0, i - 1) + 1
        prec = t[ps:i - 1]
        if not prec.strip() or _est_titre(prec) or re.search(r"[.!?]\s*$", prec) or a - ps > max_len:
            break
        m = _dernier(_FIN, t, ps, i - 1)
        debut = m.end() if m is not None else ps
        i = ps
    # Fin : la fin de CETTE phrase, à travers les retours de ligne, jusqu'à un intitulé ou une ligne vide.
    fin, j = None, b
    while fin is None:
        e = t.find("\n", j)
        e = len(t) if e < 0 else e
        mm = _FIN.search(t, j, e)
        if mm is not None:
            fin = mm.end()
        elif e >= len(t):
            fin = e
        else:
            ns = e + 1
            ne = t.find("\n", ns)
            ne = len(t) if ne < 0 else ne
            if not t[ns:ne].strip() or _est_titre(t[ns:ne]) or ne - b > max_len:
                fin = e
            j = ns
    gauche = re.sub(r"\s+", " ", t[debut:a]).lstrip(" ;:")
    mot = re.sub(r"\s+", " ", t[a:b])
    droite = re.sub(r"\s+", " ", t[b:fin]).rstrip(" ;:")
    if len(gauche) + len(mot) + len(droite) > max_len:
        place = max(0, max_len - len(mot))
        d = min(len(droite), max(place // 2, place - len(gauche)))
        g = min(len(gauche), place - d)
        g_coupe, d_coupe = gauche[len(gauche) - g:], droite[:d]
        if g < len(gauche) and " " in g_coupe:
            g_coupe = g_coupe[g_coupe.index(" ") + 1:]
        if d < len(droite) and " " in d_coupe:
            d_coupe = d_coupe[:d_coupe.rindex(" ")]
        gauche, droite = g_coupe, d_coupe
    return (gauche + mot + droite).strip(), False


def _rx(q: dict):
    r = _RX.get(q["code"])
    if r is None:
        r = re.compile("|".join(f"(?:{x})" for x in q["declencheurs"]))
        _RX[q["code"]] = r
    return r


def _trouver(q: dict, pieces: list, deja=()) -> Optional[dict]:
    """La phrase du dossier qui motive la question : autour du premier mot déclencheur trouvé (pièces dans
    l'ordre de `_ORDRE`), retrouvée MOT POUR MOT dans sa pièce (citation_guard) ; une vraie phrase plutôt qu'une
    ligne courte, et une phrase que ne montre pas déjà une question plus prioritaire (`deja`) quand le dossier
    en a une autre ; None si aucune."""
    from app.services.analysis import citation_guard
    rx = _rx(q)
    repli = repli_deja = None
    for p in pieces:
        t = p["texte"]
        f = p.get("_fold")
        if f is None:
            f = p["_fold"] = _fold(t)
        for i, m in enumerate(rx.finditer(f)):
            if i >= 30:
                break
            if _NEG.search(f[max(0, m.start() - 45):m.start()]) or _NEG_APRES.search(f[m.end():m.end() + 60]):
                continue
            brut, titre = phrase_du_dossier(t, m.start(), m.end())
            phrase = citation_guard(t, brut, min_len=12)
            if not phrase:
                continue
            n = _mots(phrase)
            if n < _MOTS_LIGNE:
                continue                    # un intitulé d'un mot (« Article 2 - Amiante ») ne motive rien
            x = {"phrase": phrase[:MOTIF_MAX], "piece": (p.get("libelle") or dp.label(p["type"]))[:200]}
            if x["phrase"] in deja:
                repli_deja = repli_deja or x
                continue
            if not titre and n >= _MOTS_PHRASE:
                return x
            repli = repli or x
    return repli or repli_deja


def lignes_grille(project: Project) -> list:
    """Les critères techniques de « Comment vous serez noté » (le prix à part), avec leur poids TEL QU'ÉCRIT
    et sa valeur pour classer (0 sans poids écrit)."""
    from app.services import atelier_plan as ap
    from app.services import grille_notation as gn
    try:
        lignes = ap.lignes_techniques(at._analysis(project))
    except Exception:       # noqa: BLE001
        return []
    out = []
    for ln in lignes:
        w = gn.parse_weight(ln.get("poids")) if ln.get("poids") else None
        out.append(dict(ln, _fold=_fold(ln.get("critere")), _w=float(w["valeur"]) if w else 0.0))
    return out


def _critere_de(stems: list, lignes: list) -> Optional[dict]:
    """Le critère que la question concerne : le PREMIER début de mot de la question qui se retrouve dans un
    critère (le plus lourd s'il y en a plusieurs) ; sinon le critère unique, ou le seul critère « technique »."""
    for stem in stems or []:
        hits = [ln for ln in lignes if _debut(ln["_fold"], stem)]
        if hits:
            return max(hits, key=lambda x: x["_w"])
    if len(lignes) == 1:
        return lignes[0]
    gen = [ln for ln in lignes if re.search(r"(?<![a-z])(?:valeur technique|technique|memoire)", ln["_fold"])]
    return gen[0] if len(gen) == 1 else None


def _texte_partie(s: DossierSection) -> str:
    return _fold(" ".join([s.intitule or "", s.critere or "", (s.question or "")[:600]]
                          + [str(p.get("intitule") or "") for p in (s.parents or []) if isinstance(p, dict)]))


_GENERIQUES_IA = {"chantier", "travaux", "comment", "quelle", "quelles", "quels", "votre", "vous", "entreprise",
                  "dossier", "pendant", "prevoyez", "organisez", "proposez", "marche", "cette", "ouvrage", "ouvrages"}


def _stems_libres(*textes) -> list:
    """Débuts de mots (6 lettres) d'une question proposée par l'IA, pour trouver sa partie et son lot."""
    out = []
    for w in re.findall(r"[a-z]{5,}", _fold(" ".join(str(t or "") for t in textes))):
        if w not in _GENERIQUES_IA and w[:6] not in out:
            out.append(w[:6])
    return out[:12]


def partie_concernee(stems: list, sections: list, ligne: Optional[dict]) -> Optional[DossierSection]:
    """La partie du plan qui reçoit la réponse (ou « [À compléter] ») : celle où se retrouvent le mieux les
    débuts de mots de la question (le premier de la liste compte le plus) ; sinon celle du critère concerné ;
    sinon la première partie de méthode ou d'organisation ; sinon la première partie. Sans IA."""
    cands = [s for s in sections if not at.est_generee(s)]
    best, best_score = None, 0
    for s in cands:
        t = _texte_partie(s)
        idx = [i for i, st in enumerate(stems or []) if _debut(t, st)]
        if not idx:
            continue
        score = (len(stems) - min(idx)) * 10 + len(idx)
        if score > best_score:
            best, best_score = s, score
    if best is not None:
        return best
    if ligne:
        s = next((s for s in cands if s.critere_id and s.critere_id == ligne.get("id")), None)
        if s is not None:
            return s
    gen = next((s for s in cands if re.search(r"(?<![a-z])(?:methodolog|technique|organis|memoire)", _texte_partie(s))),
               None)
    return gen or (cands[0] if cands else None)


_CACHE = OrderedDict()            # clé du dossier lu + grille → candidates (process unique, borné)
_CACHE_MAX = 32


def _cle_grille(lignes: list) -> str:
    return hashlib.sha256(json.dumps([[x.get("id"), x.get("critere"), x.get("poids")] for x in lignes],
                                     ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def candidates(pieces: list, lignes: list, cle: str = "") -> list:
    """Toutes les questions de la banque déclenchées par le dossier : [{q, prio, motif, ligne, w}] (sans IA)."""
    ck = f"{cle}|{_cle_grille(lignes)}" if cle else ""
    if ck and ck in _CACHE:
        _CACHE.move_to_end(ck)
        return list(_CACHE[ck])
    out, montrees = [], set()
    for prio, q in enumerate(eb.BANQUE):
        m = _trouver(q, pieces, montrees)
        if m is None:
            continue
        montrees.add(m["phrase"])
        ln = _critere_de(q["criteres"], lignes)
        out.append({"q": q, "prio": prio, "motif": m, "ligne": ln, "w": ln["_w"] if ln else 0.0})
    if ck:
        _CACHE[ck] = list(out)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
    return out


def selection(cands: list, lignes: list, n: int = MAX_QUESTIONS) -> list:
    """Les questions retenues, au plus `n`, classées par le poids du critère concerné : d'abord la meilleure
    question de chaque critère (du plus lourd au plus léger), puis la suivante de chacun, etc. ; à poids égal,
    l'ordre de la banque. L'environnement est toujours représenté : la meilleure question « environnement »
    déclenchée, sinon la question générale (sans phrase du dossier, et l'écran le dit)."""
    vus = defaultdict(int)
    for c in sorted(cands, key=lambda c: c["prio"]):
        g = (c["ligne"] or {}).get("id") or ""
        # Une question qu'aucun critère ne concerne passe après toutes celles qu'un critère concerne.
        c["passe"] = vus[g] if g else 100 + vus[g]
        vus[g] += 1
    ordre = sorted(cands, key=lambda c: (c["passe"], -c["w"], c["prio"]))
    out = ordre[:n]
    if n and not any(c["q"]["famille"] == eb.ENVIRONNEMENT for c in out):
        env = next((c for c in ordre if c["q"]["famille"] == eb.ENVIRONNEMENT), None)
        if env is None:
            q = eb.PAR_CODE["environnement"]
            ln = _critere_de(q["criteres"], lignes)
            env = {"q": q, "prio": eb.BANQUE.index(q), "motif": None, "ligne": ln, "w": ln["_w"] if ln else 0.0,
                   "passe": 0}
        out = (out[:n - 1] if len(out) >= n else out) + [env]
    out.sort(key=lambda c: (-c["w"], c["passe"], c["prio"]))
    return out


# ── Lecture : les questions enregistrées ──────────────────────────────────────────────

def lignes(db, dossier: DossierPresentation, actives: bool = True) -> list:
    q = db.query(EntretienQuestion).filter(EntretienQuestion.dossier_id == dossier.id)
    if actives:
        q = q.filter(EntretienQuestion.retiree_le.is_(None))
    return q.order_by(EntretienQuestion.ordre.asc(), EntretienQuestion.numero.asc()).all()


def prepare(db, dossier: Optional[DossierPresentation]) -> bool:
    if dossier is None:
        return False
    return db.query(EntretienQuestion.id).filter(EntretienQuestion.dossier_id == dossier.id).first() is not None


def _def(r: EntretienQuestion) -> dict:
    """La définition de la question (banque), ou celle d'une question proposée par l'IA (débuts de mots tirés
    de son texte)."""
    q = eb.PAR_CODE.get(r.code) if r.origine == BANQUE else None
    if q is not None:
        return q
    stems = _stems_libres(r.theme, r.question)
    return {"code": r.code, "theme": r.theme, "question": r.question or "", "criteres": stems, "parties": stems,
            "lots": stems, "a_completer": r.theme or "réponse à une question sur le chantier", "famille": "",
            "type_reponse": r.type_reponse or eb.TEXTE, "aide": ""}


def a_completer(r: EntretienQuestion) -> str:
    """« [À compléter : chef de chantier] » : ce que laisse une question sautée dans la partie concernée."""
    lab = _flat(_def(r).get("a_completer") or r.theme or "réponse à une question sur le chantier")[:120]
    return f"[À compléter : {lab}]"


# ── Qui répond : proposition (sans IA) et membres du groupement ──────────────────────

def _membres_ok(db, project: Project, dossier: DossierPresentation) -> list:
    """Les partenaires à qui une question peut être posée : membres du groupement qui peuvent rédiger, quand
    « Qui écrit quoi » est préparé (c'est là qu'ils ont leur espace de rédaction)."""
    from app.services import atelier_groupement as ag
    try:
        if not ag.repartition_active(db, dossier):
            return []
        return [m for m in ag.membres(db, project) if m.get("peut_rediger")]
    except Exception:       # noqa: BLE001 — sans groupement lisible, tout est posé au chef de file
        return []


def _proposition_adresse(d: dict, partie: Optional[DossierSection], membres: list) -> dict:
    """{type, invite_id, nom, message} : le partenaire à qui la partie concernée est confiée ; sinon celui dont
    le lot, et lui seul, correspond à la question ; sinon votre entreprise."""
    ok = {m["invite_id"]: m for m in membres}
    if partie is not None and partie.author_kind == INV and partie.author_invite_id in ok:
        m = ok[partie.author_invite_id]
        return {"type": INV, "invite_id": m["invite_id"], "nom": m["nom"],
                "message": f"Proposée à {m['nom']} : la partie « {_flat(partie.intitule)[:80]} » lui est confiée."}
    hits = []
    for m in membres:
        lot = _fold(m.get("lot") or "")
        if lot and any(_debut(lot, st) for st in d.get("lots") or []):
            hits.append(m)
    if len(hits) == 1:
        m = hits[0]
        return {"type": INV, "invite_id": m["invite_id"], "nom": m["nom"],
                "message": f"Proposée à {m['nom']} d'après son lot (« {_flat(m.get('lot'))[:80]} »)."}
    return {"type": ORG, "invite_id": None, "nom": "", "message": ("Posée à votre entreprise : plusieurs lots de "
                                                                  "partenaires correspondent." if len(hits) > 1
                                                                  else "Posée à votre entreprise.")}


def _noms_invitations(db, ids) -> dict:
    from app.services import atelier_groupement as ag
    out = {}
    for iid in {i for i in ids if i}:
        inv = db.get(ProjectInvite, iid)
        out[iid] = ag.nom_partenaire(inv, ag._contribution(db, iid)) if inv is not None else "Un partenaire"
    return out


def _invitation_active(db, invite_id) -> bool:
    from app.services import atelier_groupement as ag
    inv = db.get(ProjectInvite, invite_id) if invite_id else None
    return inv is not None and ag.peut_rediger(db, inv)[0]


# ── Préparer l'entretien (idempotent) ─────────────────────────────────────────────────

def _contexte(db, project: Project, dossier: DossierPresentation, member_ids: list) -> tuple:
    pieces, cle = pieces_du_marche(db, project, member_ids)
    lg = lignes_grille(project)
    secs = at.sections_actives(db, dossier)
    return pieces, cle, lg, secs


def proposition(db, project: Project, dossier: DossierPresentation, member_ids: list) -> list:
    """Les questions que l'entretien POSERAIT (rien n'est enregistré) : [{code, theme, question, …}]."""
    pieces, cle, lg, secs = _contexte(db, project, dossier, member_ids)
    membres = _membres_ok(db, project, dossier)
    out = []
    for c in selection(candidates(pieces, lg, cle), lg):
        q = c["q"]
        partie = partie_concernee(q["parties"], secs, c["ligne"])
        out.append({"code": q["code"], "theme": q["theme"], "question": q["question"], "type_reponse": q["type_reponse"],
                    "motif": c["motif"], "ligne": c["ligne"], "partie": partie,
                    "adresse": _proposition_adresse(q, partie, membres)})
    return out


def _prochain_numero(db, dossier_id: int) -> int:
    from sqlalchemy import func
    n = db.query(func.max(EntretienQuestion.numero)).filter(EntretienQuestion.dossier_id == dossier_id).scalar()
    return int(n or 0) + 1


def preparer(db, project: Project, dossier: DossierPresentation, lecteur: at.Lecteur, member_ids: list) -> dict:
    """Enregistre l'entretien (idempotent, sans IA, sans débit) : une ligne par question proposée ; une question
    déjà posée garde son numéro et sa réponse ; une question de la banque qui n'est plus proposée (dossier
    réimporté) et sans réponse est retirée (gardée, numéro réservé) ; le destinataire d'une question sans
    réponse, jamais choisi à la main, est proposé de nouveau (« Qui écrit quoi » a pu changer).
    Renvoie {creees, retirees, reproposees}."""
    for _essai in range(3):
        try:
            return _preparer(db, project, dossier, member_ids)
        except IntegrityError:          # une autre requête a préparé au même instant : on relit
            db.rollback()
    raise AtelierError(409, "reessayer", "L'entretien a été préparé au même moment : réessayez.")


def _preparer(db, project: Project, dossier: DossierPresentation, member_ids: list) -> dict:
    D = DossierPresentation
    db.query(D).filter(D.id == dossier.id).with_for_update().first()     # numérotation sérialisée
    props = proposition(db, project, dossier, member_ids)
    rows = {r.code: r for r in db.query(EntretienQuestion).filter(EntretienQuestion.dossier_id == dossier.id).all()}
    now = utcnow()
    creees = retirees = reproposees = 0
    num = _prochain_numero(db, dossier.id)
    gardes = set()
    for i, p in enumerate(props):
        gardes.add(p["code"])
        r = rows.get(p["code"])
        motif = p["motif"] or {}
        ad = p["adresse"]
        if r is None:
            r = EntretienQuestion(dossier_id=dossier.id, project_id=project.id, owner_id=dossier.owner_id, numero=num,
                                  code=p["code"], origine=BANQUE, theme=p["theme"][:160], question=p["question"][:QUESTION_MAX],
                                  type_reponse=p["type_reponse"], motif=(motif.get("phrase") or "")[:MOTIF_MAX] or None,
                                  motif_piece=(motif.get("piece") or "")[:200], ordre=i, adresse_kind=ad["type"],
                                  adresse_invite_id=ad["invite_id"], adresse_choix=PROPOSE, statut=A_REPONDRE)
            db.add(r)
            db.flush()
            num += 1
            creees += 1
            continue
        r.ordre = i
        if r.retiree_le is not None and r.statut == A_REPONDRE:
            r.retiree_le = None
        if r.statut == A_REPONDRE:
            # Sans réponse : la phrase suit le dossier actuel (réimporté) et le destinataire la répartition.
            r.motif = (motif.get("phrase") or "")[:MOTIF_MAX] or None
            r.motif_piece = (motif.get("piece") or "")[:200]
            if r.adresse_choix != MANUEL and (r.adresse_kind, r.adresse_invite_id) != (ad["type"], ad["invite_id"]):
                r.adresse_kind, r.adresse_invite_id = ad["type"], ad["invite_id"]
                r.lock_version = int(r.lock_version or 0) + 1
                reproposees += 1
    base_ia = len(props)
    for r in rows.values():
        if r.code in gardes:
            continue
        if r.origine == IA:
            if r.retiree_le is None:
                r.ordre = base_ia + int(r.numero or 0)
            continue
        if r.retiree_le is None and r.statut == A_REPONDRE:
            r.retiree_le = now
            retirees += 1
    db.commit()
    return {"creees": creees, "retirees": retirees, "reproposees": reproposees}


# ── Répondre (chef de file), adresser à un partenaire ─────────────────────────────────

def _question(db, dossier: DossierPresentation, qid, verrou: bool = False) -> EntretienQuestion:
    try:
        i = int(qid)
    except (TypeError, ValueError):
        i = 0
    q = db.query(EntretienQuestion).filter(EntretienQuestion.id == i, EntretienQuestion.dossier_id == dossier.id,
                                           EntretienQuestion.retiree_le.is_(None))
    if verrou:
        q = q.populate_existing().with_for_update()
    r = q.first()
    if r is None:
        raise AtelierError(404, "question_introuvable", "Question introuvable.")
    return r


def personnes_equipe(db, owner_id: int) -> list:
    """La liste « Équipe » de « Mes preuves » (fiches acceptées et utilisables) : [{preuve_id, ref, nom,
    fonction}]. Montrée au chef de file seul (son équipe) ; jamais un CV, jamais à l'IA."""
    from app.services import preuves as pv
    try:
        fx = pv.faits_autorises(db, owner_id, natures=[pv.SALARIE])
    except Exception:       # noqa: BLE001
        return []
    out = []
    for f in fx:
        v = f.get("valeur") or {}
        out.append({"preuve_id": f["id"], "ref": f["ref"], "nom": _flat(v.get("nom"))[:120],
                    "fonction": _flat(v.get("fonction"))[:120]})
    return out


def _verifier_lock(r: EntretienQuestion, lock_version) -> None:
    if lock_version is not None and int(lock_version) != int(r.lock_version or 0):
        raise AtelierError(409, "question_modifiee", "Cette question a changé entre-temps : relisez-la avant de répondre.")


def _appliquer(r: EntretienQuestion, statut: str, reponse, preuve_id, *, kind: str, invite_id, user_id) -> None:
    if statut not in STATUTS:
        raise AtelierError(422, "statut_invalide", "Réponse inconnue : répondre, passer, sans objet, ou à répondre.")
    texte = at.normaliser_texte(reponse or "")
    if len(texte) > REPONSE_MAX:
        raise AtelierError(422, "reponse_trop_longue", f"La réponse dépasse {REPONSE_MAX} caractères : allez à l'essentiel, "
                                                       "la rédaction la mettra en phrases.")
    if statut == REPONDUE and not preuve_id and len(texte) < 2:
        raise AtelierError(422, "reponse_vide", "Écrivez votre réponse, ou passez la question.")
    r.statut = statut
    if statut == REPONDUE:
        r.reponse, r.reponse_preuve_id = (texte or None), (int(preuve_id) if preuve_id else None)
        r.reponse_kind, r.reponse_invite_id, r.reponse_user_id = kind, invite_id, user_id
        r.repondu_le = utcnow()
    elif statut == A_REPONDRE:
        r.reponse = r.reponse_preuve_id = r.reponse_invite_id = r.reponse_user_id = r.repondu_le = None
        r.reponse_kind = ""
    else:                                        # sautée ou sans objet : qui l'a décidé, et quand
        r.reponse, r.reponse_preuve_id = None, None
        r.reponse_kind, r.reponse_invite_id, r.reponse_user_id = kind, invite_id, user_id
        r.repondu_le = utcnow()
    r.lock_version = int(r.lock_version or 0) + 1


def repondre(db, project: Project, dossier: DossierPresentation, lecteur: at.Lecteur, qid, *, statut: str,
             reponse: Optional[str] = None, preuve_id=None, lock_version=None) -> EntretienQuestion:
    """Le chef de file répond à une question posée à SON entreprise (répondre, passer, sans objet, ou la
    remettre « à répondre »). Une question posée à un partenaire : 403 (il y répond chez lui). Aucune IA."""
    r = _question(db, dossier, qid, verrou=True)
    if r.adresse_kind == INV:
        nom = _noms_invitations(db, [r.adresse_invite_id]).get(r.adresse_invite_id, "un partenaire")
        db.rollback()
        raise AtelierError(403, "question_d_un_partenaire", MSG_QUESTION_PARTENAIRE.format(nom=nom))
    _verifier_lock(r, lock_version)
    if statut == REPONDUE and preuve_id:
        if r.type_reponse != eb.EQUIPE:
            raise AtelierError(422, "personne_inattendue", "Cette question ne demande pas une personne de l'équipe.")
        if not any(p["preuve_id"] == int(preuve_id) for p in personnes_equipe(db, dossier.owner_id)):
            raise AtelierError(422, "personne_introuvable", "Cette personne n'est plus dans « Mes preuves » (rubrique "
                                                            "Équipe), ou sa fiche n'est plus utilisable.")
    _appliquer(r, statut, reponse, preuve_id, kind=ORG, invite_id=None, user_id=lecteur.user_id)
    db.commit()
    return r


def adresser(db, project: Project, dossier: DossierPresentation, lecteur: at.Lecteur, qid, invite_id,
             confirmer: bool = False, ip: str = "") -> EntretienQuestion:
    """Pose la question à un partenaire du groupement (son invitation) ou la reprend pour votre entreprise
    (`invite_id` None). Une réponse déjà donnée par le destinataire actuel sort de la fiche chantier
    (confirmation exigée : 409 « reponse_a_confirmer ») — la réponse d'un partenaire reste SA donnée, elle ne
    devient jamais celle d'un autre. Inscrit au journal (le partenaire concerné le lit dans le sien)."""
    from app.services import atelier_groupement as ag
    r = _question(db, dossier, qid, verrou=True)
    if invite_id is not None:
        try:
            iid = int(invite_id)
        except (TypeError, ValueError):
            iid = 0
        membres = {m["invite_id"]: m for m in _membres_ok(db, project, dossier)}
        if not ag.repartition_active(db, dossier):
            db.rollback()
            raise AtelierError(409, "groupement_non_prepare", "Préparez d'abord « Qui écrit quoi » : c'est dans son espace "
                                                              "de rédaction que le partenaire trouvera la question.")
        if iid not in membres:
            db.rollback()
            raise AtelierError(409, "partenaire_indisponible", "Ce partenaire ne peut pas recevoir de question : il n'est "
                                                               "pas (ou plus) membre du groupement, ou son lien a expiré.")
        cible = (INV, iid)
    else:
        cible = (ORG, None)
    if (r.adresse_kind, r.adresse_invite_id) == cible:
        r.adresse_choix = MANUEL
        db.commit()
        return r
    avant = (r.adresse_kind, r.adresse_invite_id)
    if r.statut != A_REPONDRE:
        if not confirmer:
            qui = ("votre entreprise" if avant[0] == ORG else
                   _noms_invitations(db, [avant[1]]).get(avant[1], "le partenaire"))
            db.rollback()
            raise AtelierError(409, "reponse_a_confirmer",
                               f"La question a déjà une réponse de {qui} : en la posant à un autre, cette réponse sort de "
                               "la fiche chantier.")
        _appliquer(r, A_REPONDRE, None, None, kind="", invite_id=None, user_id=None)
    r.adresse_kind, r.adresse_invite_id, r.adresse_choix = cible[0], cible[1], MANUEL
    r.lock_version = int(r.lock_version or 0) + 1
    db.commit()
    acteur = lecteur.email or f"user:{lecteur.user_id}"
    if cible[0] == INV:
        ag._journal(db, action="entretien.question_adressee", project_id=project.id, owner_id=dossier.owner_id,
                    actor=acteur, actor_kind="owner", invite_id=cible[1], target_type="entretien_question",
                    target_id=r.id, ip=ip, detail=f"Question sur le chantier : {r.theme}"[:255])
    if avant[0] == INV and avant[1]:
        ag._journal(db, action="entretien.question_reprise", project_id=project.id, owner_id=dossier.owner_id,
                    actor=acteur, actor_kind="owner", invite_id=avant[1], target_type="entretien_question",
                    target_id=r.id, ip=ip, detail=f"Question sur le chantier : {r.theme}"[:255])
    return r


# ── Partenaire : les questions posées dans SON espace ────────────────────────────────

def questions_du_partenaire(db, dossier: DossierPresentation, invite_id: int) -> list:
    return (db.query(EntretienQuestion).filter(EntretienQuestion.dossier_id == dossier.id,
                                               EntretienQuestion.retiree_le.is_(None),
                                               EntretienQuestion.adresse_kind == INV,
                                               EntretienQuestion.adresse_invite_id == invite_id)
            .order_by(EntretienQuestion.ordre.asc(), EntretienQuestion.numero.asc()).all())


def vue_partenaire(db, acces) -> dict:
    """Ce que voit un partenaire : les questions que le chef de file LUI pose, avec la phrase du dossier qui
    les motive, la partie concernée, et SA réponse. Jamais une question posée à un autre, jamais une réponse du
    chef de file ni d'un autre membre."""
    rows = questions_du_partenaire(db, acces.dossier, acces.invite_id)
    secs = at.sections_actives(db, acces.dossier)
    lg = lignes_grille(acces.project)
    qs = []
    for r in rows:
        d = _def(r)
        partie = partie_concernee(d.get("parties") or [], secs, _critere_de(d.get("criteres") or [], lg))
        sienne = r.reponse_kind == INV and r.reponse_invite_id == acces.invite_id
        qs.append({"id": r.id, "numero": r.numero, "theme": r.theme, "question": r.question or "",
                   "type_reponse": eb.TEXTE, "motif": ({"phrase": r.motif, "piece": r.motif_piece} if r.motif else None),
                   "motif_message": "" if r.motif else MSG_SANS_MOTIF,
                   "partie": ({"section_id": partie.id, "titre": _flat(partie.intitule)[:160]} if partie else None),
                   "statut": r.statut if (sienne or r.statut == A_REPONDRE) else A_REPONDRE,
                   "statut_libelle": STATUTS[r.statut if (sienne or r.statut == A_REPONDRE) else A_REPONDRE],
                   "reponse": ({"texte": r.reponse or "", "le": _iso(r.repondu_le)} if sienne and r.statut == REPONDUE
                               else None),
                   "a_completer": a_completer(r), "lock_version": int(r.lock_version or 0)})
    n = len(qs)
    a_rep = sum(1 for x in qs if x["statut"] == A_REPONDRE)
    return {"questions": qs, "total": n, "a_repondre": a_rep, "message": MSG_PARTENAIRE if n else "",
            "avertissement": AVERTISSEMENT_REPONSE, "statuts": STATUTS}


def repondre_partenaire(db, acces, qid, *, statut: str, reponse: Optional[str] = None, avertissement_lu: bool = False,
                        lock_version=None, ip: str = "") -> EntretienQuestion:
    """Le partenaire répond, chez lui, à une question qui LUI est posée. Sa réponse est une déclaration de son
    entreprise, lue par le chef de file : avertissement exigé, même exigence d'identité qu'un envoi (adresse
    prouvée par code quand le lien vise une adresse, ou compte vérifié), clé de l'espace par le lien. Inscrit
    au journal chaîné (son journal le montre). Comme ses autres écritures, le verrou de l'invitation D'ABORD
    (avant celui de la question) : l'invitation relue, la clé présentée doit encore ouvrir l'espace (409
    « espace_reinitialise » sinon, rien n'est écrit) ; un retrait arrivé entre-temps passe avant (404)."""
    from app.services import atelier_groupement as ag
    ag._exiger_ecriture(acces)
    if statut == REPONDUE and not avertissement_lu:
        raise AtelierError(422, "avertissement_requis", AVERTISSEMENT_REPONSE)
    ag._exiger_identite(acces)
    try:
        ag._verrou_du_lien(db, acces)
    except AtelierError as e:
        if e.code == "partie_introuvable":
            raise AtelierError(404, "question_introuvable", "Question introuvable.") from None
        raise
    try:
        ag._exiger_identite(acces)      # relue sous le verrou (une réinitialisation remet l'adresse à prouver)
    except AtelierError:
        db.rollback()
        raise
    try:
        i = int(qid)
    except (TypeError, ValueError):
        i = 0
    r = (db.query(EntretienQuestion).filter(EntretienQuestion.id == i, EntretienQuestion.dossier_id == acces.dossier.id,
                                            EntretienQuestion.retiree_le.is_(None), EntretienQuestion.adresse_kind == INV,
                                            EntretienQuestion.adresse_invite_id == acces.invite_id)
         .populate_existing().with_for_update().first())
    if r is None:
        db.rollback()
        raise AtelierError(404, "question_introuvable", "Question introuvable.")
    _verifier_lock(r, lock_version)
    _appliquer(r, statut, reponse, None, kind=INV, invite_id=acces.invite_id, user_id=getattr(acces.user, "id", None))
    db.commit()
    detail = {REPONDUE: "Réponse", SAUTEE: "Question passée", SANS_OBJET: "Sans objet",
              A_REPONDRE: "Réponse retirée"}[statut] + f" : {r.theme}"
    ag._journal(db, action="entretien.reponse", project_id=acces.project.id, owner_id=acces.dossier.owner_id,
                actor=acces.acteur, actor_kind="guest", invite_id=acces.invite_id, target_type="entretien_question",
                target_id=r.id, ip=ip, detail=detail[:255])
    return r


# ── La fiche chantier : des faits numérotés pour la rédaction et le contrôle (A) ─────

def _personnes_par_id(db, owner_id: int, rows: list) -> dict:
    if not any(r.reponse_preuve_id for r in rows):
        return {}
    return {p["preuve_id"]: p for p in personnes_equipe(db, owner_id)}


def _utilisable(r: EntretienQuestion, personnes: dict) -> bool:
    """Une réponse qui peut servir : du texte, ou une personne de l'équipe encore dans « Mes preuves »."""
    if r.statut != REPONDUE:
        return False
    if r.reponse_preuve_id and r.reponse_preuve_id in personnes:
        return True
    return bool(_flat(r.reponse))


def _fiche(r: EntretienQuestion, personnes: dict, pseudonymiseur, nom_partenaire: str = "") -> fs.Fiche:
    """[R3] : la réponse, avec la question pour que l'IA la place bien. Une personne de l'équipe : son nom pour
    le contrôle, son étiquette pour l'IA (jamais son nom ni son CV)."""
    theme, q = _flat(r.theme), _flat(r.question)
    rep = _flat(r.reponse)
    p = personnes.get(r.reponse_preuve_id) if r.reponse_preuve_id else None
    tete = f"{nom_partenaire} — entretien chantier" if nom_partenaire else "Entretien chantier"
    if p is not None:
        label = ""
        if pseudonymiseur is not None and getattr(pseudonymiseur, "active", False):
            try:
                label = pseudonymiseur.label_of(p["nom"] or "")
            except Exception:       # noqa: BLE001
                label = ""
        qui_ia = f"{label}, {p['fonction']}" if label else f"une personne de l'équipe, {p['fonction']}"
        texte = f"{tete}, {theme} : {p['nom']}, {p['fonction']}" + (f" ; {rep}" if rep else "")
        texte_ia = (f"{tete}, réponse à « {q} » : {qui_ia} (sa fiche : [{p['ref']}])" + (f" ; {rep}" if rep else ""))
    else:
        texte = f"{tete}, {theme} : {rep}"
        texte_ia = f"{tete}, réponse à « {q} » : {rep}"
    ref = f"{fs.ENTRETIEN}{int(r.numero)}"
    if nom_partenaire:
        return fs.Fiche(ref, fs.T_PARTENAIRE, fs.LIB_PARTENAIRE, texte, texte_ia, proprietaire=nom_partenaire)
    return fs.Fiche(ref, fs.T_DECLARE, fs.LIB_DECLARE, texte, texte_ia)


def fiches_chef(db, dossier_id: Optional[int], owner_id: int, pseudonymiseur=None) -> tuple:
    """(fiches, noms des partenaires) de la fiche chantier pour l'atelier du chef de file : SES réponses
    (« déclaré par vous ») et celles de ses partenaires encore membres du groupement (« déclaré par votre
    partenaire », qui n'appuient qu'une phrase qui les nomme). Ne lève pas."""
    if not dossier_id:
        return [], []
    try:
        rows = [r for r in db.query(EntretienQuestion).filter(EntretienQuestion.dossier_id == dossier_id,
                                                              EntretienQuestion.retiree_le.is_(None),
                                                              EntretienQuestion.statut == REPONDUE)
                .order_by(EntretienQuestion.numero.asc()).all()]
        personnes = _personnes_par_id(db, owner_id, rows)
        noms = _noms_invitations(db, [r.reponse_invite_id for r in rows if r.reponse_kind == INV])
        out, partenaires = [], []
        for r in rows:
            if not _utilisable(r, personnes):
                continue
            if r.reponse_kind == ORG and r.adresse_kind == ORG:
                out.append(_fiche(r, personnes, pseudonymiseur))
            elif (r.reponse_kind == INV and r.adresse_kind == INV and r.reponse_invite_id == r.adresse_invite_id
                  and _invitation_active(db, r.reponse_invite_id)):
                nom = noms.get(r.reponse_invite_id) or "Un partenaire"
                out.append(_fiche(r, {}, pseudonymiseur, nom_partenaire=nom))
                if nom not in partenaires:
                    partenaires.append(nom)
        return out, partenaires
    except Exception as e:      # noqa: BLE001 — la rédaction se fait alors sans la fiche chantier
        logger.warning("entretien : fiche chantier illisible (dossier %s) : %s", dossier_id, type(e).__name__)
        return [], []


def fiches_partenaire(db, dossier_id: int, invite_id: int) -> list:
    """La fiche chantier d'UN partenaire, pour SON aide de l'IA : ses réponses seulement (« déclaré par vous »)."""
    try:
        rows = [r for r in db.query(EntretienQuestion).filter(EntretienQuestion.dossier_id == dossier_id,
                                                              EntretienQuestion.retiree_le.is_(None),
                                                              EntretienQuestion.statut == REPONDUE,
                                                              EntretienQuestion.adresse_kind == INV,
                                                              EntretienQuestion.adresse_invite_id == invite_id,
                                                              EntretienQuestion.reponse_kind == INV,
                                                              EntretienQuestion.reponse_invite_id == invite_id)
                .order_by(EntretienQuestion.numero.asc()).all()]
        return [_fiche(r, {}, None) for r in rows if _flat(r.reponse)]
    except Exception as e:      # noqa: BLE001
        logger.warning("entretien : fiche chantier du partenaire illisible (invitation %s) : %s", invite_id,
                       type(e).__name__)
        return []


def pour_parties(db, project: Project, dossier: DossierPresentation, sections: list,
                 invite_id: Optional[int] = None) -> dict:
    """{section_id: {"refs": ["R3"], "manques": ["[À compléter : …]"], "en_attente": ["[À compléter : …]"]}} : pour
    chaque partie, les réponses de l'entretien qui la concernent (à citer), les questions PASSÉES (ou dont la réponse
    ne sert plus : personne retirée de « Mes preuves ») — leur « [À compléter] » est garanti dans le texte, ajouté
    sans IA s'il manque — et les questions encore SANS RÉPONSE (l'IA n'écrit aucun fait à leur sujet et laisse
    « [À compléter] » si la partie doit en parler ; l'écran prévient avant de rédiger). « Sans objet » : rien.
    Chef de file : toutes les questions ; partenaire (`invite_id`) : celles qui lui sont posées. Sans IA ; ne lève
    pas."""
    out = {}
    try:
        q = db.query(EntretienQuestion).filter(EntretienQuestion.dossier_id == dossier.id,
                                               EntretienQuestion.retiree_le.is_(None))
        if invite_id is not None:
            q = q.filter(EntretienQuestion.adresse_kind == INV, EntretienQuestion.adresse_invite_id == invite_id)
        rows = q.order_by(EntretienQuestion.ordre.asc(), EntretienQuestion.numero.asc()).all()
        if not rows:
            return out
        secs = at.sections_actives(db, dossier)
        lg = lignes_grille(project)
        personnes = _personnes_par_id(db, dossier.owner_id, rows) if invite_id is None else {}
        ids = {s.id for s in sections}
        for r in rows:
            if r.statut == SANS_OBJET:
                continue
            d = _def(r)
            partie = partie_concernee(d.get("parties") or [], secs, _critere_de(d.get("criteres") or [], lg))
            if partie is None or partie.id not in ids:
                continue
            x = out.setdefault(partie.id, {"refs": [], "manques": [], "en_attente": []})
            if invite_id is not None:
                sienne = r.reponse_kind == INV and r.reponse_invite_id == invite_id
                ok = r.statut == REPONDUE and sienne and bool(_flat(r.reponse))
            elif r.reponse_kind == INV:
                ok = (r.statut == REPONDUE and r.adresse_kind == INV and r.reponse_invite_id == r.adresse_invite_id
                      and bool(_flat(r.reponse)) and _invitation_active(db, r.reponse_invite_id))
            else:
                ok = r.adresse_kind == ORG and _utilisable(r, personnes)
            if ok:
                x["refs"].append(f"{fs.ENTRETIEN}{int(r.numero)}")
            elif r.statut == A_REPONDRE:
                x["en_attente"].append(a_completer(r))
            elif r.statut in (SAUTEE, REPONDUE):
                x["manques"].append(a_completer(r))
    except Exception as e:      # noqa: BLE001
        logger.warning("entretien : parties concernées illisibles (dossier %s) : %s", getattr(dossier, "id", "?"),
                       type(e).__name__)
    return out


_TODO = re.compile(r"\[\s*[ÀAà]\s+compl[ée]ter[^\]]*\]", re.IGNORECASE)
_MOTS_VIDES = {"chantier", "travaux", "marche", "entreprise", "dossier", "reponse", "question", "pendant", "avant"}


def _deja_la(texte_replie_todos: list, manque: str) -> bool:
    lab = _fold(re.sub(r"^\[\s*[^:]*:\s*|\]$", "", manque)).strip()
    if not lab:
        return True
    mots = [w for w in re.findall(r"[a-z]{4,}", lab) if w not in _MOTS_VIDES]
    for t in texte_replie_todos:
        if lab in t:
            return True
        if mots and sum(1 for w in mots if w[:6] in t) >= min(2, len(mots)):
            return True
    return False


def garantir_manques(texte: str, manques: list) -> str:
    """Après l'IA, sans IA : chaque question sans réponse de la partie laisse SON « [À compléter : …] » ; s'il
    manque au texte rendu, il est ajouté en fin de partie (jamais un texte de remplissage à sa place)."""
    if not manques or not (texte or "").strip():
        return texte
    todos = [_fold(m) for m in _TODO.findall(texte or "")]
    ajout = []
    for m in manques:
        if not _deja_la(todos, m) and m not in ajout:
            ajout.append(m)
            todos.append(_fold(m))
    if not ajout:
        return texte
    return texte.rstrip() + "\n\n" + "\n".join(ajout)


# ── L'état de l'entretien (chef de file) ──────────────────────────────────────────────

def _question_out(r: EntretienQuestion, *, partie, ligne, personnes: dict, noms: dict) -> dict:
    d = _def(r)
    a_part = r.adresse_kind == INV
    par = ""
    if r.statut != A_REPONDRE:
        par = "vous" if r.reponse_kind == ORG else (noms.get(r.reponse_invite_id) or "un partenaire")
    rep = None
    if r.statut == REPONDUE:
        p = personnes.get(r.reponse_preuve_id) if r.reponse_preuve_id else None
        rep = {"texte": r.reponse or "", "preuve_id": r.reponse_preuve_id,
               "personne": ({"nom": p["nom"], "fonction": p["fonction"], "ref": p["ref"]} if p else None),
               "personne_retiree": bool(r.reponse_preuve_id and p is None),
               "par": par, "le": _iso(r.repondu_le),
               "libelle": "déclaré par vous" if r.reponse_kind == ORG else f"déclaré par {par}"}
    return {"id": r.id, "numero": r.numero, "ref": f"{fs.ENTRETIEN}{int(r.numero)}", "code": r.code,
            "origine": r.origine, "origine_libelle": LIB_ORIGINE.get(r.origine, ""), "theme": r.theme,
            "question": r.question or "", "type_reponse": r.type_reponse or eb.TEXTE,
            "aide": d.get("aide") or ("" if r.type_reponse != eb.EQUIPE else BULLE_EQUIPE),
            "motif": ({"phrase": r.motif, "piece": r.motif_piece} if r.motif else None),
            "motif_message": "" if r.motif else MSG_SANS_MOTIF,
            "critere": ({"critere": ligne.get("critere"), "poids": ligne.get("poids") or "",
                         "poids_source": ligne.get("poids_source") or ""} if ligne else None),
            "partie": ({"section_id": partie.id, "titre": _flat(partie.intitule)[:160],
                        "redacteur": (noms.get(partie.author_invite_id) or "un partenaire")
                        if partie.author_kind == INV else ""} if partie else None),
            "adresse": {"type": r.adresse_kind, "invite_id": r.adresse_invite_id,
                        "nom": (noms.get(r.adresse_invite_id) or "un partenaire") if a_part else "",
                        "choix": r.adresse_choix},
            "statut": r.statut, "statut_libelle": STATUTS.get(r.statut, ""),
            "reponse": rep, "par": par, "a_completer": a_completer(r),
            "peut_repondre": not a_part, "lock_version": int(r.lock_version or 0)}


def resume(db, dossier: Optional[DossierPresentation]) -> dict:
    """Pour l'en-tête de l'atelier (deux requêtes, sans IA) : {prepare, total, repondues, a_repondre, passees,
    sans_objet, chez_partenaires}."""
    out = {"prepare": False, "total": 0, "repondues": 0, "a_repondre": 0, "passees": 0, "sans_objet": 0,
           "chez_partenaires": 0}
    if dossier is None:
        return out
    try:
        rows = lignes(db, dossier)
    except Exception:       # noqa: BLE001
        return out
    out["prepare"] = bool(rows) or prepare(db, dossier)
    out["total"] = len(rows)
    for r in rows:
        out["repondues"] += r.statut == REPONDUE
        out["a_repondre"] += r.statut == A_REPONDRE
        out["passees"] += r.statut == SAUTEE
        out["sans_objet"] += r.statut == SANS_OBJET
        out["chez_partenaires"] += r.adresse_kind == INV and r.statut == A_REPONDRE
    return out


def _en_cours_ia(db, dossier: DossierPresentation, member_ids: list) -> Optional[Job]:
    for j in (db.query(Job).filter(Job.kind == JOB_ENTRETIEN, Job.status.in_(["pending", "running"]),
                                   Job.user_id.in_(list(member_ids) or [-1])).order_by(Job.id.desc()).all()):
        dbt = ((j.result or {}).get("_debit") or {}) if isinstance(j.result, dict) else {}
        if not dbt or int(dbt.get("dossier_id") or 0) == dossier.id:
            return j
    return None


def etat(db, project: Project, dossier: DossierPresentation, lecteur: at.Lecteur, member_ids: list) -> dict:
    """L'entretien tel que le lit le chef de file. Pas encore préparé : la PROPOSITION (rien n'est enregistré :
    l'écran appelle POST /entretien quand on ouvre les questions)."""
    rows = lignes(db, dossier)
    pret = bool(rows) or prepare(db, dossier)
    secs = at.sections_actives(db, dossier)
    lg = lignes_grille(project)
    membres = _membres_ok(db, project, dossier)
    pieces_ok = True
    questions = []
    if pret:
        personnes = _personnes_par_id(db, dossier.owner_id, rows)
        noms = _noms_invitations(db, [r.adresse_invite_id for r in rows] + [r.reponse_invite_id for r in rows]
                                 + [s.author_invite_id for s in secs if s.author_kind == INV])
        for r in rows:
            d = _def(r)
            ln = _critere_de(d.get("criteres") or [], lg)
            questions.append(_question_out(r, partie=partie_concernee(d.get("parties") or [], secs, ln), ligne=ln,
                                           personnes=personnes, noms=noms))
    else:
        pieces, _cle = pieces_du_marche(db, project, member_ids)
        pieces_ok = bool(pieces)
        for p in proposition(db, project, dossier, member_ids):
            ln, partie, ad, mo = p["ligne"], p["partie"], p["adresse"], p["motif"]
            questions.append({"id": None, "numero": None, "ref": "", "code": p["code"], "origine": BANQUE,
                              "origine_libelle": LIB_ORIGINE[BANQUE], "theme": p["theme"], "question": p["question"],
                              "type_reponse": p["type_reponse"], "aide": "",
                              "motif": mo, "motif_message": "" if mo else MSG_SANS_MOTIF,
                              "critere": ({"critere": ln.get("critere"), "poids": ln.get("poids") or "",
                                           "poids_source": ln.get("poids_source") or ""} if ln else None),
                              "partie": ({"section_id": partie.id, "titre": _flat(partie.intitule)[:160],
                                          "redacteur": ""} if partie else None),
                              "adresse": {"type": ad["type"], "invite_id": ad["invite_id"], "nom": ad["nom"],
                                          "choix": PROPOSE, "message": ad["message"]},
                              "statut": A_REPONDRE, "statut_libelle": STATUTS[A_REPONDRE], "reponse": None, "par": "",
                              "a_completer": f"[À compléter : {_flat(eb.PAR_CODE[p['code']]['a_completer'])}]",
                              "peut_repondre": ad["type"] == ORG, "lock_version": 0})
    n = len(questions)
    res = resume(db, dossier)
    job = _en_cours_ia(db, dossier, member_ids)
    n_ia = sum(1 for r in rows if r.origine == IA)
    fiche = []
    if pret:
        personnes = _personnes_par_id(db, dossier.owner_id, rows)
        noms = _noms_invitations(db, [r.reponse_invite_id for r in rows if r.reponse_kind == INV])
        for r in rows:
            if r.statut != REPONDUE or not _utilisable(r, personnes):
                continue
            p = personnes.get(r.reponse_preuve_id) if r.reponse_preuve_id else None
            txt = (f"{p['nom']}, {p['fonction']}" + (f" ; {r.reponse}" if r.reponse else "")) if p else (r.reponse or "")
            par = "vous" if r.reponse_kind == ORG else (noms.get(r.reponse_invite_id) or "un partenaire")
            fiche.append({"ref": f"{fs.ENTRETIEN}{int(r.numero)}", "theme": r.theme, "texte": txt,
                          "libelle": "déclaré par vous" if r.reponse_kind == ORG else f"déclaré par {par}"})
    msg = (f"{n} question{'s' if n > 1 else ''} sur ce chantier" if n else "Aucune question sur ce chantier")
    if not pieces_ok and not pret:
        msg += ". " + MSG_SANS_DCE
    return {"prepare": pret, "message": msg, "bulle": BULLE, "max": MAX_QUESTIONS, "questions": questions,
            "compteurs": res, "fiche": fiche, "equipe": personnes_equipe(db, dossier.owner_id),
            "dossier_present": pieces_ok,
            "groupement": {"actif": bool(membres),
                           "membres": [{"invite_id": m["invite_id"], "nom": m["nom"], "lot": m.get("lot") or ""}
                                       for m in membres]},
            "ia": {"en_cours": ({"job_id": job.id, "statut": job.status} if job is not None else None),
                   "proposees": n_ia, "restantes": max(0, MAX_IA - n_ia), "plafond": MAX_IA, "bulle": BULLE_IA,
                   "quota": at.quota_out(dossier)["message"],
                   # Dossier « sans IA » (vague 5, C2) : l'écran ne propose pas la recherche avec l'IA.
                   "permise": not at.mode_sans_ia(dossier)},
            "statuts": STATUTS}


# ── Option IA : des questions supplémentaires, chacune motivée par une phrase retrouvée ──

_SYS_IA = """Tu prépares l'entretien chantier d'une entreprise du bâtiment qui répond à un marché public. Adjugo pose
déjà des questions sur les contraintes du chantier repérées dans le dossier de l'acheteur (liste ci-dessous). Tu proposes
AU PLUS {n} questions SUPPLÉMENTAIRES, sur des contraintes ou des attentes PROPRES À CE CHANTIER que ces questions ne
couvrent pas.
RÈGLES ABSOLUES :
- Chaque question s'appuie sur UNE phrase du dossier de l'acheteur, recopiée MOT POUR MOT dans "phrase" (sans la
  reformuler, sans la résumer, sans la couper au milieu d'un mot). Une question sans phrase recopiée est écartée.
- La question s'adresse à l'entreprise (« Comment… ? », « Quel… ? »), en 25 mots au plus, sans jargon, sans supposer la
  réponse, sans aucun chiffre ni aucun nom qui ne figure pas dans la phrase.
- Aucune question sur le prix, ni sur les pièces administratives à fournir.
- "theme" : 2 à 6 mots qui disent ce qui manquera si l'entreprise ne répond pas (par exemple « accès des engins de
  levage »).
- S'il n'y a rien d'utile à ajouter, rends une liste vide.
Réponds UNIQUEMENT en JSON : {{"questions": [{{"question": "...", "phrase": "...", "theme": "..."}}]}}"""

_ORDRE_IA = {dp.CCTP: 0, dp.CADRE: 1, dp.REGLEMENT: 2, dp.CCAP: 3, dp.AUTRE: 4}


def _dossier_pour_ia(pieces: list, budget: int = IA_DOSSIER_MAX) -> str:
    """Le dossier de l'acheteur remis à l'IA : CCTP, cadre, règlement, CCAP et autres pièces (jamais les
    bordereaux de prix ni l'acte d'engagement), partagés équitablement dans le budget."""
    ps = sorted([p for p in pieces if p["type"] in _ORDRE_IA], key=lambda p: _ORDRE_IA[p["type"]])
    alloc = dp.water_fill([len(p["texte"]) for p in ps], budget)
    parts = []
    for p, n in zip(ps, alloc):
        if n > 0:
            parts.append(dp.header(p.get("nom") or p.get("libelle")) + "\n" + p["texte"][:n])
    return "\n\n".join(parts)


def lancer_ia(db, user: User, project: Project, dossier: DossierPresentation, lecteur: at.Lecteur, member_ids: list,
              accepte_debit: bool = False) -> Job:
    """« Chercher d'autres questions avec Adjugo » : tâche de fond du chef de file. Débit : une refonte du dossier
    (décision 6a ; la 1re action de l'IA du dossier compte pour 1 analyse), RENDUE si l'IA tombe ou si aucune
    question n'est retenue."""
    from app.services.budget_ia import estimer, verifier
    from app.services.jobs import run_in_thread
    # Vague 5 (C2 × D) : un dossier « sans IA » (choix du chef de file, souvent parce que le règlement l'exige) ne
    # demande aucune question à l'IA (409 « mode_sans_ia ») ; les questions de la banque, elles, restent (sans IA).
    at.exiger_ia_permise(dossier)
    if not prepare(db, dossier):
        preparer(db, project, dossier, lecteur, member_ids)
    if _en_cours_ia(db, dossier, member_ids) is not None:
        raise AtelierError(409, "entretien_ia_en_cours", "Adjugo cherche déjà d'autres questions : attendez la fin.")
    n_ia = sum(1 for r in lignes(db, dossier) if r.origine == IA)
    if n_ia >= MAX_IA:
        raise AtelierError(409, "plafond_questions_ia", f"Adjugo a déjà proposé {MAX_IA} questions avec l'IA pour ce "
                                                        "dossier : écrivez les autres vous-même dans vos réponses.")
    pieces, _cle = pieces_du_marche(db, project, member_ids)
    if not pieces:
        raise AtelierError(422, "dossier_absent", MSG_SANS_DCE)
    sections = [s for s in at.sections_actives(db, dossier) if not at.est_generee(s)]
    if not sections:
        raise AtelierError(422, "aucune_partie", "Le dossier de présentation n'a aucune partie : préparez d'abord son plan.")
    estimation = estimer("entretien")
    verifier(user, db, "atelier", estimation)
    job = Job(user_id=user.id, kind=JOB_ENTRETIEN, status="pending",
              label="Entretien chantier : questions proposées par Adjugo")
    db.add(job)
    db.commit()
    jid = job.id
    try:
        releve = at._debiter(db, user, dossier, [sections[0]], accepte_debit, jid, estimation,
                             deja_ia=lambda _db, _s: True)
    except Exception:
        db.rollback()
        j = db.get(Job, jid)
        if j is not None:
            db.delete(j)
            db.commit()
        raise
    job = db.get(Job, jid)
    releve.update(dossier_id=dossier.id, rendu=False)
    job.result = {"_debit": releve}
    db.commit()
    pid, owner, mids = project.id, dossier.owner_id, list(member_ids)

    def _work(jdb):
        return _executer_ia(jdb, job_id=jid, project_id=pid, owner_id=owner, member_ids=mids)

    def _on_error(jdb, j):
        at.rembourser(jdb, j)

    run_in_thread(jid, _work, on_error=_on_error, tenant_id=owner, error_message=MSG_IA_PANNE)
    return db.get(Job, jid)


_NOMBRE = re.compile(r"\d+(?:[.,]\d+)?")


def _valider_ia(item, texte_dossier: str, pieces: list, deja: set) -> Optional[dict]:
    """Une question proposée par l'IA, contrôlée SANS IA : sa phrase retrouvée mot pour mot dans le dossier
    (citation_guard), aucun nombre absent de cette phrase, une vraie question courte, pas déjà posée."""
    from app.services.analysis import _norm_citation, citation_guard
    if not isinstance(item, dict):
        return None
    q = _flat(item.get("question"))
    phrase = citation_guard(texte_dossier, item.get("phrase") or "", min_len=20)
    theme = _flat(item.get("theme"))[:120]
    if not q or not phrase or len(q) < 12 or len(q) > QUESTION_MAX:
        return None
    if not q.endswith("?"):
        q = q.rstrip(" .;:") + " ?"
    if re.search(r"[\[\]{}<>]|https?://|www\.|@", q):
        return None
    if set(_NOMBRE.findall(q)) - set(_NOMBRE.findall(phrase)):
        return None                          # un nombre de la question qui n'est pas dans la phrase : refusé
    cle_q, cle_p = _norm_citation(q), _norm_citation(phrase)
    if cle_q in deja or cle_p in deja:
        return None
    piece = ""
    for p in pieces:
        if citation_guard(p["texte"], phrase, min_len=20):
            piece = (p.get("libelle") or dp.label(p["type"]))[:200]
            break
    return {"question": q, "phrase": phrase[:MOTIF_MAX], "piece": piece,
            "theme": theme or " ".join(q.rstrip(" ?").split()[:6])[:120], "cles": (cle_q, cle_p)}


def _appel_ia(existantes: list, texte: str, n: int, billing_id) -> dict:
    """L'appel de l'IA (tâche « exigences » du routage : lecture du dossier de l'acheteur), sans base. Ne lève
    pas : une panne rend erreur=True."""
    from app.services.llm import complete_ex, parse_json, tenant_scope
    lst = "\n".join(f"- {x}" for x in existantes) or "- (aucune)"
    user = (f"QUESTIONS DÉJÀ POSÉES (ne les répète pas) :\n{lst}\n\nDOSSIER DE L'ACHETEUR (pièces choisies, chacune "
            f"précédée de « === nom === ») :\n{texte}")
    try:
        with tenant_scope(billing_id):
            content, _stop = complete_ex(_SYS_IA.format(n=n), user, max_tokens=1600, temperature=0.2,
                                         tache="exigences", json_attendu=True)
        data = parse_json(content)
    except Exception as e:
        logger.warning("entretien : questions de l'IA en échec : %s", type(e).__name__)
        return {"questions": [], "erreur": True}
    items = data.get("questions") if isinstance(data, dict) else None
    return {"questions": items if isinstance(items, list) else [], "erreur": False}


def _executer_ia(db, *, job_id: int, project_id: int, owner_id: int, member_ids: list) -> dict:
    """Dans le fil de la tâche de fond (espace facturé du chef de file) : prépare le dossier, appelle l'IA SANS
    base (noms masqués), contrôle chaque question sans IA, puis enregistre celles qui sont retenues."""
    from app.services.llm import LLMUnavailable, cost_meter, pii_scope
    project = db.get(Project, project_id)
    dossier = at.get_dossier(db, project_id, owner_id)
    if project is None or dossier is None:
        raise RuntimeError("dossier introuvable")
    pieces, _cle = pieces_du_marche(db, project, member_ids)
    rows = db.query(EntretienQuestion).filter(EntretienQuestion.dossier_id == dossier.id).all()
    actives = [r for r in rows if r.retiree_le is None]
    n_ia = sum(1 for r in actives if r.origine == IA)
    place = max(0, MAX_IA - n_ia)
    texte = _dossier_pour_ia(pieces)
    ctx = at.Contexte(db, project, owner_id, member_ids)
    pz = ctx.pseudonymiseur([texte])
    with pii_scope(pz), cost_meter("atelier : entretien chantier", owner_id) as cm:
        res = _appel_ia([f"{r.theme} : {r.question}" for r in actives], texte, max(1, place), owner_id)
    db.expire_all()
    dossier = at.get_dossier(db, project_id, owner_id)
    at._cumuler_cout(dossier, cm.summary())
    db.commit()
    if res.get("erreur"):
        raise LLMUnavailable("Service IA indisponible : aucune question proposée.")
    from app.services.analysis import _norm_citation
    deja = set()
    for r in rows:
        deja.add(_norm_citation(r.question or ""))
        if r.motif:
            deja.add(_norm_citation(r.motif))
    texte_entier = "\n\n".join(p["texte"] for p in pieces)
    retenues, refusees = [], 0
    for item in res.get("questions") or []:
        v = _valider_ia(item, texte_entier, pieces, deja) if len(retenues) < place else None
        if v is None:
            refusees += 1
            continue
        deja.update(v["cles"])
        retenues.append(v)
    ajoutees = 0
    if retenues:
        D = DossierPresentation
        db.query(D).filter(D.id == dossier.id).with_for_update().first()
        num = _prochain_numero(db, dossier.id)
        secs = at.sections_actives(db, dossier)
        lg = lignes_grille(project)
        membres = _membres_ok(db, project, dossier)
        ordre0 = len(actives)
        for i, v in enumerate(retenues):
            code = "ia-" + hashlib.sha256(_norm_citation(v["question"]).encode("utf-8")).hexdigest()[:12]
            stems = _stems_libres(v["theme"], v["question"])
            d = {"lots": stems}
            partie = partie_concernee(stems, secs, _critere_de(stems, lg))
            ad = _proposition_adresse(d, partie, membres)
            db.add(EntretienQuestion(dossier_id=dossier.id, project_id=project.id, owner_id=dossier.owner_id,
                                     numero=num + i, code=code, origine=IA, theme=v["theme"][:160],
                                     question=v["question"][:QUESTION_MAX], type_reponse=eb.TEXTE,
                                     motif=v["phrase"], motif_piece=v["piece"], ordre=ordre0 + i,
                                     adresse_kind=ad["type"], adresse_invite_id=ad["invite_id"], adresse_choix=PROPOSE,
                                     statut=A_REPONDRE))
            ajoutees += 1
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            ajoutees = 0
    j = db.get(Job, job_id)
    debit = None
    if j is not None:
        if not ajoutees:
            at.rembourser(db, j)          # rien de retenu : rien n'est décompté
            db.refresh(j)
        debit = (j.result or {}).get("_debit") if isinstance(j.result, dict) else None
    if ajoutees:
        msg = (f"{ajoutees} question{'s' if ajoutees > 1 else ''} de plus sur ce chantier, chacune avec sa phrase du "
               "dossier.")
    else:
        msg = ("Adjugo n'a trouvé aucune autre question appuyée par une phrase du dossier : rien n'a été décompté.")
    return {"ajoutees": ajoutees, "refusees": refusees, "message": msg, "_debit": debit}


# ── RGPD et cycle de vie ─────────────────────────────────────────────────────────────

def effacer_dossiers(db, dossier_ids: list) -> None:
    """Effacement des dossiers (compte du chef de file, corbeille) : l'entretien part avec eux."""
    if dossier_ids:
        db.query(EntretienQuestion).filter(EntretienQuestion.dossier_id.in_(list(dossier_ids))).delete(
            synchronize_session=False)


def retirer_invitation(db, inv: ProjectInvite) -> int:
    """Invitation RETIRÉE ou DÉCLINÉE : ses réponses sont EFFACÉES (elles sont à lui, plus rien ne les
    justifie), ses questions reviennent au chef de file, à répondre. Renvoie le nombre de questions reprises.
    L'appelant valide la transaction."""
    n = 0
    for r in db.query(EntretienQuestion).filter((EntretienQuestion.adresse_invite_id == inv.id)
                                                | (EntretienQuestion.reponse_invite_id == inv.id)).all():
        if r.reponse_invite_id == inv.id:
            _appliquer(r, A_REPONDRE, None, None, kind="", invite_id=None, user_id=None)
        if r.adresse_invite_id == inv.id:
            r.adresse_kind, r.adresse_invite_id, r.adresse_choix = ORG, None, MANUEL
            r.lock_version = int(r.lock_version or 0) + 1
            n += 1
    return n


def oublier_compte(db, uid: int) -> None:
    """Effacement d'un compte : ses réponses restent à l'organisation ou à l'invitation qui les a données, sans
    le compte qui les a saisies."""
    if uid:
        db.query(EntretienQuestion).filter(EntretienQuestion.reponse_user_id == uid).update(
            {EntretienQuestion.reponse_user_id: None}, synchronize_session=False)


def _export_ligne(r: EntretienQuestion) -> dict:
    return {"numero": r.numero, "theme": r.theme, "question": r.question or "", "phrase_du_dossier": r.motif or "",
            "piece": r.motif_piece or "", "statut": r.statut, "reponse": r.reponse or "",
            "personne_de_l_equipe": r.reponse_preuve_id, "repondu_le": _iso(r.repondu_le),
            "posee_a": "partenaire" if r.adresse_kind == INV else "votre entreprise",
            "repondue_par": ("partenaire" if r.reponse_kind == INV else "votre entreprise") if r.reponse_kind else ""}


def exporter_chef(db, owner_id: int) -> list:
    """Export RGPD du chef de file : l'entretien de ses dossiers (questions, phrases du dossier, réponses — celles
    de ses partenaires comprises, qu'ils lui ont adressées)."""
    out = []
    for d in db.query(DossierPresentation).filter(DossierPresentation.owner_id == owner_id).all():
        rows = lignes(db, d, actives=False)
        if rows:
            out.append({"dossier_id": d.id, "project_id": d.project_id, "questions": [_export_ligne(r) for r in rows]})
    return out


def exporter_invitation(db, inv: ProjectInvite) -> list:
    """Portabilité pour un partenaire : les questions qui lui sont posées et SES réponses."""
    rows = (db.query(EntretienQuestion).filter((EntretienQuestion.adresse_invite_id == inv.id)
                                               | (EntretienQuestion.reponse_invite_id == inv.id))
            .order_by(EntretienQuestion.numero.asc()).all())
    out = []
    for r in rows:
        x = _export_ligne(r)
        if r.reponse_invite_id != inv.id:
            x.update(reponse="", repondue_par="", statut=A_REPONDRE if r.adresse_invite_id == inv.id else x["statut"])
        out.append(x)
    return out
