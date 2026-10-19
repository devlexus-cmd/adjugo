"""
Adjugo - Export dossier complet
Genere un ZIP avec tous les CERFA + documents du coffre-fort pour un projet.
"""
import io
import os
import zipfile
import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.org import data_owner_id, member_ids
from app.core.http import content_disposition
from app.services.storage import get_storage
from app.models import User, Project, Company, Document
from app.services.cerfa import GENERATORS, reference_consultation

router = APIRouter(prefix="/api/export", tags=["Export dossier"])

UPLOADS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads"
)


@router.post("/{project_id}")
def export_dossier(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(
        Project.id == project_id, Project.user_id.in_(member_ids(current_user, db))
    ).first()
    if not project:
        raise HTTPException(404, "Projet introuvable")

    company = db.query(Company).filter(Company.user_id == data_owner_id(current_user, db)).first()
    if not company:
        raise HTTPException(400, "Renseignez votre entreprise dans Mon entreprise, onglet « Identité ».")

    # Preparer les donnees entreprise
    cd = {}
    for k in ["name", "siret", "code_ape", "forme_juridique", "capital",
              "representant_legal", "address", "city", "postal_code",
              "tva_intracom", "ca_n1", "ca_n2", "ca_n3", "effectif",
              "email", "phone"]:
        cd[k] = getattr(company, k, "") or ""
    cd["qualifications"] = company.qualifications or []

    # Montant d'engagement (ATTRI1) = chiffrage RÉEL du candidat, JAMAIS le budget supposé de
    # l'acheteur ni 0. None si non chiffré → l'acte d'engagement affiche « à compléter ».
    est = project.estimate if isinstance(project.estimate, dict) else {}
    pd = {
        "name": project.name,
        "client": project.client or "",
        "budget": est.get("total_ht"),
        # SANS ça, l'ATTRI1 du ZIP affichait toujours « 0 % — TVA non applicable » (TTC=HT),
        # même quand le client avait choisi 20 % — un acte d'engagement à la TVA fausse.
        "tva_rate": getattr(project, "tva_rate", 0) or 0,
        "reference": reference_consultation(project.ai_analysis),   # l'avis publié, jamais le n° interne
        "cotraitants": [],
    }

    # Entreprises RATTACHÉES À CE MARCHÉ uniquement (pas tout le carnet d'adresses de l'org), role/lot
    # venant du LIEN (co-traitant → DC1/DC2, sous-traitant → DC4). Seulement les sous-traitants
    # déclarés et les partenaires dont l'invitation est ACCEPTÉE (aucune entreprise sans son accord).
    # Celles qui en sont écartées faute d'accord sont dites dans le sommaire et à l'écran.
    avertissements = []
    try:
        from app.services.groupement_members import avertissements_formulaires, cotraitants_pour_formulaires
        _form = cotraitants_pour_formulaires(db, project_id)
        pd["cotraitants"].extend(_form["lignes"])
        avertissements = avertissements_formulaires(_form)
    except Exception:
        pass

    # Groupements montés via le réseau Adjugo (invitation → contribution SOUMISE, lien non
    # révoqué) : SANS ça, le ZIP « dossier complet » sortait un DC1 « candidat seul » alors
    # que build_dossier (bouton « Télécharger ») déclarait bien le groupement — incohérence.
    try:
        from app.models import ProjectContribution, ProjectInvite
        from app.services.groupement_members import active_invite_filter
        _seen_sir = {str(c.get("siret") or "").strip() for c in pd["cotraitants"] if c.get("siret")}
        rows = db.query(ProjectContribution).join(
            ProjectInvite, ProjectContribution.invite_id == ProjectInvite.id).filter(
            ProjectContribution.project_id == project_id,
            ProjectContribution.status == "submitted",
            active_invite_filter()).all()
        for c in rows:
            sir = str(getattr(c, "siret", "") or "").strip()
            if sir and sir in _seen_sir:
                continue
            if not ((c.company_name or "") or sir):
                continue
            contact = c.contact or {}
            pd["cotraitants"].append({
                "name": c.company_name or "", "siret": sir,
                "forme_juridique": getattr(c, "forme_juridique", "") or "",
                "address": getattr(c, "address", "") or "", "postal_code": getattr(c, "postal_code", "") or "",
                "city": getattr(c, "city", "") or "",
                "email": contact.get("email", ""), "phone": contact.get("telephone", ""),
                # role/lot : co-traitant → DC1/DC2 ; sous-traitant → DC4 (cf. cerfa._is_soustraitant).
                "role": getattr(c, "role", "") or "cotraitant", "lot": getattr(c, "lot", "") or "",
            })
            if sir:
                _seen_sir.add(sir)
    except Exception:
        pass

    # Convention de groupement générée et à jour : les CERFA reprennent SES membres, lots,
    # prix, forme et habilitation (le dossier dit partout la même chose), et le PDF de la
    # convention (avec les accords enregistrés) rejoint le ZIP.
    from app.services.groupement_convention import active_convention_pdf, apply_to_cerfa, STATUS_LABELS
    grp = apply_to_cerfa(db, project, cd, pd)
    conv_pdf = active_convention_pdf(db, project) if grp else None

    # Creer le ZIP
    zip_buf = io.BytesIO()
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    project_slug = project.name.replace(" ", "_")[:30]

    # DC4 (déclaration de sous-traitance) UNIQUEMENT si un sous-traitant est déclaré —
    # sinon on joignait un DC4 vide/sans objet à chaque dossier de groupement.
    from app.services.cerfa import _soustraitants
    _has_soustraitance = bool(_soustraitants(pd.get("cotraitants", [])))

    cerfa_ok = []
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Generer les CERFA (DC4 seulement en cas de sous-traitance)
        for doc_type, generator in GENERATORS.items():
            if doc_type == "dc4" and not _has_soustraitance:
                continue
            try:
                pdf_bytes = generator(cd, pd)
                filename = "01_Formulaires_officiels/{}_{}_{}.pdf".format(
                    doc_type.upper(), project_slug, date_str
                )
                zf.writestr(filename, pdf_bytes)
                cerfa_ok.append(doc_type)
            except Exception as e:
                # Ajouter un fichier d'erreur
                zf.writestr(
                    "01_Formulaires_officiels/{}_ERREUR.txt".format(doc_type.upper()),
                    "Erreur generation {}: {}".format(doc_type.upper(), str(e))
                )

        # 1 bis. Convention de groupement (texte figé + accords enregistrés)
        if conv_pdf:
            zf.writestr("03_Groupement/Convention_de_groupement_v{}.pdf".format(conv_pdf[1].version), conv_pdf[0])

        # 2. Documents : CE marché (project_id) + pièces générales du coffre-fort (project_id NULL,
        #    type Kbis/attestations valables pour tout pli) — JAMAIS les documents d'un AUTRE
        #    marché ; ni la corbeille (deleted_at) ni les versions remplacées (parent_id).
        documents = db.query(Document).filter(
            Document.user_id.in_(member_ids(current_user, db)),
            Document.deleted_at.is_(None),
            Document.parent_id.is_(None),
            ((Document.project_id == project_id) | (Document.project_id.is_(None))),
        ).all()

        storage = get_storage()
        for doc in documents:
            category = str(getattr(doc.category, "value", doc.category) or "autre")
            content = None
            if doc.file_key:
                try:
                    content = storage.load(doc.file_key)   # stockage objet (R2/local)
                except Exception:
                    content = None
            if content:
                ext = (os.path.splitext(doc.file_key)[1]
                       or os.path.splitext(doc.name)[1] or ".pdf")
                safe_name = doc.name.replace("/", "_").replace(" ", "_")
                if safe_name.lower().endswith(ext.lower()):     # « Kbis.pdf » → « Kbis.pdf », jamais « Kbis.pdf.pdf »
                    ext = ""
                filename = "02_Documents/{}/{}{}".format(category.capitalize(), safe_name, ext)
                zf.writestr(filename, content)
            else:
                # Document en base mais fichier introuvable dans le stockage
                zf.writestr(
                    "02_Documents/{}.txt".format(doc.name.replace(" ", "_")),
                    "Document reference: {}\nCategorie: {}\nFichier non disponible sur le serveur.".format(
                        doc.name, category
                    )
                )

        # 3. Generer un sommaire
        sommaire = []
        sommaire.append("=" * 60)
        sommaire.append("DOSSIER DE REPONSE - APPEL D'OFFRES")
        sommaire.append("=" * 60)
        sommaire.append("")
        sommaire.append("Projet : " + project.name)
        sommaire.append("Client : " + (project.client or ""))
        if grp and grp.get("total_ht") is not None:
            sommaire.append("Montant de l'offre commune du groupement (HT) : "
                            + "{:,.2f} EUR".format(grp["total_ht"]).replace(",", " "))
        else:
            sommaire.append("Montant de l'offre (HT) : " + ("{:,.0f} EUR".format(est.get("total_ht")).replace(",", " ") if est.get("total_ht") else "à chiffrer (aucun chiffrage enregistré)"))
        sommaire.append("Reference : marche n° {:04d}".format(project.id))
        sommaire.append("Date : " + date_str)
        sommaire.append("")
        sommaire.append("-" * 60)
        sommaire.append("ENTREPRISE CANDIDATE")
        sommaire.append("-" * 60)
        sommaire.append("Denomination : " + cd.get("name", ""))
        sommaire.append("SIRET : " + cd.get("siret", ""))
        sommaire.append("Adresse : " + cd.get("address", "") + " " + cd.get("city", ""))
        sommaire.append("Representant : " + cd.get("representant_legal", ""))
        try:
            _ca1 = float(cd.get("ca_n1") or 0)
        except (TypeError, ValueError):
            _ca1 = 0   # CA stocké en texte → ne fait plus planter TOUT l'export ZIP
        sommaire.append("CA N-1 : " + ("{:,.0f} EUR".format(_ca1).replace(",", " ") if _ca1 else "—"))
        sommaire.append("")

        if pd["cotraitants"]:
            sommaire.append("-" * 60)
            sommaire.append("PARTENAIRES DU GROUPEMENT ({})".format(len(pd["cotraitants"])))
            sommaire.append("-" * 60)
            for i, ct in enumerate(pd["cotraitants"]):
                sommaire.append("{}. {} - SIRET: {}".format(i + 1, ct.get("name", ""), ct.get("siret", "")))
            sommaire.append("")

        if avertissements:
            sommaire.append("-" * 60)
            sommaire.append("A VERIFIER AVANT DEPOT")
            sommaire.append("-" * 60)
            for a in avertissements:
                sommaire.append("- " + a)
            sommaire.append("")

        sommaire.append("-" * 60)
        sommaire.append("CONTENU DU DOSSIER")
        sommaire.append("-" * 60)
        sommaire.append("")
        sommaire.append("01_Formulaires_officiels/")
        # Dérivé de GENERATORS (sinon le sommaire listait 4 CERFA alors que le ZIP en contient 6 :
        # la déclaration sur l'honneur OBLIGATOIRE et le DUME manquaient au sommaire).
        for dt in GENERATORS:
            if dt == "dc4" and not _has_soustraitance:   # cohérent avec le ZIP réellement généré
                continue
            sommaire.append("  - {}_{}_{}.pdf".format(dt.upper(), project_slug, date_str))
        sommaire.append("")
        sommaire.append("02_Documents/")
        for doc in documents:
            # .value : sinon le sommaire affichait « DocCategory.administratif » (repr de l'enum).
            cat = getattr(doc.category, "value", doc.category) or "autre"
            sommaire.append("  - {} ({})".format(doc.name, cat))
        if conv_pdf:
            c_ = conv_pdf[1]
            sommaire.append("")
            sommaire.append("03_Groupement/")
            sommaire.append("  - Convention_de_groupement_v{}.pdf ({})".format(
                c_.version, STATUS_LABELS.get(c_.status, c_.status)))

        sommaire.append("")
        sommaire.append("=" * 60)
        sommaire.append("Genere par adjugo. le " + date_str)

        zf.writestr("00_SOMMAIRE.txt", "\n".join(sommaire))

    zip_bytes = zip_buf.getvalue()
    filename = "Dossier_{}_{}.zip".format(project_slug, date_str)
    if grp:
        # Formulaires produits APRÈS la convention : compte pour l'état « prêt à déposer ».
        from app.services.groupement_convention import mark_cerfa_generated
        mark_cerfa_generated(db, project.id, [d for d in ("dc1", "dc2", "attri1") if d in cerfa_ok],
                             grp.get("convention_version"))

    headers = {"Content-Disposition": content_disposition(filename)}
    if avertissements:
        from app.core.http import AVERTISSEMENT_HEADER, en_tete_avertissements
        headers[AVERTISSEMENT_HEADER] = en_tete_avertissements(avertissements)
    return Response(content=zip_bytes, media_type="application/zip", headers=headers)
