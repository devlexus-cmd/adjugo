"""Gabarits d'emails HTML soignés (compatibles clients mail : layout en tableaux + styles
INLINE, le <style> étant souvent retiré par Gmail/Outlook). Charte Adjugo : accent #1B4FFF,
wordmark « adjug◎ » (le ◎ rappelle le logo en cercles concentriques)."""

_ACCENT = "#1B4FFF"
_INK = "#16181d"
_MUTED = "#6b7280"
_BG = "#f4f5f7"
_BORDER = "#e6e8ec"


def _shell(inner: str, preheader: str = "") -> str:
    """Enveloppe commune : fond gris, carte blanche centrée, en-tête wordmark, pied de page."""
    return f"""\
<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{_BG};">
<span style="display:none;font-size:1px;color:{_BG};line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">{preheader}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};padding:32px 12px;">
  <tr><td align="center">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#ffffff;border:1px solid {_BORDER};border-radius:16px;overflow:hidden;">
      <tr><td style="padding:30px 36px 8px;text-align:center;">
        <div style="font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:26px;font-weight:800;letter-spacing:-.5px;color:{_ACCENT};">adjugo</div>
      </td></tr>
      {inner}
      <tr><td style="padding:8px 36px 30px;">
        <hr style="border:none;border-top:1px solid {_BORDER};margin:18px 0;">
        <p style="margin:0;font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:12px;line-height:1.6;color:{_MUTED};text-align:center;">
          Adjugo — la plateforme qui simplifie la réponse aux marchés publics.<br>
          Si vous n'êtes pas à l'origine de cette demande, ignorez simplement cet email.
        </p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>"""


def _button(label: str, href: str) -> str:
    """Bouton « bulletproof » (table) qui s'affiche correctement jusque dans Outlook."""
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px auto 4px;">
  <tr><td align="center" bgcolor="{_ACCENT}" style="border-radius:11px;">
    <a href="{href}" target="_blank"
       style="display:inline-block;padding:14px 30px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;
              font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;border-radius:11px;">{label}</a>
  </td></tr>
</table>"""


def reset_password_html(link: str, name: str = "") -> str:
    """Email de réinitialisation de mot de passe (même charte que la confirmation d'adresse)."""
    hello = "Bonjour" + (f" {name.split()[0]}" if name and name.split() else "")
    inner = f"""\
      <tr><td style="padding:6px 36px 4px;">
        <h1 style="margin:14px 0 6px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:21px;font-weight:800;color:{_INK};text-align:center;">{hello}</h1>
        <p style="margin:0 0 20px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:15px;line-height:1.62;color:{_INK};text-align:center;">
          Vous avez demandé à réinitialiser votre mot de passe Adjugo. Cliquez ci-dessous pour en définir un nouveau.
        </p>
        {_button("Réinitialiser mon mot de passe", link)}
        <p style="margin:18px 0 4px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:12.5px;line-height:1.6;color:{_MUTED};text-align:center;">
          Ce lien est valable <b>1 heure</b>. S'il ne fonctionne pas, copiez-collez cette adresse&nbsp;:
        </p>
        <p style="margin:0;font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:11.5px;line-height:1.5;color:{_ACCENT};text-align:center;word-break:break-all;">{link}</p>
      </td></tr>"""
    return _shell(inner, preheader="Réinitialisez votre mot de passe Adjugo.")


def verify_email_html(link: str, name: str = "") -> str:
    """Email de confirmation d'adresse à l'inscription."""
    hello = "Bienvenue" + (f" {name.split()[0]}" if name and name.split() else "")
    inner = f"""\
      <tr><td style="padding:6px 36px 4px;">
        <h1 style="margin:14px 0 6px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:21px;font-weight:800;color:{_INK};text-align:center;">{hello}</h1>
        <p style="margin:0 0 20px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:15px;line-height:1.62;color:{_INK};text-align:center;">
          Plus qu'une étape pour activer votre compte Adjugo : confirmez votre adresse email.
        </p>
        {_button("Vérifier mon adresse email", link)}
        <p style="margin:18px 0 4px;font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:12.5px;line-height:1.6;color:{_MUTED};text-align:center;">
          Ce lien est valable <b>3 jours</b>. S'il ne fonctionne pas, copiez-collez cette adresse&nbsp;:
        </p>
        <p style="margin:0;font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-size:11.5px;line-height:1.5;color:{_ACCENT};text-align:center;word-break:break-all;">{link}</p>
      </td></tr>"""
    return _shell(inner, preheader="Confirmez votre adresse pour activer votre compte Adjugo.")
