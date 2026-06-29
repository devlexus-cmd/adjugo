"""
Optimiseur de groupement : décompose l'allotissement d'un marché en lots, infère le
métier (NAF) de chaque lot, et recommande une composition — lots couverts en propre
(mandataire) vs lots à confier à un co-traitant. Déterministe et explicable ; les
co-traitants proposés viennent du scoring fondé (SIRENE + BODACC), jamais inventés.
"""
import re
from typing import Optional

# Mots-clés → métier (clé TRADES de sirene.py). Inférence transparente.
_TRADE_KEYWORDS = {
    "electricite": ["électric", "electric", "courant fort", "courant faible", "cfo", "cfa", "éclairage", "eclairage"],
    "plomberie": ["plomberie", "cvc", "chauffage", "ventilation", "sanitaire", "climatisation", "génie climatique", "genie climatique"],
    "maconnerie": ["maçonnerie", "maconnerie", "gros œuvre", "gros oeuvre", "béton", "beton", "fondation", "structure"],
    "menuiserie": ["menuiserie", "bois", "fenêtre", "fenetre", "porte", "agencement", "mobilier"],
    "couverture": ["couverture", "toiture", "charpente", "zinguerie", "bardage"],
    "peinture": ["peinture", "finition", "revêtement mural", "revetement mural", "papier peint"],
    "platrerie": ["plâtrerie", "platrerie", "cloison", "isolation", "doublage", "faux plafond", "plaque de plâtre"],
    "carrelage": ["carrelage", "revêtement de sol", "revetement de sol", "faïence", "faience", "sol souple"],
    "terrassement": ["terrassement", "vrd", "voirie", "réseaux", "reseaux", "assainissement"],
    "metallerie": ["serrurerie", "métallerie", "metallerie", "métallique", "metallique", "ferronnerie", "garde-corps"],
    "etancheite": ["étanchéité", "etancheite"],
    "demolition": ["démolition", "demolition", "déconstruction", "deconstruction", "désamiantage", "desamiantage", "curage"],
    # Fournitures & services
    "nettoyage": ["nettoyage", "propreté", "proprete", "entretien des locaux", "ménage", "menage", "bionettoyage", "vitrerie"],
    "espaces_verts": ["espaces verts", "paysag", "tonte", "élagage", "elagage", "jardin", "végéta", "vegeta", "fleuriss"],
    "restauration": ["restauration", "cantine", "repas", "traiteur", "alimentaire", "denrées", "denrees"],
    "informatique": ["informatique", "logiciel", "progiciel", "matériel informatique", "materiel informatique", "infogérance", "infogerance", "numérique", "numerique", "téléphonie", "telephonie"],
    "securite": ["gardiennage", "surveillance humaine", "sécurité privée", "securite privee", "agent de sécurité", "agent de securite"],
    "imprimerie": ["imprimerie", "impression", "reprographie"],
    "formation": ["formation professionnelle", "stage de formation", "organisme de formation"],
}


def infer_trade(label: str) -> Optional[str]:
    """Renvoie la clé métier (TRADES) la plus probable pour un libellé de lot, ou None."""
    t = (label or "").lower()
    best, best_hits = None, 0
    for key, kws in _TRADE_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in t)
        if hits > best_hits:
            best, best_hits = key, hits
    return best


def parse_lots(allotissement: str) -> list[dict]:
    """Décompose un texte d'allotissement en lots [{num, label}].
    Gère « Lot 1 : Gros œuvre, Lot 2 : Électricité… », les retours à la ligne, le lot unique."""
    txt = (allotissement or "").strip()
    if not txt or "lot unique" in txt.lower() or "non alloti" in txt.lower():
        return []

    lots = []
    # Capture « Lot N : libellé » jusqu'au prochain « Lot » ou fin
    for m in re.finditer(r"lot\s*n?°?\s*(\d+)\s*[:\-–]?\s*([^\n;]*?)(?=(?:lot\s*n?°?\s*\d)|[\n;]|$)",
                         txt, flags=re.IGNORECASE):
        num = m.group(1)
        label = m.group(2).strip(" .,-–")
        if label:
            lots.append({"num": num, "label": label[:80]})
    if lots:
        return lots

    # Repli : découpe sur séparateurs si pas de numérotation explicite
    parts = [p.strip() for p in re.split(r"[,;\n]", txt) if len(p.strip()) > 2]
    return [{"num": str(i + 1), "label": p[:80]} for i, p in enumerate(parts[:12])]


def own_trades(company: dict) -> set:
    """Métiers couverts en propre par l'entreprise (depuis spécialités/qualifs/APE)."""
    blob = " ".join(str(company.get(k) or "") for k in
                    ("specialites", "qualifications", "code_ape", "naf_label", "name")).lower()
    return {key for key, kws in _TRADE_KEYWORDS.items() if any(kw in blob for kw in kws)}
