"""
AGENT 3 — RÉDACTEUR
Tâche : produire le dossier de réponse. Mémoire technique (IA) + formulaires CERFA
pré-remplis (DC1 en groupement, DC2 par membre, ATTRI1) + dossier ZIP téléchargeable.

Prend en compte le groupement recommandé par l'Agent 2 : les co-traitants retenus
sont injectés dans le DC1 (section groupement) et un DC2 est généré par membre.
"""
import io
import re
import base64
import zipfile
from typing import Optional

from app.services.llm import complete, MODEL_FAST

# Seuil (€ HT) au-delà duquel le DUME est ajouté d'office au dossier. Les procédures
# formalisées le rendent quasi incontournable ; ajustable selon la stratégie commerciale.
DUME_THRESHOLD = 90000

MEMOIRE_SYSTEM = """Tu es un rédacteur expert de mémoires techniques pour les marchés
publics français du BTP. Tu produis un mémoire technique convaincant, concret et
structuré en Markdown, prêt à être inséré dans une réponse à appel d'offres.
Pas de bla-bla : des engagements précis, des moyens chiffrés, une méthodologie crédible."""


def _generate_memoire_fast(analysis: dict, company: dict, cotraitants: list,
                           lang_name: str = None, db=None, user_id: int = None,
                           estimate: dict = None, contributions: list = None) -> str:
    """Mémoire technique en UN seul appel LLM. SOURCÉ sur la base de connaissances de
    l'entreprise quand elle existe (extraits injectés + citations [S1]) → traçabilité ;
    sinon mémoire générique (l'entreprise est invitée à alimenter sa base)."""
    details = analysis.get("details", {}) if analysis else {}
    quals = company.get("qualifications", [])
    if isinstance(quals, list):
        quals = ", ".join(q.get("name", "") if isinstance(q, dict) else str(q) for q in quals)
    cot = "; ".join(f"{c.get('name')} ({c.get('specialites','')})" for c in cotraitants) or "aucun"

    # Équipe interne (moyens humains) : présentée nommément dans le mémoire si renseignée.
    team_block = ""
    team = company.get("team") or []
    if isinstance(team, list):
        members = "\n".join(
            f"- {m.get('nom','')} — {m.get('fonction','')}"
            + (f" ({m.get('qualifications','')})" if m.get('qualifications') else "")
            + (f" ; réf. : {m.get('references','')}" if m.get('references') else "")
            for m in team if isinstance(m, dict) and m.get('nom'))
        if members:
            team_block = ("\n\nÉQUIPE INTERNE DÉDIÉE (présente-la NOMMÉMENT dans « Moyens humains », "
                          f"avec rôles et qualifications) :\n{members}")

    # Chiffrage : si un devis a été établi, la méthodologie et le planning du mémoire
    # DOIVENT refléter le découpage chiffré (cohérence prix / discours).
    chiffrage_block, chiffrage_rule = "", ""
    if estimate and estimate.get("lignes"):
        lines = "\n".join(f"- [{l.get('phase','')}] {l.get('tache','')} — {l.get('jours','')} j"
                          for l in estimate["lignes"])
        chiffrage_block = (f"\n\nDÉCOUPAGE CHIFFRÉ DE LA PRESTATION (charge totale : "
                           f"{estimate.get('jours_total','')} jours) :\n{lines}")
        chiffrage_rule = ("\n\nRÈGLE : structure la section « Méthodologie » et le « Planning » "
                          "autour de CES phases et tâches ; le planning doit refléter la charge en jours.")

    # CONSORTIUM (réseau Adjugo) : fusion des apports des co-traitants invités.
    # Chaque PME a renseigné sa part (lot, références, qualifs, paragraphe, prix) via
    # son lien cloisonné ; l'IA les tisse en UNE réponse commune cohérente.
    consortium_block, consortium_rule = "", ""
    subs = [c for c in (contributions or []) if isinstance(c, dict) and c.get("status") == "submitted"]
    if subs:
        parts = []
        for c in subs:
            refs = "; ".join(
                (r.get("intitule", "") + (f" — {r.get('client','')}" if r.get("client") else "")
                 + (f" ({r.get('annee','')})" if r.get("annee") else ""))
                for r in (c.get("references") or []) if isinstance(r, dict) and r.get("intitule"))
            quals_c = ", ".join(str(q) for q in (c.get("qualifications") or []) if q)
            b = f"- {c.get('company_name') or '(co-traitant)'} — rôle {c.get('role','cotraitant')}, lot : {c.get('lot') or '(non précisé)'}"
            if quals_c:
                b += f"\n  Qualifications : {quals_c}"
            if refs:
                b += f"\n  Références : {refs}"
            if c.get("chiffrage_note"):
                b += f"\n  Approche prix de son lot : {c['chiffrage_note']}"
            if c.get("memoire_paragraph"):
                b += f"\n  Apport rédigé par la PME : {c['memoire_paragraph']}"
            parts.append(b)
        consortium_block = ("\n\nCONTRIBUTIONS DES CO-TRAITANTS DU CONSORTIUM "
                            "(apports réels fournis par chaque PME — à FUSIONNER) :\n" + "\n".join(parts))
        consortium_rule = ("\n\nRÈGLE CONSORTIUM : intègre les qualifications, références et apports de CHAQUE "
                           "co-traitant ci-dessus ; attribue chaque lot à l'entreprise qui le couvre et tisse "
                           "leurs moyens et savoir-faire en un récit d'équipe UNIQUE et cohérent. N'invente rien "
                           "au-delà de ce que chaque co-traitant a fourni.")

    # RAG : récupère le savoir-faire réel de l'entreprise pertinent pour ce marché
    sources_block, src_rule = "", ""
    if db is not None and user_id:
        try:
            from app.services import rag
            q = " ".join(str(details.get(k, "")) for k in ("intitule_marche", "type_marche", "critere_rse")) \
                + " méthodologie sécurité qualité références moyens"
            chunks = rag.retrieve(db, user_id, q, k=6)
            if chunks:
                sources_block = "\n\nSOURCES (savoir-faire RÉEL de l'entreprise — appuie-toi DESSUS) :\n" + rag.sources_block(chunks)
                src_rule = ("\n\nRÈGLE : appuie chaque affirmation factuelle (moyens, références, "
                            "certifications, chiffres) sur ces sources et CITE-les avec [S1], [S2]… "
                            "N'invente aucun chiffre ni référence absent des sources.")
        except Exception:
            pass

    prompt = f"""Rédige un mémoire technique pour cet appel d'offres.

MARCHÉ : {details.get('intitule_marche','')}
ACHETEUR : {details.get('acheteur','')}
ALLOTISSEMENT : {details.get('allotissement','')}
DÉLAI : {details.get('delai_execution','')}
EXIGENCES RSE : {details.get('critere_rse','')}
CRITÈRES D'ATTRIBUTION : {details.get('criteres_attribution','')}

ENTREPRISE MANDATAIRE : {company.get('name','')} — {company.get('forme_juridique','')},
{company.get('city','')}, effectif {company.get('effectif','')}, qualifications : {quals}.
CO-TRAITANTS DU GROUPEMENT : {cot}.{team_block}{consortium_block}{sources_block}{chiffrage_block}

Structure en Markdown avec ces sections :
1. Présentation du groupement et répartition des lots
2. Méthodologie et organisation du chantier
3. Moyens humains et matériels
4. Démarche qualité, sécurité et RSE (clause d'insertion)
5. Planning et engagements de délai
Sois concret, mentionne explicitement la co-traitance par lot. ~600 mots.{src_rule}{chiffrage_rule}{consortium_rule}"""
    if lang_name and lang_name.lower() != "français":
        prompt += (f"\n\nLANGUE : rédige l'intégralité du mémoire en {lang_name} "
                   f"(titres de sections compris).")
    return complete(MEMOIRE_SYSTEM, prompt, max_tokens=2000, temperature=0.3, model=MODEL_FAST)


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

    # Contributions cloisonnées des co-traitants (réseau Adjugo) à fusionner dans le mémoire.
    contributions = []
    if db is not None and project_id:
        try:
            from app.models import ProjectContribution
            rows = db.query(ProjectContribution).filter(
                ProjectContribution.project_id == project_id,
                ProjectContribution.status == "submitted").all()
            contributions = [{
                "company_name": c.company_name, "role": c.role, "lot": c.lot,
                "references": c.references or [], "qualifications": c.qualifications or [],
                "chiffrage_note": c.chiffrage_note or "", "memoire_paragraph": c.memoire_paragraph or "",
                "status": c.status,
            } for c in rows]
        except Exception:
            contributions = []

    # Pièces administratives des co-traitants (parts SOUMISES) → assemblées dans le ZIP.
    cotraitant_pieces = []
    if db is not None and project_id:
        try:
            from app.models import ContributionPiece, ProjectContribution
            prows = db.query(ContributionPiece, ProjectContribution).join(
                ProjectContribution, ContributionPiece.contribution_id == ProjectContribution.id).filter(
                ContributionPiece.project_id == project_id,
                ProjectContribution.status == "submitted").all()
            cotraitant_pieces = [{"company": (cb.company_name or "cotraitant"),
                                  "name": pc.name, "file_key": pc.file_key} for pc, cb in prows]
        except Exception:
            cotraitant_pieces = []

    # ── Mémoire technique (IA, un seul appel) ──
    try:
        memoire_md = _generate_memoire_fast(analysis, company, cotraitants, lang_name, db=db, user_id=user_id, estimate=estimate, contributions=contributions)
    except Exception as e:
        memoire_md = f"# Mémoire technique\n\n(génération indisponible : {e})"
        warnings.append(f"mémoire: {e}")

    # ── CERFA ──
    project_data = {
        "name": details.get("intitule_marche", "Marché public"),
        "client": details.get("acheteur", ""),
        "budget": _parse_amount(details.get("budget_estime", "")),  # numérique pour l'ATTRI1
        "reference": f"AO-{(project_id or 0):04d}",
        "cotraitants": cotraitants,   # ← injecté pour le DC1 groupement / DC2 multi-membres
    }

    # Composition du dossier selon le PAYS :
    #  - France : CERFA DC1/DC2/(DC4)/ATTRI1 + DUME sur gros marchés.
    #  - Autres pays UE adaptés : les CERFA français ne s'appliquent pas → le document
    #    de candidature est l'ESPD (= DUME), toujours inclus, dans la langue locale.
    roles = [str(c.get("role") or "") for c in cotraitants]
    has_subcontractor = any(r == "sous_traitant" for r in roles) or (cotraitants and not any(roles))
    if (country or "FR").upper() == "FR":
        include_dume = (project_data.get("budget") or 0) >= DUME_THRESHOLD
        cerfa_ids = ["dc1", "dc2"] + (["dc4"] if has_subcontractor else []) + ["attri1"] \
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
        warnings.append(f"cerfa indisponible: {e}")

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

    # ── ZIP ──
    zip_bytes, zip_name = _build_zip(memoire_md, cerfa_files, company, details, cotraitants, project_id, cotraitant_pieces)

    return {
        "memoire_markdown": memoire_md,
        "memoire_preview": _preview(memoire_md, 400),
        "cerfas": [{"id": c["id"], "name": c["name"],
                    "content_b64": base64.b64encode(_as_bytes(c["content"])).decode()}
                   for c in cerfa_files],
        "zip_name": zip_name,
        "zip_b64": base64.b64encode(zip_bytes).decode(),
        "warnings": warnings,
    }


