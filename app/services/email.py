"""
Service d'envoi d'emails (SMTP).
No-op silencieux si SMTP non configuré → ne casse jamais le dev.
"""
import json
import smtplib
import ssl
import logging
import urllib.request
import urllib.error
from email.message import EmailMessage
from email.utils import parseaddr

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("adjugo")

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def is_enabled() -> bool:
    # Actif si une clé API Brevo (voie HTTP, fiable sur PaaS) OU un SMTP est configuré.
    return bool(settings.BREVO_API_KEY or (settings.SMTP_HOST and settings.SMTP_USER))


def _sender() -> dict:
    """Décompose SMTP_FROM (« Adjugo <noreply@adjugo.pro> ») en {name, email}."""
    name, addr = parseaddr(settings.SMTP_FROM)
    return {"name": name or "Adjugo", "email": addr or "noreply@adjugo.pro"}


def _send_via_brevo_api(to: str, subject: str, text: str, html: str | None) -> bool:
    """Envoi via l'API HTTP de Brevo (port 443). Lève en cas d'échec réseau ;
    retourne False sur réponse d'erreur applicative (clé invalide, etc.)."""
    payload = {
        "sender": _sender(),
        "to": [{"email": to}],
        "subject": subject,
        "textContent": text,
    }
    if html:
        payload["htmlContent"] = html
    req = urllib.request.Request(
        BREVO_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": settings.BREVO_API_KEY,
            "content-type": "application/json",
            "accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if 200 <= resp.status < 300:
                logger.info("email envoyé destinataire=%s sujet=%s via=brevo-api", to, subject)
                return True
            logger.warning("échec envoi email destinataire=%s : brevo-api HTTP %s", to, resp.status)
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")[:300]
        logger.warning("échec envoi email destinataire=%s : brevo-api HTTP %s (%s)", to, e.code, body)
        return False


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

    # Voie privilégiée : API HTTP Brevo (port 443). Sur Railway/PaaS les ports SMTP
    # sortants sont bloqués → le SMTP ci-dessous ne sert qu'en dev local.
    if settings.BREVO_API_KEY:
        try:
            return _send_via_brevo_api(to, subject, text, html)
        except Exception as e:
            logger.warning("brevo-api injoignable (%s) — repli SMTP", e)

    if not (settings.SMTP_HOST and settings.SMTP_USER):
        logger.warning("échec envoi email destinataire=%s : aucune voie disponible", to)
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
