"""
« Mes preuves » depuis les sources publiques (rédaction, vague 5, E2) : ce que l'utilisateur COCHE
devient une preuve (décision 7 b : proposé, jamais importé d'office).

  • `apercu_marches` / `apercu_rge` : ce que les DECP et la liste RGE de l'ADEME disent de l'entreprise
    (SIRET du profil), avec, pour chaque ligne, « déjà dans vos preuves » et pourquoi une ligne ne peut
    pas devenir une fiche ; rien n'est enregistré ;
  • `importer` : crée les fiches cochées, « acceptées » (cocher, c'est accepter), type de source
    « public » datée (« marché attribué, source publique DECP » ; « source publique : liste RGE de
    l'ADEME »), origine « import_public ». Le client n'envoie que les CLÉS : le contenu est toujours
    relu ici, dans la lecture mise en cache (jamais pris du navigateur) ;
  • le partenaire d'un groupement (lien ou compte) : `apercu_part` (sources publiques lues avec le SIRET
    de SA part), `preuves_du_partenaire` (SES preuves utilisables, compte seulement) et
    `reprendre_dans_part` (ajoute à ses références et qualifications ce qu'il a coché). Sa part est SA
    donnée : rien n'est lu ni écrit chez le chef de file.

Doctrine : aucune IA ; un fait ne vient que de la source ; jamais le mot interdit ; une valeur bizarre est
montrée telle quelle et l'utilisateur la confirme en cochant. Contrat : docs/REDACTION_V5.md, section E2.
"""
from typing import Iterable, Optional

from app.models import Company, Preuve, User
from app.services import preuves as pv
from app.services import sources_publiques as sp

MSG_SIRET = ("Indiquez le SIRET de votre entreprise dans « Profil de l'entreprise » : Adjugo s'en sert pour lire "
             "vos marchés publics et vos qualifications RGE.")
MSG_SIRET_PART = ("Indiquez votre SIRET dans votre part (14 chiffres) et enregistrez-la : Adjugo s'en sert pour lire "
                  "vos marchés publics et vos qualifications RGE.")
MSG_DEJA = "Déjà dans vos preuves."
MSG_DEJA_PART = "Déjà dans votre part."
MSG_PERIMEE = ("Cette ligne n'est plus dans la dernière lecture : rechargez la liste, puis cochez de nouveau.")
MAX_PART = 50                 # références et qualifications d'une part (même borne que l'enregistrement)


def _fold(s) -> str:
    from app.services.faits_a_relire import fold
    return fold(s)


def siret_de(db, owner_id: int) -> str:
    c = db.query(Company).filter(Company.user_id == owner_id).first()
    return "".join(ch for ch in str(getattr(c, "siret", "") or "") if ch.isdigit())


class _DemoMarque:
    """Marque « démo » pour le lien partenaire de la vitrine (aucun compte : l'invitation est de la démo)."""
    email = ""


def _est_demo(user) -> bool:
    """Compte démo, ou lien partenaire de la vitrine : l'exemple fictif, jamais le réseau."""
    if isinstance(user, _DemoMarque):
        return True
    try:
        from app.core.demo_guard import is_demo_user
        return bool(user is not None and is_demo_user(user))
    except Exception:       # noqa: BLE001
        return False


# ── Ce qui est déjà dans « Mes preuves » ─────────────────────────────────────────────

def _existant(db, owner_id: int) -> tuple:
    """(identifiants publics, empreintes, clés « même intitulé ») des fiches de l'organisation (hors
    supprimées)."""
    from app.services.preuves_reprise import cle_souple
    idents, emp, souples = set(), set(), set()
    for p in pv._q_org(db, owner_id).all():
        if p.empreinte:
            emp.add(p.empreinte)
        souples.add(cle_souple(p.nature, p.valeur or {}))
        s = p.source or {}
        if p.type_source == pv.PUBLIC and s.get("identifiant"):
            idents.add((_fold(s.get("nom")), _fold(s.get("identifiant"))))
    return idents, emp, souples


def _valeur_propre(nature: str, valeur: dict) -> tuple:
    """(valeur nettoyée, message) : un champ refusé par « Mes preuves » est écarté et dit, jamais corrigé."""
    from app.services.preuves_reprise import _propre
    return _propre(nature, valeur)


