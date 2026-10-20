"""Courriels d'invitation à un groupement, en HTML avec leur version texte (réorganisation de l'interface,
vague 2b, chantier B4 ; contrat : docs/REORGANISATION_V2B.md, § B4).

Trois envois, une seule composition :
  - l'invitation d'un partenaire connu (adresse saisie par le chef de file, `invites._send_invite_email`) ;
  - l'invitation d'un membre du réseau Adjugo (adresse remplie par le serveur, jamais montrée au chef de file,
    `reseau._network_mailer`) ;
  - leurs relances : le renvoi demandé par le chef de file (« Relancer », même lien) et le rappel planifié
    à J-3 puis J-1 de la date limite quand la part n'est pas soumise (`alerts.run_cotraitance_reminders`).

Chaque courriel nomme le chef de file (son entreprise), le marché, la date limite, ce qui est attendu du
partenaire et ce qu'il verra (sa part, jamais le détail des prix des autres), et mène à « Votre part dans
[marché] » par le lien de l'invitation (`/invite/<jeton>`, inchangé : les liens déjà envoyés marchent toujours).

Règles tenues ici, vérifiées par tests/test_reorganisation_v2b_courriel_invitation.py :
  - toute donnée saisie (entreprise, marché, partie) est aplatie (retours à la ligne, caractères de contrôle et
    de sens d'écriture retirés) puis ÉCHAPPÉE dans le HTML ; l'objet ne porte jamais de retour à la ligne ;
  - aucune image, aucun pixel, aucun lien autre que celui de l'invitation ;
  - aucune adresse email dans le courriel (ni celle du destinataire, ni celle du chef de file) ;
  - aucun fait inventé : une date limite inconnue est dite inconnue, un chef de file sans nom d'entreprise est
    « une entreprise » / « le chef de file » ;
  - vocabulaire du glossaire : « partenaire », « partie », jamais les mots bannis (tests/textes_visibles.py).
"""
import html
import unicodedata
from datetime import date, datetime
from typing import Iterable, Optional

from app.services.email_templates import _ACCENT, _BG, _BORDER, _INK, _MUTED, _button, _shell

_POLICE = "'Segoe UI',Helvetica,Arial,sans-serif"
SIGNATURE = "— Adjugo, le réseau des PME"
ROLES = {"cotraitant": "Partenaire du groupement", "sous_traitant": "Sous-traitant"}
# Chemin de l'écran où un membre du réseau retire la publication de son profil (rubrique Partenaires).
CHEMIN_PROFIL_RESEAU = "Partenaires › Réseau Adjugo › Mon profil partenaire"
# Caractères de sens d'écriture (U+202A–U+202E, U+2066–U+2069) : ils retournent un nom à l'affichage.
_SENS = {chr(c) for c in list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A))}


def net(valeur, limite: Optional[int] = None) -> str:
    """Texte saisi, sur une ligne : caractères de contrôle et de sens d'écriture retirés, blancs réunis."""
    s = "".join(" " if unicodedata.category(ch) in ("Cc", "Zl", "Zp") else ch
                for ch in str(valeur or "") if ch not in _SENS and unicodedata.category(ch) != "Cf")
    s = " ".join(s.split())
    return s[:limite].rstrip() if limite else s


def _e(valeur) -> str:
    return html.escape(valeur or "", quote=True)


def jour(d) -> str:
    """JJ/MM/AAAA, ou "" quand la date est inconnue."""
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, date):
        return d.strftime("%d/%m/%Y")
    return ""


def _p(texte_html: str, *, taille: str = "15px", couleur: str = _INK, marge: str = "0 0 14px",
       centre: bool = False) -> str:
    align = "text-align:center;" if centre else ""
    return (f'<p style="margin:{marge};font-family:{_POLICE};font-size:{taille};line-height:1.6;color:{couleur};'
            f'{align}">{texte_html}</p>')


def _titre(texte_html: str) -> str:
    return (f'<h2 style="margin:18px 0 6px;font-family:{_POLICE};font-size:15px;font-weight:700;color:{_INK};">'
            f'{texte_html}</h2>')


