from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    port = parsed.port
    default = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    netloc = hostname if not port or default else f"{hostname}:{port}"
    parameters = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING
    ]
    return urlunsplit((scheme, netloc, parsed.path or "/", urlencode(sorted(parameters)), ""))