def _marquer(props: list, nature: str, nom_source: str, source_fn, consulte_le: str, existant: tuple,
             cle_de_part: Optional[set] = None) -> list:
    from app.services.preuves_reprise import cle_souple
    idents, emp, souples = existant
    out = []
    for p in props:
        q = dict(p)
        valeur, msg = _valeur_propre(nature, p.get("valeur") or {})
        if valeur is not None:
            # Le relevé ne garde que ce qui est enregistré (un champ refusé n'est pas « de la source »).
            q["releve"] = {k: v for k, v in (p.get("releve") or {}).items()
                           if k in valeur or k == pv.CHAMP_FIN}
        q["valeur"] = valeur if valeur is not None else dict(p.get("valeur") or {})
        if not q.get("manque") and valeur is None:
            q["manque"] = msg
        src = source_fn(q, consulte_le)
        if cle_de_part is not None:
            deja = _fold(_intitule(nature, q["valeur"])) in cle_de_part
            q["deja"] = bool(deja)
            q["deja_message"] = MSG_DEJA_PART if deja else ""
        else:
            deja = ((_fold(nom_source), _fold(src.get("identifiant"))) in idents
                    or (valeur is not None and pv.empreinte_de(nature, valeur) in emp)
                    or cle_souple(nature, q["valeur"]) in souples)
            q["deja"] = bool(deja)
            q["deja_message"] = MSG_DEJA if deja else ""
        attribue = nature == pv.REFERENCE
        q["texte"] = pv.texte_de(nature, q["valeur"], _date(q.get("date_fin_validite")), attribue=attribue)
        q["source_libelle"] = pv.LIB_DECP if nature == pv.REFERENCE else f"{pv.LIB_PUBLIC} : {nom_source}"
        q["source"] = {k: v for k, v in src.items() if k != "releve"}
        out.append(q)
    return out


def _date(v):
    from datetime import date
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _public(r: dict) -> dict:
    """Ce que l'écran reçoit (sans les champs internes)."""
    return {k: v for k, v in r.items() if not k.startswith("_")}


def apercu_marches(db, owner_id: int, user=None, siret: Optional[str] = None, existant=None,
                   cle_de_part: Optional[set] = None) -> dict:
    """Les marchés DECP de l'entreprise, proposés. Démo : l'exemple fictif, jamais le réseau."""
    if _est_demo(user):
        r = sp.exemple_fictif_marches()
    else:
        siret = siret if siret is not None else siret_de(db, owner_id)
        if not sp.clean_siren(siret):
            return {"statut": "siret_manquant", "message": MSG_SIRET if cle_de_part is None else MSG_SIRET_PART,
                    "marches": []}
        r = sp.marches(siret)
        r["siren"] = sp.clean_siren(siret)
    if r.get("statut") not in ("ok", "exemple"):
        return r
    ex = existant if existant is not None else (_existant(db, owner_id) if cle_de_part is None else None)
    r["marches"] = _marquer(r.get("marches") or [], pv.REFERENCE, sp.NOM_DECP, sp.source_decp,
                            r.get("consulte_le"), ex or (set(), set(), set()), cle_de_part)
    r["a_cocher"] = sum(1 for m in r["marches"] if not m["deja"] and not m.get("manque"))
    return r


def apercu_rge(db, owner_id: int, user=None, siret: Optional[str] = None, existant=None,
               cle_de_part: Optional[set] = None) -> dict:
    """Les qualifications RGE valables, proposées ; les expirées, signalées (jamais proposées)."""
    if _est_demo(user):
        r = sp.exemple_fictif_rge()
    else:
        siret = siret if siret is not None else siret_de(db, owner_id)
        if not sp.clean_siren(siret):
            return {"statut": "siret_manquant", "message": MSG_SIRET if cle_de_part is None else MSG_SIRET_PART,
                    "qualifications": [], "expirees": []}
        r = sp.qualifications_rge(siret)
        r["siren"] = sp.clean_siren(siret)
    if r.get("statut") not in ("ok", "exemple"):
        return r
    ex = existant if existant is not None else (_existant(db, owner_id) if cle_de_part is None else None)
    r["qualifications"] = _marquer(r.get("qualifications") or [], pv.QUALIFICATION, sp.NOM_RGE, sp.source_rge,
                                   r.get("consulte_le"), ex or (set(), set(), set()), cle_de_part)
    r["expirees"] = [{"nom": (x.get("affiche") or {}).get("nom") or (x.get("valeur") or {}).get("nom"),
                      "organisme": (x.get("affiche") or {}).get("organisme"),
                      "date_fin": (x.get("affiche") or {}).get("date_fin"), "message": x.get("message")}
                     for x in (r.get("expirees") or [])]
    r["a_cocher"] = sum(1 for m in r["qualifications"] if not m["deja"] and not m.get("manque"))
    return r


