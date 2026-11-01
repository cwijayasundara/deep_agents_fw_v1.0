from __future__ import annotations

import ipaddress
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from .models import Page, ToolError

_SKIP = {"script", "style", "noscript", "svg", "head"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._parts: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        elif tag in _SKIP:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag in _SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data.strip()
        elif not self._skip and data.strip():
            self._parts.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._parts)


def _check_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ToolError("only http(s) URLs are allowed")
    host = p.hostname
    if host == "localhost" or host.endswith(".internal"):
        raise ToolError("private hosts are not allowed")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return  # hostname; DNS-rebinding protection is out of scope for phase 0
    if not ip.is_global:
        raise ToolError("private addresses are not allowed")


class HttpFetch:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        max_bytes: int = 1_000_000,
        max_chars: int = 20_000,
        timeout: float = 20.0,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
        self._max_bytes = max_bytes
        self._max_chars = max_chars

    async def fetch(self, url: str) -> Page:
        _check_url(url)
        try:
            async with self._client.stream("GET", url) as resp:
                resp.raise_for_status()
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf += chunk
                    if len(buf) > self._max_bytes:
                        break
                ctype = resp.headers.get("content-type", "")
        except httpx.HTTPError as e:
            raise ToolError(f"fetch failed: {type(e).__name__}") from e
        raw = bytes(buf[: self._max_bytes]).decode("utf-8", errors="replace")
        if "html" in ctype or raw.lstrip().startswith("<"):
            parser = _Text()
            parser.feed(raw)
            title, text = parser.title, parser.text()
        else:
            title, text = "", raw
        truncated = len(buf) > self._max_bytes or len(text) > self._max_chars
        return Page(url=url, title=title, text=text[: self._max_chars], truncated=truncated)
