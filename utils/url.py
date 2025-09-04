"""URL helpers for stream components."""

from __future__ import annotations

from urllib.parse import quote, unquote, urlsplit, urlunsplit


def normalize_stream_url(url: str) -> str:
    """Return URL with credentials decoded then re-encoded once.

    Parameters
    ----------
    url: str
        Input URL possibly containing percent-encoded username/password.

    Returns
    -------
    str
        URL with username/password decoded and re-encoded exactly once.
    """
    parts = urlsplit(url)
    if not parts.username and not parts.password:
        return url

    username = unquote(parts.username or "")
    password = unquote(parts.password or "")

    host = parts.hostname or ""
    if parts.port:
        host += f":{parts.port}"

    if username:
        creds = quote(username, safe="")
        if password:
            creds += ":" + quote(password, safe="")
        netloc = f"{creds}@{host}"
    else:
        netloc = host

    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def get_stream_type(url: str) -> str:
    """Return stream type based on the URL scheme.

    Parameters
    ----------
    url: str
        Source string representing the camera stream.

    Returns
    -------
    str
        ``"rtsp"`` when the URL starts with ``rtsp://``, ``"http"`` when it
        begins with ``http://`` or ``https://`` and ``"local"`` for anything
        else.
    """
    lowered = url.lower()
    if lowered.startswith("rtsp://"):
        return "rtsp"
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return "http"
    return "local"