def _a_relire(db, owner_id: int, user, cles: Iterable, siret: Optional[str] = None,
              cle_de_part: Optional[set] = None) -> tuple:
    """(propositions retrouvées {cle: (nature, prop, consulte_le, nom_source)}, panne) pour les clés
    demandées : relues dans la lecture mise en cache (ou relues à la source), jamais prises du client."""
    voulues = {str(c) for c in (cles or []) if c}
    trouve, panne = {}, []
    if any(c.startswith("decp:") for c in voulues):
        r = apercu_marches(db, owner_id, user, siret=siret, cle_de_part=cle_de_part)
        if r.get("statut") in ("ok", "exemple"):
            for m in r["marches"]:
                if m["cle"] in voulues:
                    trouve[m["cle"]] = (pv.REFERENCE, m, r.get("consulte_le"), sp.NOM_DECP)
        else:
            panne.append(r.get("message") or sp.MSG_PANNE["decp"])
    if any(c.startswith("rge:") for c in voulues):
        r = apercu_rge(db, owner_id, user, siret=siret, cle_de_part=cle_de_part)
        if r.get("statut") in ("ok", "exemple"):
            for m in r["qualifications"]:
                if m["cle"] in voulues:
                    trouve[m["cle"]] = (pv.QUALIFICATION, m, r.get("consulte_le"), sp.NOM_RGE)
        else:
            panne.append(r.get("message") or sp.MSG_PANNE["rge"])
    return voulues, trouve, panne


def importer(db, owner_id: int, cles, user=None) -> dict:
    """Crée, dans « Mes preuves », les fiches COCHÉES (acceptées, source publique datée). Une ligne déjà
    présente n'est pas recréée ; une ligne qui ne peut pas devenir une fiche est dite. Une seule
    transaction ; la ligne du compte qui porte les données est verrouillée (Postgres)."""
    voulues, trouve, panne = _a_relire(db, owner_id, user, cles)
    db.query(User.id).filter(User.id == owner_id).with_for_update().first()
    creees, deja, ignorees = [], 0, []
    for cle in sorted(voulues):
        if cle not in trouve:
            if not panne:
                ignorees.append({"cle": cle, "texte": "", "message": MSG_PERIMEE})
            continue
        nature, m, consulte_le, _nom = trouve[cle]
        if m.get("deja"):
            deja += 1
            continue
        if m.get("manque"):
            ignorees.append({"cle": cle, "texte": m.get("texte") or "", "message": m["manque"]})
            continue
        src = sp.source_decp(m, consulte_le) if nature == pv.REFERENCE else sp.source_rge(m, consulte_le)
        src["releve"] = m.get("releve") or {}
        try:
            p = pv.creer(db, owner_id, nature=nature, valeur=m["valeur"], type_source=pv.PUBLIC, source=src,
                         date_fin_validite=m.get("date_fin_validite"), statut=pv.ACCEPTEE, origine="import_public",
                         user=user, commit=False)
        except pv.PreuveError as e:
            ignorees.append({"cle": cle, "texte": m.get("texte") or "", "message": e.message})
            if e.code == "trop_de_preuves":
                break
            continue
        creees.append(p)
    db.commit()
    for p in creees:
        db.refresh(p)
    return {"creees": creees, "deja": deja, "ignorees": ignorees, "pannes": panne}


# ── Le partenaire d'un groupement : SES sources, SES preuves, SA part ────────────────

