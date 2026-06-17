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
from app.core.org import data_owner_id
from app.models import User, Project, Company, Document
from app.services.cerfa import GENERATORS

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
        Project.id == project_id, Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(404, "Projet introuvable")

    company = db.query(Company).filter(Company.user_id == data_owner_id(current_user, db)).first()
    if not company:
        raise HTTPException(400, "Completez votre profil entreprise")

    # Preparer les donnees entreprise
    cd = {}
    for k in ["name", "siret", "code_ape", "forme_juridique", "capital",
              "representant_legal", "address", "city", "postal_code",
              "tva_intracom", "ca_n1", "ca_n2", "ca_n3", "effectif",
              "email", "phone"]:
        cd[k] = getattr(company, k, "") or ""
    cd["qualifications"] = company.qualifications or []

    pd = {
        "name": project.name,
        "client": project.client or "",
        "budget": project.budget or 0,
        "reference": "AO-{:04d}".format(project.id),
        "cotraitants": [],
    }

    # Charger les co-traitants si disponibles
    try:
        from app.routers.cotraitants import Cotraitant
        cts = db.query(Cotraitant).filter(Cotraitant.user_id == current_user.id).all()
        for ct in cts:
            ct_data = {}
            for k in ["name", "siret", "code_ape", "forme_juridique",
                       "representant_legal", "address", "city", "postal_code",
                       "email", "phone", "tva_intracom", "ca_n1", "ca_n2",
                       "ca_n3", "effectif"]:
                ct_data[k] = getattr(ct, k, "") or ""
            pd["cotraitants"].append(ct_data)
    except Exception:
        pass

    # Creer le ZIP
    zip_buf = io.BytesIO()
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    project_slug = project.name.replace(" ", "_")[:30]

    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Generer les 4 CERFA
        for doc_type, generator in GENERATORS.items():
            try:
                pdf_bytes = generator(cd, pd)
                filename = "01_CERFA/{}_{}_{}.pdf".format(
                    doc_type.upper(), project_slug, date_str
                )
                zf.writestr(filename, pdf_bytes)
            except Exception as e:
                # Ajouter un fichier d'erreur
                zf.writestr(
                    "01_CERFA/{}_ERREUR.txt".format(doc_type.upper()),
                    "Erreur generation {}: {}".format(doc_type.upper(), str(e))
                )

        # 2. Ajouter les documents du coffre-fort
        documents = db.query(Document).filter(
            Document.user_id == current_user.id
        ).all()

        for doc in documents:
            # Verifier si le fichier existe physiquement
            if doc.file_path and os.path.exists(doc.file_path):
                category = doc.category or "autre"
                ext = os.path.splitext(doc.file_path)[1] or ".pdf"
                safe_name = doc.name.replace("/", "_").replace(" ", "_")
                filename = "02_Documents/{}/{}{}".format(
                    category.capitalize(), safe_name, ext
                )
                with open(doc.file_path, "rb") as f:
                    zf.writestr(filename, f.read())
            else:
                # Document en base mais fichier manquant
                zf.writestr(
                    "02_Documents/{}.txt".format(doc.name.replace(" ", "_")),
                    "Document reference: {}\nCategorie: {}\nFichier non disponible sur le serveur.".format(
                        doc.name, doc.category or "autre"
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
        sommaire.append("Budget : " + "{:,.0f} EUR".format(project.budget or 0).replace(",", " "))
        sommaire.append("Reference : AO-{:04d}".format(project.id))
        sommaire.append("Date : " + date_str)
        sommaire.append("")
        sommaire.append("-" * 60)
        sommaire.append("ENTREPRISE CANDIDATE")
        sommaire.append("-" * 60)
        sommaire.append("Denomination : " + cd.get("name", ""))
        sommaire.append("SIRET : " + cd.get("siret", ""))
        sommaire.append("Adresse : " + cd.get("address", "") + " " + cd.get("city", ""))
        sommaire.append("Representant : " + cd.get("representant_legal", ""))
        sommaire.append("CA N-1 : " + "{:,.0f} EUR".format(cd.get("ca_n1", 0) or 0).replace(",", " "))
        sommaire.append("")

        if pd["cotraitants"]:
            sommaire.append("-" * 60)
            sommaire.append("CO-TRAITANTS ({})".format(len(pd["cotraitants"])))
            sommaire.append("-" * 60)
            for i, ct in enumerate(pd["cotraitants"]):
                sommaire.append("{}. {} - SIRET: {}".format(i + 1, ct.get("name", ""), ct.get("siret", "")))
            sommaire.append("")

        sommaire.append("-" * 60)
        sommaire.append("CONTENU DU DOSSIER")
        sommaire.append("-" * 60)
        sommaire.append("")
        sommaire.append("01_CERFA/")
        for dt in ["DC1", "DC2", "DC4", "ATTRI1"]:
            sommaire.append("  - {}_{}_{}.pdf".format(dt, project_slug, date_str))
        sommaire.append("")
        sommaire.append("02_Documents/")
        for doc in documents:
            sommaire.append("  - {} ({})".format(doc.name, doc.category or "autre"))

        sommaire.append("")
        sommaire.append("=" * 60)
        sommaire.append("Genere par adjugo. le " + date_str)

        zf.writestr("00_SOMMAIRE.txt", "\n".join(sommaire))

    zip_bytes = zip_buf.getvalue()
    filename = "Dossier_{}_{}.zip".format(project_slug, date_str)

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="' + filename + '"'},
    )
