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


def _candidate_transports() -> list[tuple[int, str]]:
    """Ordre d'essai (port, mode). On commence par le port configuré, puis on
    bascule sur les alternatives Brevo. Beaucoup d'hébergeurs PaaS (dont Railway)
    bloquent/throttlent le 587 sortant : 2525 (STARTTLS) et 465 (SSL) servent de
    repli. On déduplique en gardant le 1er essai = la config explicite de l'user."""
    primary_mode = "starttls" if settings.SMTP_TLS else "plain"
    primary = (int(settings.SMTP_PORT), primary_mode)
    fallbacks = [(587, "starttls"), (2525, "starttls"), (465, "ssl")]
    ordered: list[tuple[int, str]] = [primary]
    for t in fallbacks:
        if t not in ordered:
            ordered.append(t)
    return ordered


def _send_via(host: str, port: int, mode: str, msg: EmailMessage, timeout: int = 12) -> None:
    """Tente un envoi sur un (port, mode) donné. Lève en cas d'échec."""
    if mode == "ssl":
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx) as s:
            s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.send_message(msg)
    elif mode == "starttls":
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=timeout) as s:
            s.starttls(context=ctx)
            s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.send_message(msg)
    else:  # plain
        with smtplib.SMTP(host, port, timeout=timeout) as s:
            s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.send_message(msg)


def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Envoie un email. Retourne True si envoyé, False si désactivé ou en erreur.

    Auto-résilient : essaie plusieurs ports/modes (587 STARTTLS → 2525 STARTTLS →
    465 SSL) tant que la connexion échoue, pour survivre au blocage du 587 sortant
    fréquent sur les PaaS. Un échec d'AUTHENTIFICATION (identifiants faux) n'est pas
    réessayé sur les autres ports — inutile, et ça évite 3 timeouts en série."""
    if not is_enabled():
        logger.info("email désactivé (SMTP non configuré) — destinataire=%s sujet=%s", to, subject)
        return False

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    host = settings.SMTP_HOST
    last_err: Exception | None = None
    for port, mode in _candidate_transports():
        try:
            _send_via(host, port, mode, msg)
            logger.info("email envoyé destinataire=%s sujet=%s via=%s:%s", to, subject, host, port)
            return True
        except smtplib.SMTPAuthenticationError as e:
            # Identifiants refusés : inutile d'insister sur d'autres ports.
            logger.warning("échec envoi email destinataire=%s : auth refusée (%s)", to, e)
            return False
        except Exception as e:
            last_err = e
            logger.info("envoi email : %s:%s indisponible (%s) — essai suivant", host, port, e)
            continue
    logger.warning("échec envoi email destinataire=%s : aucun transport SMTP joignable (%s)", to, last_err)
    return False