def cles_de_part(c) -> set:
    """Intitulés (repliés) des références et qualifications déjà dans la part."""
    out = set()
    for r in (getattr(c, "references", None) or []):
        if isinstance(r, dict):
            out.add(_fold(r.get("intitule") or r.get("objet") or ""))
        elif r:
            out.add(_fold(r))
    for q in (getattr(c, "qualifications", None) or []):
        if isinstance(q, dict):
            out.add(_fold(q.get("name") or q.get("nom") or ""))
        elif q:
            out.add(_fold(q))
    out.discard("")
    return out


def apercu_part(db, inv, c, kind: str, demo: bool = False) -> dict:
    """Sources publiques lues avec le SIRET de la part du partenaire (jamais celui du chef de file)."""
    user = _DemoMarque() if demo else None
    siret = "".join(ch for ch in str(getattr(c, "siret", "") or "") if ch.isdigit())
    cles = cles_de_part(c)
    if kind == "rge":
        return apercu_rge(db, 0, user, siret=siret, cle_de_part=cles)
    return apercu_marches(db, 0, user, siret=siret, cle_de_part=cles)


def _ref_de_preuve(f: dict) -> dict:
    v = f.get("valeur") or {}
    r = {"intitule": v.get("objet") or ""}
    if v.get("acheteur"):
        r["client"] = v["acheteur"]
    if v.get("montant_ht") is not None:
        r["montant"] = v["montant_ht"]
    if v.get("annee"):
        r["annee"] = v["annee"]
    if v.get("role"):
        r["role"] = v["role"]
    if f.get("source_libelle") == pv.LIB_DECP:
        s = f.get("source") or {}
        r.update(provenance="decp", consulte_le=s.get("consulte_le") or "", identifiant=s.get("identifiant") or "")
    else:
        r["provenance"] = "mes_preuves"
    return r


def _ref_de_decp(m: dict, consulte_le: str) -> dict:
    v = m.get("valeur") or {}
    r = {"intitule": v.get("objet") or ""}
    if v.get("acheteur"):
        r["client"] = v["acheteur"]
    if v.get("montant_ht") is not None:
        r["montant"] = v["montant_ht"]
    if v.get("annee"):
        r["annee"] = v["annee"]
    if v.get("role"):
        r["role"] = v["role"]
    src = sp.source_decp(m, consulte_le)
    r.update(provenance="decp", consulte_le=consulte_le or "", identifiant=src.get("identifiant") or "")
    return r


def preuves_du_partenaire(db, owner_id: int, c) -> list:
    """SES références et qualifications UTILISABLES (acceptées, valables, source présente), pour sa part.
    Jamais une fiche d'une autre organisation, jamais un CV, jamais le chef de file."""
    cles = cles_de_part(c)
    out = []
    for f in pv.faits_autorises(db, owner_id, natures=[pv.REFERENCE, pv.QUALIFICATION]):
        v = f.get("valeur") or {}
        deja = _fold(_intitule(f["nature"], v)) in cles
        out.append({"id": f["id"], "nature": f["nature"], "nature_libelle": f["nature_libelle"],
                    "titre": pv.titre_court(f["nature"], v), "texte": f["texte"], "source_libelle": f["source_libelle"],
                    "date_fin_validite": f.get("date_fin_validite"),
                    "deja": deja, "deja_message": MSG_DEJA_PART if deja else ""})
    return out


def _intitule(nature: str, valeur: dict) -> str:
    """Ce qui entre dans la part : l'objet d'une référence, le nom d'une qualification (en entier)."""
    v = valeur or {}
    x = v.get("objet") if nature == pv.REFERENCE else v.get("nom")
    return str(x or "")


def prechauffer(siret: str, publiques: Iterable) -> None:
    """Lit (ou relit) les sources publiques demandées, pour que l'écriture qui suit trouve la lecture en
    cache sans appel réseau (aucune attente pendant qu'une ligne est verrouillée)."""
    cles = [str(x) for x in (publiques or ()) if x]
    if not sp.clean_siren(siret):
        return
    if any(c.startswith("decp:") for c in cles):
        sp.marches(siret)
    if any(c.startswith("rge:") for c in cles):
        sp.qualifications_rge(siret)


