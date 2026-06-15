"""
AGENT WAR ROOM — pré-répartition autonome d'un marché en groupement.

Avant même que les entreprises ne se parlent, l'IA « simule » le partenariat :
elle lit le DCE, identifie les lots, et propose une RÉPARTITION (qui prend quel lot,
montant estimé, pourquoi) en fonction du savoir-faire réel de chaque membre (sa base
de connaissances). Le partenaire invité reçoit ainsi un dossier clé en main plutôt
qu'un simple « voulez-vous répondre avec nous ? ».

Anti-hallucination : les lots et montants viennent du DCE (montant = null si non cité,
labellisé « estimation »). L'affectation s'appuie sur les savoir-faire réellement présents.
"""
import logging

from app.services.llm import complete_json
from app.services import rag

logger = logging.getLogger("adjugo")

_SYS = """Tu es un responsable d'offres expérimenté en marchés publics. À partir d'un DCE
et du savoir-faire de plusieurs entreprises d'un groupement, tu proposes une RÉPARTITION
des lots/prestations : qui prend quoi, montant estimé, et pourquoi (en t'appuyant sur le
savoir-faire réel de chacun). Tu n'inventes ni lot, ni montant : si un montant n'est pas
dans le DCE, mets null. Réponds en JSON strict."""


def _member_profile(db, user_id: int, name: str) -> str:
    """Résumé court du savoir-faire d'un membre à partir de sa base de connaissances."""
    chunks = rag.retrieve(db, user_id, "savoir-faire méthodologie compétences références", k=4)
    if not chunks:
        return f"{name} : base de connaissances vide (savoir-faire à préciser)."
    extrait = " ".join(c["text"][:200] for c in chunks)[:700]
    return f"{name} : {extrait}"


def propose_allocation(db, dce_text: str, members: list) -> dict:
    """members = [{user_id, name, role}]. Renvoie la pré-répartition du marché."""
    profils = "\n".join("- " + _member_profile(db, m["user_id"], m.get("name") or "Entreprise")
                        for m in members if m.get("user_id"))
    names = [m.get("name") or "Entreprise" for m in members]
    user = f"""GROUPEMENT (savoir-faire de chaque entreprise) :
{profils}

DCE (extrait) :
{(dce_text or '')[:16000]}

Renvoie EXACTEMENT ce JSON :
{{
  "marche_objet": "objet du marché en une phrase",
  "montant_total_estime": <nombre € si déductible du DCE, sinon null>,
  "lots": [
    {{"intitule": "lot / prestation", "montant_estime": <€ si cité, sinon null>,
      "attribue_a": "nom de l'entreprise du groupement la plus pertinente",
      "raison": "pourquoi cette entreprise (savoir-faire correspondant)"}}
  ],
  "synthese": "2-3 phrases : logique de la répartition et complémentarité du groupement",
  "accroche_partenaire": "message d'accroche pour le partenaire invité (1-2 phrases concrètes)"
}}
Entreprises autorisées pour « attribue_a » : {", ".join(names)}. N'invente aucun lot ni montant."""
    try:
        data = complete_json(_SYS, user, max_tokens=2200, temperature=0.2)
    except Exception as e:
        logger.warning("warroom.propose en échec : %s", e)
        return {"marche_objet": "", "lots": [], "montant_total_estime": None,
                "synthese": "", "accroche_partenaire": "", "error": "Génération indisponible."}
    if not isinstance(data, dict):
        return {"marche_objet": "", "lots": [], "synthese": "", "accroche_partenaire": ""}
    data["lots"] = [l for l in (data.get("lots") or []) if isinstance(l, dict) and l.get("intitule")]
    return data
