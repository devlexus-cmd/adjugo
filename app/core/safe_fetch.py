"""Récupération HTTP SORTANTE sûre (anti-SSRF) pour toute URL qui ne vient pas du code.

Pourquoi : une URL fournie par un utilisateur (ou lue dans un avis) ne doit jamais faire
interroger par le serveur une adresse interne (métadonnées cloud 169.254.169.254, service
local, réseau privé). Règles appliquées à CHAQUE requête, redirections comprises :

  1. https uniquement, port 443, pas d'identifiants dans l'URL ;
  2. hôte dans une LISTE BLANCHE explicite (domaine exact ou sous-domaine) ;
  3. toutes les adresses IP résolues doivent être publiques (pas de privé, loopback,
     link-local, multicast, réservé…) — une IP littérale est refusée d'emblée ;
  4. redirections suivies À LA MAIN (follow_redirects=False) et revalidées à chaque saut ;
  5. délais courts et corps de réponse BORNÉ (lecture en flux, arrêt au-delà du plafond).

Usage : `safe_get(url, allowed_hosts=DCE_HOSTS)` → SafeResponse, ou lève UnsafeURL /
ResponseTooLarge / httpx.HTTPError. Les appelants traitent toute exception comme
« ressource indisponible » (jamais de contenu inventé en repli).
"""
import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Iterable, Optional
from urllib.parse import urljoin, urlsplit

import httpx

# Hôtes officiels où vit un DCE / un avis récupéré automatiquement. Liste FERMÉE :
# ajouter un domaine ici est une décision de sécurité (il pourra être appelé par le serveur).
DCE_HOSTS = ("boamp.fr",)

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
DEFAULT_MAX_BYTES = 25 * 1024 * 1024     # un PDF de DCE tient largement sous 25 Mo
MAX_REDIRECTS = 3
_UA = {"User-Agent": "AdjugoBot/1.0 (+https://adjugo.fr)"}


class UnsafeURL(ValueError):
    """URL refusée (schéma, hôte hors liste blanche, IP non publique…)."""


class ResponseTooLarge(ValueError):
    """Réponse plus grosse que le plafond autorisé."""


@dataclass
class SafeResponse:
    url: str
    status_code: int
    headers: dict = field(default_factory=dict)
    content: bytes = b""

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


def _host_allowed(host: str, allowed_hosts: Iterable[str]) -> bool:
    host = host.lower().rstrip(".")
    for a in allowed_hosts:
        a = a.lower().strip(".")
        if host == a or host.endswith("." + a):
            return True
    return False


def _ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    # IPv4 encapsulée dans de l'IPv6 (::ffff:10.0.0.1, 6to4…) : on juge l'IPv4 réelle.
    mapped = getattr(addr, "ipv4_mapped", None) or getattr(addr, "sixtofour", None)
    if mapped is not None:
        addr = mapped
    return bool(addr.is_global) and not (
        addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast
        or addr.is_reserved or addr.is_unspecified)


def _resolve(host: str) -> list:
    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    return sorted({i[4][0] for i in infos})


def validate_url(url: str, allowed_hosts: Iterable[str] = DCE_HOSTS, resolve: bool = True) -> str:
    """Vérifie qu'une URL peut être appelée par le serveur. Retourne l'URL ou lève UnsafeURL."""
    if not url or not isinstance(url, str) or len(url) > 2048:
        raise UnsafeURL("URL absente ou invalide")
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        raise UnsafeURL("URL mal formée")
    if parts.scheme.lower() != "https":
        raise UnsafeURL("seul https est autorisé")
    if parts.username is not None or parts.password is not None:
        raise UnsafeURL("identifiants interdits dans l'URL")
    if port not in (None, 443):
        raise UnsafeURL("port non autorisé")
    host = (parts.hostname or "").lower()
    if not host:
        raise UnsafeURL("hôte absent")
    try:
        ipaddress.ip_address(host.strip("[]"))
        is_ip_literal = True
    except ValueError:
        is_ip_literal = False
    if is_ip_literal:
        raise UnsafeURL("adresse IP littérale interdite")
    if not _host_allowed(host, allowed_hosts):
        raise UnsafeURL("hôte hors liste blanche")
    if resolve:
        try:
            ips = _resolve(host)
        except OSError:
            raise UnsafeURL("hôte introuvable")
        if not ips or not all(_ip_is_public(ip) for ip in ips):
            raise UnsafeURL("l'hôte pointe vers une adresse non publique")
    return url.strip()


def safe_get(url: str, allowed_hosts: Iterable[str] = DCE_HOSTS,
             max_bytes: int = DEFAULT_MAX_BYTES, timeout=DEFAULT_TIMEOUT,
             client: Optional[httpx.Client] = None, max_redirects: int = MAX_REDIRECTS) -> SafeResponse:
    """GET borné et revalidé à chaque redirection. Ne suit jamais une redirection
    automatiquement : chaque `Location` repasse par validate_url."""
    own = client is None
    c = client or httpx.Client(follow_redirects=False, timeout=timeout, headers=_UA)
    try:
        current = url
        for _hop in range(max_redirects + 1):
            current = validate_url(current, allowed_hosts)
            with c.stream("GET", current, follow_redirects=False, timeout=timeout) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("location")
                    if not loc:
                        return SafeResponse(current, resp.status_code, dict(resp.headers), b"")
                    current = urljoin(current, loc)
                    continue
                declared = resp.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise ResponseTooLarge("réponse trop volumineuse")
                buf = bytearray()
                for chunk in resp.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        raise ResponseTooLarge("réponse trop volumineuse")
                return SafeResponse(current, resp.status_code,
                                    {k.lower(): v for k, v in resp.headers.items()}, bytes(buf))
        raise UnsafeURL("trop de redirections")
    finally:
        if own:
            c.close()
