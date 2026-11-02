"""Auth token check and SSRF-safe URL fetching."""
import ipaddress
import secrets
import socket
from urllib.parse import urljoin, urlparse

import requests
from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

USER_AGENT = "Mozilla/5.0 (compatible; HebrewReader/1.0)"


def make_auth(expected_token: str):
    """Accepts 'Authorization: Bearer <token>' or '?token=' (needed for <audio src>)."""
    expected = expected_token.encode()
    bearer = HTTPBearer(auto_error=False)  # registers the scheme -> "Authorize" button in /docs

    def verify(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
               token: str | None = Query(default=None)) -> None:
        supplied = creds.credentials if creds else token
        # constant-time comparison: no timing side channel
        if not supplied or not secrets.compare_digest(supplied.encode(), expected):
            raise HTTPException(401, "Invalid or missing token",
                                headers={"WWW-Authenticate": "Bearer"})

    return verify


class UnsafeURLError(Exception):
    pass


def validate_public_url(url: str) -> None:
    """
    SSRF guard: the server fetches user-supplied links, so block anything that
    resolves to an internal address (localhost, 10.x, 192.168.x, cloud metadata 169.254.169.254...).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeURLError("Only http:// and https:// links are supported")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(parsed.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UnsafeURLError("Could not find that website") from e
    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0].split("%")[0])
        if not ip.is_global:
            raise UnsafeURLError("Link points to a private or internal address")


def safe_fetch(url: str, max_redirects: int = 5, max_bytes: int = 5 * 1024 * 1024,
               timeout: int = 15) -> bytes:
    """GET a page, re-validating every redirect hop (a public URL can redirect to 127.0.0.1)."""
    for _ in range(max_redirects + 1):
        validate_public_url(url)
        resp = requests.get(url, allow_redirects=False, timeout=timeout, stream=True,
                            headers={"User-Agent": USER_AGENT})
        try:
            if resp.is_redirect:
                url = urljoin(url, resp.headers["Location"])
                continue
            if resp.status_code >= 400:
                raise UnsafeURLError(f"The website returned an error ({resp.status_code})")
            body = b""
            for part in resp.iter_content(64 * 1024):
                body += part
                if len(body) > max_bytes:
                    raise UnsafeURLError("Page is too large")
            return body
        finally:
            resp.close()
    raise UnsafeURLError("Too many redirects")