def _build_zip(memoire_md, cerfa_files, company, details, cotraitants, project_id, cotraitant_pieces=None):
    import os
    buf = io.BytesIO()
    ao = re.sub(r"[^\w\s-]", "", details.get("intitule_marche", "AO"))[:40].strip() or f"projet_{project_id}"
    zip_name = f"Adjugo_Dossier_{ao}.zip".replace(" ", "_")

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("memoire_technique.md", memoire_md.encode("utf-8"))
        for c in cerfa_files:
            zf.writestr(f"cerfa/{c['name']}", _as_bytes(c["content"]))
        zf.writestr("00_groupement.txt", _groupement_recap(company, cotraitants, details).encode("utf-8"))
        zf.writestr("fiche_ao.txt", _ao_recap(details).encode("utf-8"))

        # Pièces administratives des co-traitants (assemblage automatique du groupement).
        if cotraitant_pieces:
            from app.services.storage import get_storage
            storage = get_storage()
            seen = set()
            for p in cotraitant_pieces:
                try:
                    content = storage.load(p["file_key"])
                except Exception:
                    continue
                co = re.sub(r"[^\w\s-]", "", p.get("company", "") or "cotraitant")[:40].strip() or "cotraitant"
                nm = os.path.basename(p.get("name", "") or "piece") or "piece"
                path = f"pieces_cotraitants/{co}/{nm}"
                i = 2
                while path in seen:        # évite l'écrasement si deux pièces de même nom
                    stem, dot, ext = nm.rpartition(".")
                    nm2 = (f"{stem}_{i}{dot}{ext}" if dot else f"{nm}_{i}")
                    path = f"pieces_cotraitants/{co}/{nm2}"
                    i += 1
                seen.add(path)
                zf.writestr(path, content)
    return buf.getvalue(), zip_name


