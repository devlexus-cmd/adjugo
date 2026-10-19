"""
AGENT 3 — RÉDACTEUR
Tâche : assembler le dossier de réponse : formulaires CERFA pré-remplis (DC1 en groupement,
DC2 par membre, ATTRI1), dossier ZIP téléchargeable, et le dossier de présentation (« mémoire
technique ») RÉDIGÉ DANS L'ATELIER (app/services/atelier.py).

Rédaction, vague 2 : l'ancien moteur qui écrivait tout le mémoire d'un seul appel à l'IA (et
fusionnait les apports des partenaires) est RETIRÉ. Le dossier commun prend le texte de
l'atelier, avec les mêmes règles que son export : rien si l'export est bloqué sans dérogation,
avertissement BLOQUANT tant que toutes les parties ne sont pas validées.

Prend en compte le groupement recommandé par l'Agent 2 : les co-traitants retenus
sont injectés dans le DC1 (section groupement) et un DC2 est généré par membre.
"""
import io
import re
import base64
import zipfile
from typing import Optional

# Avertissement (non bloquant) quand le règlement impose son propre cadre de réponse.
FICHIER_IMPOSE_WARNING = ("Dossier de présentation : l'acheteur impose son propre cadre de réponse. Recopiez-y "
                          "ce texte ; ne déposez pas le fichier Word d'Adjugo seul.")

# Dossiers du ZIP « Préparer mes documents » (réorganisation, vague 1 : noms lus par le client, sans « CERFA »
# ni « co-traitant » ; l'aperçu du dossier commun, app/routers/invites.py, reprend les mêmes).
DOSSIER_FORMULAIRES = "formulaires_officiels"
DOSSIER_PIECES_PARTENAIRES = "pieces_partenaires"

# Seuil (€ HT) au-delà duquel le DUME est ajouté d'office au dossier. Les procédures
# formalisées le rendent quasi incontournable ; ajustable selon la stratégie commerciale.
DUME_THRESHOLD = 90000

def _criteres_du_plan(details: dict) -> str:
    """Critères remis à la rédaction. Avec la grille « Comment vous serez noté » : seulement
    les lignes retrouvées dans le règlement ou confirmées par l'utilisateur, poids TEL QU'ÉCRIT
    (une ligne « à vérifier » n'entre pas dans le plan). Analyse plus ancienne (sans grille) :
    les NOMS proposés par l'IA, sans leurs poids, jamais contrôlés contre le texte."""
    g = (details or {}).get("grille_notation")
    if isinstance(g, dict):
        from app.services.grille_notation import plan_text
        return plan_text(g) or "non retrouvés dans le règlement (ne pas en inventer)"
    raw = (details or {}).get("criteres_attribution")
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return ""
    noms = []
    for x in raw:
        n = (x.get("critere") or x.get("intitule") or x.get("nom") or "") if isinstance(x, dict) else x
        n = re.sub(r"\s+", " ", str(n or "")).strip()[:160]
        if n and n not in noms:
            noms.append(n)
    if not noms:
        return ""
    return "; ".join(noms) + " (poids non contrôlés : n'en cite aucun et ne suppose aucun ordre d'importance)"


