"""Masquage des secrets et des données personnelles avant écriture dans les journaux
et avant tout envoi à Sentry (audit cyber oct. 2026, vague 3).

Pourquoi : les chemins d'invitation (`/invite/<jeton>`, `/api/invite/<jeton>/...`), les
liens de confirmation et de réinitialisation (`?verify=`, `?reset=`, `?token=`) et les
adresses email apparaissaient en clair dans les journaux applicatifs, donc potentiellement
chez Sentry. La politique de confidentialité ne déclare que « journaux techniques,
identifiants techniques, adresse IP » : ces valeurs doivent être masquées à la source.

Un seul jeu de règles, utilisé par :
  - le filtre de journaux posé au démarrage sur les handlers (`RedactingFilter`) ;
  - les crochets Sentry `before_send` / `before_breadcrumb` (`app.core.observability`).

Règles :
  - valeur exacte de la clé du lien privé de démonstration (DEMO_LIEN_CLE) → `***` ;
  - `/invite/<jeton>`            → `/invite/***` (le reste du chemin est conservé) ;
  - `verify=…`, `token=…`, `code=…`, `reset=…` et autres paramètres secrets → `nom=***` ;
  - JWT (`eyJ…`) et `Bearer <jeton>` → `***` ;
  - adresse email `jean.dupont@domaine.fr` → `j***@domaine.fr` (le domaine reste lisible,
    utile au diagnostic d'un souci de délivrabilité).
Le masquage est idempotent : repasser un texte déjà masqué ne change rien.
"""
import logging
import re

MASK = "***"

# JWT : en-tête base64url d'un objet JSON (« {" » → « eyJ »), suivi de la charge et de la
# signature. On masque aussi un « eyJ… » isolé (fragment de jeton).
_RE_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]{5,}(?:\.[A-Za-z0-9_\-]*){0,2}")
_RE_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=\-]+")
# Jeton d'invitation dans un chemin : /invite/<jeton> et /api/invite/<jeton>/...
_RE_INVITE = re.compile(r"(/invite/)[^/?#\s\"'<>]+")
# Paramètres porteurs d'un secret (query string ou « clé=valeur » dans un message).
_SECRET_PARAMS = (
    "verify", "token", "code", "reset", "gtoken", "gcode", "state",
    "access_token", "refresh_token", "id_token", "api_key", "apikey",
    "password", "secret", "otp", "client_secret",
    "x-amz-signature", "x-amz-credential", "x-amz-security-token",
)
_RE_PARAM = re.compile(
    r"(?i)(?<![\w\-])(" + "|".join(re.escape(p) for p in _SECRET_PARAMS) + r")=([^&\s#\"'<>,;]+)")
_DOMAIN = r"([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,})"
# Pas d'ancrage à gauche : la correspondance la plus à gauche englobe toute la partie
# locale (y compris « Jean%20jean@… »), seul son premier caractère est conservé.
_RE_EMAIL = re.compile(r"([A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]*@" + _DOMAIN)
# Même chose encodée dans une URL (jean%40domaine.fr).
_RE_EMAIL_ENC = re.compile(r"(?i)([A-Za-z0-9._+\-])[A-Za-z0-9._+\-]*%40" + _DOMAIN)

# Clés de dictionnaire dont la valeur est TOUJOURS masquée (évènements Sentry : corps de
# requête, variables, extras…). Comparaison insensible à la casse, tirets = soulignés.
SENSITIVE_KEYS = frozenset({
    "password", "new_password", "old_password", "current_password", "hashed_password",
    "token", "access_token", "refresh_token", "id_token", "gtoken", "gcode", "code",
    "verify", "reset", "reset_token", "invite_token", "state", "nonce", "otp",
    "secret", "client_secret", "api_key", "apikey", "authorization", "cookie", "cookies",
    "set_cookie", "x_cron_secret", "x_api_key", "proxy_authorization",
})


def _secrets_exacts():
    """Secrets de configuration à masquer par leur VALEUR exacte, où qu'ils apparaissent :
    la clé du lien privé de démonstration (DEMO_LIEN_CLE). Elle ne doit atteindre aucun
    journal ni Sentry, même recopiée par erreur dans un message."""
    try:
        from app.core.demo_guard import demo_lien_cle   # même règle que les routes (≥ 32 caractères)
        v = demo_lien_cle()
    except Exception:
        return ()
    return (v,) if v else ()


def mask_text(text):
    """Masque jetons, secrets et adresses email dans une chaîne. Non-chaîne : inchangé."""
    if not isinstance(text, str) or not text:
        return text
    for v in _secrets_exacts():
        if v in text:
            text = text.replace(v, MASK)
    s = _RE_JWT.sub(MASK, text)
    s = _RE_BEARER.sub(lambda m: m.group(1) + MASK, s)
    s = _RE_INVITE.sub(lambda m: m.group(1) + MASK, s)
    s = _RE_PARAM.sub(lambda m: m.group(1) + "=" + MASK, s)
    s = _RE_EMAIL.sub(lambda m: m.group(1) + MASK + "@" + m.group(2), s)
    s = _RE_EMAIL_ENC.sub(lambda m: m.group(1) + MASK + "%40" + m.group(2), s)
    return s


def _is_sensitive_key(key) -> bool:
    return isinstance(key, str) and key.strip().lower().replace("-", "_") in SENSITIVE_KEYS


def redact(obj, _depth: int = 0):
    """Copie masquée d'une structure (dict / liste / chaîne), pour les évènements Sentry.
    Les valeurs des clés sensibles sont remplacées ; toutes les chaînes passent par
    `mask_text`. Profondeur bornée : au-delà, la valeur est remplacée (jamais envoyée
    telle quelle)."""
    if _depth > 25:
        return MASK
    if isinstance(obj, str):
        return mask_text(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _is_sensitive_key(k) and v not in (None, "", [], {}):
                out[k] = MASK
            else:
                out[k] = redact(v, _depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact(v, _depth + 1) for v in obj]
    return obj


class RedactingFilter(logging.Filter):
    """Filtre de journaux : masque le message FORMATÉ (gabarit + `record.args`), la trace
    d'exception et la pile. Posé sur les handlers au démarrage (voir observability)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True  # message mal formé : on laisse logging signaler sa propre erreur
        masked = mask_text(msg)
        if masked != msg:
            # Les arguments sont déjà fusionnés dans le message masqué : on les retire,
            # sinon un formateur (ou Sentry) pourrait les réinjecter en clair.
            record.msg = masked
            record.args = None
        try:
            if record.exc_info and not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            if record.exc_text:
                record.exc_text = mask_text(record.exc_text)
            if record.stack_info:
                record.stack_info = mask_text(record.stack_info)
        except Exception:
            pass
        return True


def install_log_redaction(logger_names=("", "uvicorn", "uvicorn.error", "uvicorn.access")) -> None:
    """Pose le filtre (une seule fois) sur les handlers des journaux indiqués ("" = racine)."""
    for name in logger_names:
        for h in logging.getLogger(name).handlers:
            if not any(isinstance(f, RedactingFilter) for f in h.filters):
                h.addFilter(RedactingFilter())