def reprendre_dans_part(db, c, *, publiques: Iterable = (), preuves: Iterable = (), owner_partenaire=None,
                        siret: str = "", demo: bool = False) -> dict:
    """Ajoute à la part ce que le partenaire a coché : références (avec leur provenance) et qualifications
    (leur intitulé, comme une saisie). Rien n'est retiré ni réécrit ; un élément déjà présent n'est pas
    doublé. Pas de commit : la route garde le verrou de version de la part et la transaction."""
    refs = [r for r in (c.references or []) if r]
    quals = [q for q in (c.qualifications or []) if q]
    cles = cles_de_part(c)
    ajout_refs, ajout_quals, deja, ignorees, provenances = [], [], 0, [], set()

    def _ajoute_ref(r: dict, texte: str):
        nonlocal deja
        k = _fold(r.get("intitule"))
        if not k:
            ignorees.append({"texte": texte, "message": "Référence sans intitulé."})
            return
        if k in cles:
            deja += 1
            return
        if len(refs) + len(ajout_refs) >= MAX_PART:
            ignorees.append({"texte": texte, "message": f"Une part compte au plus {MAX_PART} références."})
            return
        cles.add(k)
        ajout_refs.append(r)

    def _ajoute_qual(nom: str, texte: str):
        nonlocal deja
        nom = str(nom or "").strip()[:200]
        k = _fold(nom)
        if not k:
            return
        if k in cles:
            deja += 1
            return
        if len(quals) + len(ajout_quals) >= MAX_PART:
            ignorees.append({"texte": texte, "message": f"Une part compte au plus {MAX_PART} qualifications."})
            return
        cles.add(k)
        ajout_quals.append(nom)

    # 1) Ses preuves (compte seulement) : relues dans SON organisation, utilisables seulement.
    ids = set()
    for x in preuves or ():
        try:
            ids.add(int(x))
        except (TypeError, ValueError):
            continue
    if ids and owner_partenaire:
        faits = {f["id"]: f for f in pv.faits_autorises(db, owner_partenaire, natures=[pv.REFERENCE, pv.QUALIFICATION])}
        for i in sorted(ids):
            f = faits.get(i)
            if f is None:
                ignorees.append({"texte": "", "message": "Fiche introuvable ou plus utilisable dans vos preuves."})
                continue
            if f["nature"] == pv.REFERENCE:
                _ajoute_ref(_ref_de_preuve(f), f["texte"])
                provenances.add("preuves")
            else:
                _ajoute_qual((f.get("valeur") or {}).get("nom"), f["texte"])
                provenances.add("preuves")
    elif ids:
        ignorees.append({"texte": "", "message": "Connectez-vous au compte qui a rattaché ce lien pour reprendre vos "
                                                 "preuves."})

    # 2) Les sources publiques lues avec le SIRET de SA part (relues ici, jamais prises du client).
    pubs = [str(x) for x in (publiques or ()) if x]
    pannes = []
    if pubs:
        user = _DemoMarque() if demo else None
        voulues, trouve, pannes = _a_relire(db, 0, user, pubs, siret=siret, cle_de_part=set())
        for cle in sorted(voulues):
            if cle not in trouve:
                if not pannes:
                    ignorees.append({"texte": "", "message": MSG_PERIMEE})
                continue
            nature, m, consulte_le, _nom = trouve[cle]
            if m.get("manque"):
                ignorees.append({"texte": m.get("texte") or "", "message": m["manque"]})
                continue
            if nature == pv.REFERENCE:
                _ajoute_ref(_ref_de_decp(m, consulte_le), m.get("texte") or "")
                provenances.add("decp")
            else:
                _ajoute_qual((m.get("valeur") or {}).get("nom"), m.get("texte") or "")
                provenances.add("rge")
    if ajout_refs:
        c.references = list(refs) + ajout_refs
    if ajout_quals:
        c.qualifications = list(quals) + ajout_quals
    return {"references": ajout_refs, "qualifications": ajout_quals, "deja": deja, "ignorees": ignorees,
            "pannes": pannes, "provenances": sorted(provenances)}