def build_dossier(analysis: dict, company: dict, cotraitants: list,
                  project_id: Optional[int] = None, lang_name: str = None,
                  country: str = "FR", db=None, user_id: int = None, estimate: dict = None) -> dict:
    """
    Génère le dossier complet.
    cotraitants : liste de dicts des co-traitants retenus dans le groupement.
    Retourne : {memoire, cerfas:[{id,name,content_b64}], zip_name, zip_b64, warnings}
    """
    details = analysis.get("details", {}) if analysis else {}
    company = company or {}
    cotraitants = cotraitants or []
    warnings = []

    # Parts SOUMISES des partenaires (réseau Adjugo) : leur identité juridique alimente les CERFA.
    # On EXCLUT les parts dont le lien a été révoqué OU décliné (partenaire sorti du groupement).
    # DOCTRINE DE VISIBILITÉ : seul le PRIX DE VENTE du lot (prix_lot_ht) est lisible ici
    # (ATTRI1/convention) ; detail_chiffre (enveloppe chiffrée) n'est JAMAIS lu.
    contributions = []
    if db is not None and project_id:
        try:
            from app.models import ProjectContribution, ProjectInvite
            from app.services.groupement_members import active_invite_filter
            rows = db.query(ProjectContribution).join(
                ProjectInvite, ProjectContribution.invite_id == ProjectInvite.id).filter(
                ProjectContribution.project_id == project_id,
                ProjectContribution.status == "submitted",
                active_invite_filter()).all()
            contributions = [{
                "company_name": c.company_name, "role": c.role, "lot": c.lot,
                "siret": getattr(c, "siret", "") or "", "forme_juridique": getattr(c, "forme_juridique", "") or "",
                "address": getattr(c, "address", "") or "", "postal_code": getattr(c, "postal_code", "") or "",
                "city": getattr(c, "city", "") or "", "contact": c.contact or {},
                "prix_lot_ht": getattr(c, "prix_lot_ht", None), "status": c.status,
            } for c in rows]
        except Exception:
            contributions = []

    # Pièces administratives des co-traitants (parts SOUMISES) → assemblées dans le ZIP.
    cotraitant_pieces = []
    if db is not None and project_id:
        try:
            from app.models import ContributionPiece, ProjectContribution, ProjectInvite
            from app.services.groupement_members import active_invite_filter
            prows = db.query(ContributionPiece, ProjectContribution).join(
                ProjectContribution, ContributionPiece.contribution_id == ProjectContribution.id).join(
                ProjectInvite, ProjectContribution.invite_id == ProjectInvite.id).filter(
                ContributionPiece.project_id == project_id,
                ProjectContribution.status == "submitted",
                active_invite_filter()).all()
            cotraitant_pieces = [{"company": (cb.company_name or "cotraitant"),
                                  "name": pc.name, "file_key": pc.file_key} for pc, cb in prows]
        except Exception:
            cotraitant_pieces = []

    # ── Dossier de présentation = le texte de l'ATELIER (aucun appel à l'IA ici) ──
    # Mêmes règles que l'export de l'atelier : rien n'est joint si l'export est bloqué sans
    # dérogation (« [À compléter] », fait à relire non traité, partie vide, limite dépassée) ;
    # avertissement BLOQUANT tant que toutes les parties ne sont pas validées. Jamais de message
    # technique dans le livrable.
    from app.services import memoire_export
    memoire_label = memoire_export.memoire_label(analysis)
    memoire_files, memoire_md, memoire_etat, memoire_garder = {}, "", None, []
    if db is not None and project_id:
        try:
            from app.services import atelier
            from app.models import Project as _P, User as _U
            from app.core.org import data_owner_id
            _proj = db.query(_P).filter(_P.id == project_id).first()
            _u = db.get(_U, user_id) if user_id else None
            _owner = data_owner_id(_u, db) if _u is not None else (_proj.user_id if _proj else None)
            if _proj is not None and _owner is not None:
                commun = atelier.dossier_commun(db, _proj, _owner)
                memoire_files, memoire_md = commun["files"], commun["markdown"]
                memoire_etat = commun["etat"]
                memoire_garder = list(commun.get("garder") or [])
                warnings.extend(commun["warnings"])
        except Exception as e:
            import logging
            logging.getLogger("adjugo").warning("dossier de présentation de l'atelier indisponible (projet %s) : %s",
                                                project_id, type(e).__name__)
            memoire_files, memoire_md = {}, ""
            warnings.append("BLOQUANT — Le dossier de présentation n'a pas pu être joint : ouvrez l'atelier "
                            "(sur la page du marché, carte « Dossier de présentation ») puis relancez l'assemblage.")
    else:
        warnings.append("BLOQUANT — Dossier de présentation non rédigé : préparez-le dans l'atelier (sur la page "
                        "du marché, carte « Dossier de présentation »).")
    # Le règlement impose son propre cadre de réponse : le fichier Word d'Adjugo ne se dépose pas
    # seul (avertissement non bloquant, affiché avec le dossier).
    _gn = details.get("grille_notation") if isinstance(details, dict) else None
    if isinstance(_gn, dict) and ((_gn.get("contraintes") or {}).get("fichier_impose")):
        warnings.append(FICHIER_IMPOSE_WARNING)

    # Taux de TVA piloté par le projet (0 % par défaut — art. 293 B CGI).
    tva_rate = 0
    if db is not None and project_id:
        try:
            from app.models import Project
            proj = db.query(Project).filter(Project.id == project_id).first()
            tva_rate = (getattr(proj, "tva_rate", 0) or 0) if proj else 0
        except Exception:
            tva_rate = 0

    # Co-traitants pour les CERFA : on FUSIONNE la liste fournie (SIRET vérifiés) avec
    # l'identité juridique réellement SOUMISE par les partenaires invités (réseau Adjugo)
    # → leurs DC1/DC2 multi-membres sont enfin alimentés par leurs propres contributions.
    cerfa_cotraitants = list(cotraitants or [])
    _seen_sir = {str(c.get("siret") or "").strip() for c in cerfa_cotraitants if c.get("siret")}
    for c in contributions:
        if c.get("status") != "submitted":
            continue
        sir = str(c.get("siret") or "").strip()
        if sir and sir in _seen_sir:
            continue
        if not (c.get("company_name") or sir):
            continue
        cerfa_cotraitants.append({
            "name": c.get("company_name", ""), "siret": sir,
            "forme_juridique": c.get("forme_juridique", ""), "address": c.get("address", ""),
            "postal_code": c.get("postal_code", ""), "city": c.get("city", ""),
            "email": (c.get("contact") or {}).get("email", ""),
            "phone": (c.get("contact") or {}).get("telephone", ""),
            "role": c.get("role", "cotraitant"), "lot": c.get("lot", ""),
        })
        if sir:
            _seen_sir.add(sir)

    # ── CERFA ──
    # Montant de l'ATTRI1 (acte d'engagement) = chiffrage RÉEL du candidat (estimate.total_ht),
    # JAMAIS le budget estimé de l'ACHETEUR (details.budget_estime) — sinon on engage l'entreprise
    # sur un prix qu'elle n'a pas calculé. None si pas chiffré → l'ATTRI1 affiche « À COMPLÉTER ».
    _real_ht = (estimate or {}).get("total_ht") if isinstance(estimate, dict) else None
    if not _real_ht:
        warnings.append("Montant d'engagement (ATTRI1) vide : chiffrez le marché avant de déposer.")
    from app.services.cerfa import reference_consultation as _reference_consultation
    project_data = {
        "name": details.get("intitule_marche", "Marché public"),
        "client": details.get("acheteur", ""),
        "budget": _real_ht,  # None → ATTRI1 « À COMPLÉTER » (jamais un prix inventé)
        "tva_rate": tva_rate,
        "reference": _reference_consultation(analysis),   # l'avis publié, jamais le n° interne d'Adjugo
        "cotraitants": cerfa_cotraitants,   # ← DC1 groupement / DC2 multi-membres (incl. contributions)
    }

    # ── Convention de groupement (vague 2) ── si elle est générée et à jour, les CERFA reprennent
    # SES membres, lots, prix, forme et habilitation, et son PDF (accords inclus) remplace le
    # modèle à compléter. Le mémoire est DÉJÀ rédigé ci-dessus : la convention n'est JAMAIS
    # transmise au LLM (invariant de la doctrine de visibilité).
    convention_pdf, _grp_conv = None, None
    if db is not None and project_id:
        try:
            from app.models import Project as _Project
            from app.services import groupement_convention as _gc
            _proj = db.query(_Project).filter(_Project.id == project_id).first()
            if _proj is not None:
                _grp_conv = _gc.apply_to_cerfa(db, _proj, company, project_data)
                if _grp_conv:
                    cerfa_cotraitants = project_data["cotraitants"]
                    act = _gc.active_convention_pdf(db, _proj)
                    if act:
                        convention_pdf, _conv = act
                        if _conv.status != "signee":
                            _sigs = _gc.signatures_of(db, _conv)
                            warnings.append("Convention de groupement générée mais pas encore validée par tous "
                                            f"(accords {sum(1 for s in _sigs if s.status in ('signed', 'hors_ligne'))}"
                                            f" sur {len(_sigs)}).")
                else:
                    _conv = _gc.get_convention(db, project_id)
                    if _conv is not None and _conv.status == "perimee":
                        warnings.append("La convention de groupement n'est plus à jour (une part, un prix ou la "
                                        "composition a changé) : régénérez-la avant de déposer.")
                    elif _conv is not None and _conv.status == "draft":
                        warnings.append("Convention de groupement en brouillon : générez-la dans « Convention et "
                                        "accords » (page du marché, étape Préparer) pour que chaque membre la valide.")
        except Exception as e:
            warnings.append(f"convention de groupement : {e}")

    # ── Pare-feu : champs critiques manquants = pli rejeté. On signale (bloquant,
    # remonté en rouge côté front) sans empêcher l'assemblage du brouillon.
    try:
        from app.services.cerfa import missing_company_fields
        miss = missing_company_fields(company)
        if miss:
            warnings.append("BLOQUANT — profil entreprise incomplet (rejet probable du pli) : "
                            + ", ".join(miss))
    except Exception:
        pass

    # Composition du dossier selon le PAYS :
    #  - France : CERFA DC1/DC2/(DC4)/ATTRI1 + DUME sur gros marchés.
    #  - Autres pays UE adaptés : les CERFA français ne s'appliquent pas → le document
    #    de candidature est l'ESPD (= DUME), toujours inclus, dans la langue locale.
    # DC4 (déclaration de sous-traitance) : dès qu'il y a un GROUPEMENT/consortium, on le
    # génère pré-rempli — la sous-traitance est fréquente en groupement et l'acheteur
    # l'exige le cas échéant ; mieux vaut le fournir prêt que de l'oublier.
    # DC4 = déclaration de SOUS-TRAITANCE : on ne le joint que si un partenaire est
    # réellement déclaré sous-traitant (role sous_traitant), pas pour un simple groupement
    # de co-traitants — sinon on ajoutait un DC4 sans objet à chaque dossier.
    from app.services.cerfa import _soustraitants
    has_soustraitance = bool(_soustraitants(cerfa_cotraitants))
    # Membres du groupement (co-traitants) dont le représentant légal (signataire du DC2)
    # est manquant : leur DC2 serait non signable → on avertit (bloquant) plutôt que de
    # produire un DC2 vide en silence.
    from app.services.cerfa import _groupement_members
    _missing_rep = [ct.get("name") or ct.get("siret") or "un partenaire du groupement"
                    for ct in _groupement_members(cerfa_cotraitants)
                    if not str(ct.get("representant_legal") or "").strip()]
    if _missing_rep:
        warnings.append("BLOQUANT — représentant légal (signataire du DC2) manquant pour : "
                        + ", ".join(_missing_rep) + ". Demandez-le au partenaire avant dépôt.")
    if (country or "FR").upper() == "FR":
        include_dume = (project_data.get("budget") or 0) >= DUME_THRESHOLD
        # "honneur" = déclaration sur l'honneur (R2143-3), pièce obligatoire de tout pli FR.
        cerfa_ids = ["dc1", "dc2"] + (["dc4"] if has_soustraitance else []) + ["attri1", "honneur"] \
            + (["dume"] if include_dume else [])
    else:
        cerfa_ids = ["dume"]   # ESPD localisé = pièce de candidature paneuropéenne
    cerfa_files = []
    try:
        from app.services.cerfa import GENERATORS
        for cid in cerfa_ids:
            gen = GENERATORS.get(cid)
            if not gen:
                continue
            try:
                content = gen(company, project_data) if cid != "dume" else gen(company, project_data, lang_name)
                cerfa_files.append({"id": cid, "name": f"{cid.upper()}.pdf", "content": content})
            except Exception as e:
                warnings.append(f"{cid}: {e}")
    except Exception as e:
        warnings.append(f"formulaires officiels indisponibles : {e}")
    if _grp_conv and db is not None and project_id:
        # Formulaires produits APRÈS la convention : compte pour l'état « prêt à déposer ».
        from app.services.groupement_convention import mark_cerfa_generated
        mark_cerfa_generated(db, project_id, [c["id"] for c in cerfa_files if c["id"] in ("dc1", "dc2", "attri1")],
                             _grp_conv.get("convention_version"))

    # ── Formulaire national supplémentaire (PL, PT, IT, NL, RO) ──
    if (country or "FR").upper() != "FR":
        try:
            from app.services.national_forms import form_spec
            from app.services.cerfa import generate_national_form
            spec = form_spec(country)
            if spec:
                content = generate_national_form(company, project_data, spec)
                fname = re.sub(r"[^\w]+", "_", spec.get("form_name") or "Formulaire").strip("_")[:40] + ".pdf"
                cerfa_files.append({"id": "national", "name": fname, "content": content})
        except Exception as e:
            warnings.append(f"formulaire national: {e}")

    # ── Convention de groupement : la VRAIE (générée, accords inclus) si elle existe ; sinon
    #    le modèle à compléter/signer (comportement historique) si groupement.
    convention_md = ("" if convention_pdf else
                     (_groupement_convention(company, cerfa_cotraitants, details) if cerfa_cotraitants else ""))

    # ── ZIP ──
    zip_bytes, zip_name, failed_pieces = _build_zip(memoire_files, cerfa_files, company, details, cerfa_cotraitants, project_id,
                                                    cotraitant_pieces, convention_md, convention_pdf=convention_pdf)
    if failed_pieces:
        warnings.append("Pièces partenaires non jointes au dossier (à re-déposer) : "
                        + ", ".join(failed_pieces[:8]))

    return {
        "memoire_markdown": memoire_md,
        "memoire_preview": _preview(memoire_md, 400),
        "memoire_nom": memoire_label,
        "memoire_fichiers": [name for name, _b in memoire_files.values()],
        "memoire_etat": memoire_etat,
        # Octets des fichiers (archivage dans le dossier du marché) : retirés par la route avant la
        # réponse JSON (ils sont déjà dans le ZIP).
        "_memoire_files": memoire_files,
        # Fichiers d'un lot NON joint (bloqué) : gardés tels quels dans le dossier du marché (rédaction, vague 6).
        "_memoire_garder": memoire_garder,
        "cerfas": [{"id": c["id"], "name": c["name"],
                    "content_b64": base64.b64encode(_as_bytes(c["content"])).decode()}
                   for c in cerfa_files],
        "zip_name": zip_name,
        "zip_b64": base64.b64encode(zip_bytes).decode(),
        "warnings": warnings,
    }