def _faits(lignes: list) -> str:
    """L'essentiel, une ligne par fait (libellé au-dessus de sa valeur : lisible sur un téléphone de 375 px)."""
    cellules = "".join(
        f'<tr><td style="padding:7px 14px;border-top:{"0" if i == 0 else "1px solid " + _BORDER};">'
        f'<div style="font-family:{_POLICE};font-size:12px;line-height:1.4;color:{_MUTED};">{_e(lib)}</div>'
        f'<div style="font-family:{_POLICE};font-size:14.5px;line-height:1.45;color:{_INK};font-weight:600;'
        f'word-break:break-word;">{_e(val)}</div></td></tr>'
        for i, (lib, val) in enumerate(lignes))
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:4px 0 6px;background:{_BG};border:1px solid {_BORDER};border-radius:12px;">'
            f'{cellules}</table>')


def _liste(points: Iterable[str]) -> str:
    items = "".join(f'<li style="margin:0 0 4px;">{_e(x)}</li>' for x in points)
    return (f'<ul style="margin:0 0 14px;padding-left:20px;font-family:{_POLICE};font-size:14.5px;line-height:1.55;'
            f'color:{_INK};">{items}</ul>')


def _lien_secours(url: str, avant: str) -> str:
    return (_p(_e(avant) + ("&nbsp;" if avant else "") + "S'il ne fonctionne pas, copiez-collez cette adresse&nbsp;:",
               taille="12.5px", couleur=_MUTED, marge="16px 0 4px", centre=True)
            + f'<p style="margin:0 0 6px;font-family:{_POLICE};font-size:11.5px;line-height:1.5;color:{_ACCENT};'
              f'text-align:center;word-break:break-all;">{_e(url)}</p>')


def _carte(corps: str, preheader: str, pourquoi: str) -> str:
    """La carte des courriels d'Adjugo (`_shell`) ; son pied dit pourquoi on reçoit ce courriel (`pourquoi`, en clair)."""
    pied = ("Adjugo — la plateforme qui simplifie la réponse aux marchés publics.<br>\n          " + _e(pourquoi))
    return _shell(f'      <tr><td style="padding:6px 36px 4px;">\n{corps}\n      </td></tr>', preheader=preheader,
                  pied=pied)


def _bloc_part(marche: str, url: str, bouton: str) -> tuple:
    """« Votre part dans [marché] » : (texte, html). Le lien est celui de l'invitation, jamais un autre."""
    titre = f"Votre part dans « {marche} »"
    return f"{titre} :\n{url}", _titre(_e(titre)) + _button(_e(bouton), _e(url))


