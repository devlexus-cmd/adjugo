"""
Service d'envoi d'emails (SMTP).
No-op silencieux si SMTP non configuré → ne casse jamais le dev.
"""
import smtplib
import ssl
import logging
from email.message import EmailMessage

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("adjugo")


def is_enabled() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER)


def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Envoie un email. Retourne True si envoyé, False si désactivé ou en erreur."""
    if not is_enabled():
        logger.info("email désactivé (SMTP non configuré) — destinataire=%s sujet=%s", to, subject)
        return False
    try:
        msg = EmailMessage()
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")

        if settings.SMTP_TLS:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
                s.starttls(context=ctx)
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
        logger.info("email envoyé destinataire=%s sujet=%s", to, subject)
        return True
    except Exception as e:
        logger.warning("échec envoi email destinataire=%s : %s", to, e)
        return False