def _groupement_convention(company, cotraitants, details):
    """Brouillon de convention de groupement momentané d'entreprises (à relire/signer).
    Désigne le mandataire et liste les membres + leurs lots. Pièce attendue par
    l'acheteur sur les marchés en groupement."""
    mand = (company.get("name") if isinstance(company, dict) else "") or "Entreprise à préciser"
    # Rôle affiché en clair (jamais le code brut « sous_traitant » / « mandataire »).
    role_lbl = {"cotraitant": "co-traitant", "sous_traitant": "sous-traitant", "mandataire": "chef de file"}
    lines = [
        "# Convention de groupement momentané d'entreprises",
        "",
        "*Projet à relire, compléter et faire signer par chaque membre. Modèle Adjugo — "
        "ne dispense pas d'une validation juridique.*",
        "",
        f"**Marché :** {details.get('intitule_marche','')}",
        f"**Acheteur :** {details.get('acheteur','')}",
        "",
        "## Article 1 — Membres du groupement",
        f"- **{mand}** — chef de file (mandataire du groupement)",
    ]
    for c in cotraitants:
        ident = c.get("name", "")
        extra = " — ".join(x for x in [c.get("lot") and f"lot : {c['lot']}",
                                       c.get("siret") and f"SIRET {c['siret']}"] if x)
        role = str(c.get("role") or "cotraitant")
        lines.append(f"- {ident}" + (f" ({extra})" if extra else "") + f" — {role_lbl.get(role, role)}")
    lines += [
        "",
        "## Article 2 — Forme du groupement",
        "Le groupement est **conjoint** / **solidaire** *(rayer la mention inutile)*. En cas "
        "de groupement conjoint, le chef de file (mandataire) est solidaire de chacun des membres pour "
        "l'exécution du marché.",
        "",
        "## Article 3 — Chef de file (mandataire)",
        # Tournure sans accord (nom d'entreprise ou repli « Entreprise à préciser ») : jamais
        # « Entreprise à préciser est désigné … Il représente ».
        f"Est désigné chef de file (mandataire du groupement) : {mand}. Le chef de file représente "
        "l'ensemble des membres vis-à-vis de l'acheteur, coordonne les prestations et est "
        "l'interlocuteur unique.",
        "",
        "## Article 4 — Répartition des prestations et de la rémunération",
        "Chaque membre exécute le(s) lot(s) indiqué(s) à l'article 1 et perçoit la part de "
        "rémunération correspondante, selon la décomposition jointe (DPGF/BPU).",
        "",
        "## Article 5 — Durée",
        "La présente convention prend effet à la date de signature et reste valable pendant "
        "toute la durée d'exécution du marché et de la période de garantie.",
        "",
        "## Signatures",
        "Fait à ……………………, le ……………………, en autant d'exemplaires que de membres.",
        "",
    ]
    for c in [{"name": mand}] + list(cotraitants):
        lines.append(f"- {c.get('name','')} : ……………………………… (nom, qualité, signature)")
    return "\n".join(lines)