def invitation(*, chef: str, marche: str, url: str, date_limite=None, role: str = "cotraitant",
               peut_contribuer: bool = True, voit_pieces: bool = True, partie: str = "", entreprise: str = "",
               reseau: bool = False, relance: bool = False, expire_le=None) -> dict:
    """Invitation (ou son renvoi, `relance`) d'un partenaire connu ou d'un membre du réseau (`reseau`).
    Renvoie {"objet", "texte", "html"}."""
    chef_nom = net(chef, 160)
    m = net(marche, 300) or "sans titre"
    partie = net(partie, 160)
    entreprise = net(entreprise, 160)
    sous_traitant = (role or "") == "sous_traitant"
    qui = chef_nom or "Une entreprise"                 # sujet d'une phrase
    chez = chef_nom or "le chef de file"               # dans une phrase
    a_chef = f"à {chef_nom}" if chef_nom else "au chef de file"     # jamais « à le chef de file »
    if sous_traitant:
        projet = f"intervenir comme sous-traitant sur le marché « {m} »"
    else:
        projet = f"rejoindre son groupement pour répondre ensemble au marché « {m} »"
    if reseau and relance:
        intro = f"{qui}, qui a trouvé votre profil sur le réseau Adjugo, vous renvoie sa proposition : {projet}."
    elif reseau:
        intro = f"{qui} a trouvé votre profil sur le réseau Adjugo et vous propose de {projet}."
    elif relance:
        intro = f"{qui} vous renvoie son invitation à {projet}."
    else:
        intro = f"{qui} vous invite à {projet}."

    echeance = jour(date_limite)
    faits = []
    if chef_nom:
        faits.append(("Chef de file", chef_nom))
    faits.append(("Marché", m))
    faits.append(("Date limite", echeance or "pas encore indiquée sur ce marché"))
    faits.append(("Votre rôle", ROLES["sous_traitant" if sous_traitant else "cotraitant"]))
    if partie:
        faits.append(("Partie proposée", partie))
    if entreprise:
        faits.append(("Entreprise invitée", entreprise))

    # Ce qui est attendu : ce que la page du partenaire permet de faire, rien de plus.
    if peut_contribuer:
        attendu = [("Renseigner votre part : la partie du marché que vous prenez et son prix, l'identité de votre "
                    "entreprise pour les formulaires officiels, vos références et vos attestations."),
                   f"La soumettre {a_chef}, avant la date limite."]
        if reseau:
            attendu.insert(0, "Accepter ou décliner l'invitation, depuis le lien ci-dessous.")
        else:
            attendu.append("Si vous ne souhaitez pas y aller, déclinez l'invitation depuis la même page.")
        if sous_traitant:
            attendu.append("Comme sous-traitant, vous ne signez pas la convention de groupement.")
    else:
        attendu = [f"Prendre connaissance du dossier que {chez} partage avec vous. Ce lien est en lecture seule : "
                   "aucune part à renseigner."]
    # Ce qu'il verra : ce que la page lui montre (l'aperçu du réseau tant qu'il n'a pas accepté).
    pieces = f", les pièces que {chez} partage avec vous" if voit_pieces else ""
    if reseau:
        verra = ["Avant votre réponse : un aperçu du marché.",
                 f"Une fois l'invitation acceptée : le résumé du marché{pieces}"
                 + (" et votre part." if peut_contribuer else ".")]
    elif peut_contribuer:
        verra = [f"Le résumé du marché{pieces} et votre part."]
    else:
        verra = [f"Le résumé du marché{pieces}."]
    verra.append("Jamais le détail des prix des autres entreprises.")
    if peut_contribuer:
        verra.append(f"Le détail de vos prix reste chez vous : {chez} reçoit le prix de votre partie, pas son détail.")

    validite = ("Ce lien est réservé à votre entreprise"
                + (f" et valable jusqu'au {jour(expire_le)}." if jour(expire_le) else "."))
    if peut_contribuer:
        part_texte, part_html = _bloc_part(m, url, "Ouvrir votre part")
    else:
        part_texte = f"Le dossier partagé :\n{url}"
        part_html = _titre("Le dossier partagé") + _button("Ouvrir le dossier partagé", _e(url))

    if reseau:
        notes = ["Votre adresse n'est pas communiquée au chef de file tant que vous n'avez pas accepté.",
                 ("Vous recevez ce message parce que le profil partenaire de votre entreprise est publié sur "
                  f"Adjugo. Vous pouvez retirer cette publication à tout moment depuis {CHEMIN_PROFIL_RESEAU}.")]
    else:
        notes = [(f"Vous recevez ce message parce que {chez} a indiqué votre adresse pour vous inviter sur "
                  "Adjugo. Si vous ne connaissez pas cette entreprise, ignorez simplement ce message.")]

    base = "Une entreprise vous propose un groupement" if reseau else "Invitation à répondre ensemble à un marché"
    objet = net(("Rappel : " + base[:1].lower() + base[1:]) if relance else base) + f" — {net(marche, 60) or m}"

    texte = "\n".join([
        "Bonjour,", "", intro, "",
        *[f"{lib} : {val}" for lib, val in faits], "",
        "Ce qui est attendu de vous :", *[f"- {x}" for x in attendu], "",
        "Ce que vous verrez :", *[f"- {x}" for x in verra], "",
        part_texte, validite, "",
        *[x for n in notes for x in (n, "")],
        SIGNATURE,
    ])
    corps = "\n".join([
        f'<h1 style="margin:14px 0 10px;font-family:{_POLICE};font-size:20px;font-weight:800;color:{_INK};">'
        "Bonjour,</h1>",
        _p(_e(intro)),
        _faits(faits),
        _titre("Ce qui est attendu de vous"), _liste(attendu),
        _titre("Ce que vous verrez"), _liste(verra),
        part_html,
        _lien_secours(url, validite),
        *[_p(_e(n), taille="12.5px", couleur=_MUTED, marge="12px 0 0") for n in (notes[:1] if reseau else [])],
    ])
    return {"objet": objet, "texte": texte,
            "html": _carte(corps, preheader=_e(intro), pourquoi=notes[-1])}