def _groupement_recap(company, cotraitants, details):
    lines = ["COMPOSITION DU GROUPEMENT — ADJUGO", "=" * 45, ""]
    lines.append(f"Marché : {details.get('intitule_marche','')}")
    lines.append(f"Mandataire : {company.get('name','')} ({company.get('siret','')})")
    lines.append("")
    if cotraitants:
        lines.append("Co-traitants :")
        for c in cotraitants:
            lines.append(f"  - {c.get('name','')} | {c.get('specialites','')} | SIRET {c.get('siret','')}")
    else:
        lines.append("Candidature en entreprise seule.")
    return "\n".join(lines)


def _ao_recap(details):
    lines = ["FICHE RÉCAPITULATIVE AO", "=" * 45, ""]
    for k, v in (details or {}).items():
        if isinstance(v, (str, int, float)) and str(v).strip():
            lines.append(f"{k.replace('_',' ').title()} : {v}")
    return "\n".join(lines)


def _parse_amount(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if not v:
        return 0.0
    nums = re.findall(r"[\d\s]+", str(v).replace(",", "."))
    for n in nums:
        n = n.replace(" ", "")
        if n:
            try:
                return float(n)
            except ValueError:
                continue
    return 0.0


def _as_bytes(content) -> bytes:
    return content if isinstance(content, bytes) else str(content).encode("utf-8")


def _preview(md: str, n: int = 400) -> str:
    clean = re.sub(r"#{1,6}\s+", "", md or "")
    clean = re.sub(r"\*\*(.+?)\*\*", r"\1", clean).strip()
    return clean[:n] + ("…" if len(clean) > n else "")