def _build_zip(memoire_files, cerfa_files, company, details, cotraitants, project_id, cotraitant_pieces=None, convention_md="",
               convention_pdf=None):
    """`memoire_files` = {"docx": (nom, octets), "pdf": (nom, octets)} (vide si la rédaction a
    échoué : aucun fichier de mémoire plutôt qu'un fichier qui contiendrait un message d'erreur)."""
    import os
    buf = io.BytesIO()
    failed_pieces = []
    ao = re.sub(r"[^\w\s-]", "", details.get("intitule_marche") or "")[:40].strip() or f"marche_{project_id or 0}"
    zip_name = f"Adjugo_Dossier_{ao}.zip".replace(" ", "_")

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Dossier de présentation en Word (à relire et compléter) ET en PDF, sous le nom du règlement.
        from app.services.md_pdf import markdown_to_pdf, text_to_pdf
        for _kind, (name, content) in sorted((memoire_files or {}).items()):
            zf.writestr(name, content)
        for c in cerfa_files:
            zf.writestr(f"{DOSSIER_FORMULAIRES}/{c['name']}", _as_bytes(c["content"]))
        zf.writestr("synthese_groupement.pdf",
                    text_to_pdf(_groupement_recap(company, cotraitants, details), "Composition du groupement"))
        zf.writestr("fiche_appel_offres.pdf", text_to_pdf(_ao_recap(details), "Fiche récapitulative du marché"))
        if convention_pdf:
            # Convention GÉNÉRÉE (texte figé + accords enregistrés) : remplace le modèle.
            zf.writestr("convention_groupement.pdf", convention_pdf)
        elif convention_md:
            try:
                zf.writestr("convention_groupement.pdf",
                            markdown_to_pdf(convention_md, "Convention de groupement"))
            except Exception:
                pass

        # Pièces administratives des co-traitants (assemblage automatique du groupement).
        if cotraitant_pieces:
            from app.services.storage import get_storage
            storage = get_storage()
            seen = set()
            for p in cotraitant_pieces:
                try:
                    content = storage.load(p["file_key"])
                except Exception:
                    # Ne plus avaler silencieusement : le mandataire doit savoir qu'une
                    # pièce partenaire manque au ZIP (sinon dossier commun incomplet déposé).
                    failed_pieces.append(f"{p.get('company') or 'partenaire'} — {p.get('name') or 'pièce'}")
                    continue
                co = re.sub(r"[^\w\s-]", "", p.get("company", "") or "partenaire")[:40].strip() or "partenaire"
                nm = os.path.basename(p.get("name", "") or "piece") or "piece"
                path = f"{DOSSIER_PIECES_PARTENAIRES}/{co}/{nm}"
                i = 2
                while path in seen:        # évite l'écrasement si deux pièces de même nom
                    stem, dot, ext = nm.rpartition(".")
                    nm2 = (f"{stem}_{i}{dot}{ext}" if dot else f"{nm}_{i}")
                    path = f"{DOSSIER_PIECES_PARTENAIRES}/{co}/{nm2}"
                    i += 1
                seen.add(path)
                zf.writestr(path, content)
    return buf.getvalue(), zip_name, failed_pieces