def rappel_part(*, chef: str, marche: str, url: str, date_limite, jours_restants: int,
                attestations: Iterable[str] = (), parties: Iterable[str] = ()) -> dict:
    """Rappel planifié (J-3, puis J-1) au partenaire dont la part n'est pas soumise. `attestations` et `parties` :
    les lignes déjà composées par la relance (« Kbis à fournir », « « Démarche … » (date limite interne : …) »),
    sans leur tiret. Renvoie {"objet", "texte", "html"} ; l'objet est celui d'avant (« Rappel — il vous reste … »)."""
    chef_nom = net(chef, 160)
    du_chef = f"de {chef_nom}" if chef_nom else "du chef de file"
    chez = chef_nom or "le chef de file"
    m = net(marche, 300) or "sans titre"
    reste = "il vous reste 1 jour" if jours_restants <= 1 else f"il vous reste {int(jours_restants)} jours"
    reste_maj = reste[:1].upper() + reste[1:]
    echeance = jour(date_limite)
    attestations = [net(x, 300) for x in attestations if net(x)]
    parties = [net(x, 300) for x in parties if net(x)]
    phrase = (f"{reste_maj} pour ajouter votre part au groupement {du_chef} sur le marché « {m} »"
              + (f" (date limite : {echeance})." if echeance else "."))
    a_chef = f"à {chef_nom}" if chef_nom else "au chef de file"     # jamais « à le chef de file »
    suite = (f"Complétez votre part et soumettez-la {a_chef}. Sans elle, votre entreprise ne figurera pas dans la "
             "réponse commune.")
    verra = ("Depuis votre lien, vous voyez le résumé du marché et votre part, jamais le détail des prix des autres "
             "entreprises. "
             f"Le détail de vos prix reste chez vous : {chez} reçoit le prix de votre partie, pas son détail.")
    texte = ["Bonjour,", "", phrase, "", suite, "", verra]
    corps = [f'<h1 style="margin:14px 0 10px;font-family:{_POLICE};font-size:20px;font-weight:800;color:{_INK};">'
             'Bonjour,</h1>', _p(_e(phrase)), _p(_e(suite)), _p(_e(verra), taille="14px", couleur=_MUTED)]
    if attestations:
        texte += ["", "Vos attestations sont aussi à mettre à jour avant le dépôt :", *[f"- {x}" for x in attestations]]
        corps += [_titre("Vos attestations sont aussi à mettre à jour avant le dépôt"), _liste(attestations)]
    if parties:
        texte += ["", "Votre partie du dossier de présentation est aussi attendue :", *[f"- {x}" for x in parties]]
        corps += [_titre("Votre partie du dossier de présentation est aussi attendue"), _liste(parties)]
    if url:
        part_texte, part_html = _bloc_part(m, url, "Ouvrir votre part")
        texte += ["", part_texte]
        corps += [part_html, _lien_secours(url, "")]
    texte += ["", SIGNATURE]
    pourquoi = f"Vous recevez ce rappel parce que {chez} a invité votre entreprise dans son groupement sur Adjugo."
    objet = f"Rappel — {reste} pour votre part ({net(marche, 50) or m})"
    return {"objet": objet, "texte": "\n".join(texte),
            "html": _carte("\n".join(corps), preheader=_e(phrase), pourquoi=pourquoi)}