def _groupement_recap(company, cotraitants, details):
    lines = ["COMPOSITION DU GROUPEMENT — ADJUGO", "=" * 45, ""]
    lines.append(f"Marché : {details.get('intitule_marche','')}")
    lines.append(f"Chef de file : {company.get('name','')} ({company.get('siret','')})")
    lines.append("")
    if cotraitants:
        lines.append("Partenaires du groupement :")
        for c in cotraitants:
            lines.append(f"  - {c.get('name','')} | {c.get('specialites','')} | SIRET {c.get('siret','')}")
    else:
        lines.append("Candidature en entreprise seule.")
    return "\n".join(lines)


def _ao_recap(details):
    lines = ["FICHE RÉCAPITULATIVE DU MARCHÉ", "=" * 45, ""]
    for k, v in (details or {}).items():
        if isinstance(v, (str, int, float)) and str(v).strip():
            lines.append(f"{k.replace('_',' ').title()} : {v}")
    return "\n".join(lines)


def _parse_amount(v) -> float:
    """Montant € robuste, y compris formats compacts (« 8 M€ », « 1,5 M€ HT », « 300 k€ »).
    L'ancienne version renvoyait 8 pour « 8 M€ » (multiplicateur ignoré)."""
    if isinstance(v, (int, float)):
        return float(v)
    if not v:
        return 0.0
    s = str(v).lower().replace("\xa0", " ").replace(" ", " ")
    mult = 1.0
    if re.search(r"milliard|\bmd\b", s):
        mult = 1e9
    elif re.search(r"million|m€|\bm\b|\bmio\b", s):
        mult = 1e6
    elif re.search(r"millier|k€|\bk\b", s):
        mult = 1e3
    m = re.search(r"\d[\d .,]*", s)
    if not m:
        return 0.0
    num = m.group(0).strip().replace(" ", "")   # l'espace = séparateur de milliers en FR
    if "," in num and "." in num:               # le dernier séparateur est décimal
        if num.rfind(",") > num.rfind("."):
            num = num.replace(".", "").replace(",", ".")
        else:
            num = num.replace(",", "")
    elif "," in num:
        num = num.replace(",", ".")
    try:
        return float(num.rstrip(".")) * mult
    except ValueError:
        return 0.0


def _as_bytes(content) -> bytes:
    return content if isinstance(content, bytes) else str(content).encode("utf-8")


def _preview(md: str, n: int = 400) -> str:
    clean = re.sub(r"#{1,6}\s+", "", md or "")
    clean = re.sub(r"\*\*(.+?)\*\*", r"\1", clean).strip()
    return clean[:n] + ("…" if len(clean) > n else "")
