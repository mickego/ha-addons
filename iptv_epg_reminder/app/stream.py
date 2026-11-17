"""Strömadresser till kanaler: uppspelning på mediaspelare och proxy för webbläsarspelaren.

Strömadressen innehåller inloggning och byggs först när den behövs – den sparas aldrig
i påminnelser, historik eller events."""
import base64
import logging
from urllib.parse import urljoin, urlparse

import aiohttp
from aiohttp import web

import epg
import store
from util import scrub

log = logging.getLogger("stream")
_HOSTS: set = set()      # värdar proxyn får hämta från (leverantören + CDN som dyker upp i spellistor)


def resolve(cid: str, fmt: str, cfg: dict):
    """(url, kanalnamn) eller (None, namn) om kanalen saknar ström."""
    c = store.conn()
    try:
        r = c.execute("select name,stream_id,url from channels where id=?", (cid,)).fetchone()
    finally:
        c.close()
    if not r:
        return None, ""
    name = r["name"] or cid
    url = r["url"] or ""
    if not url and r["stream_id"]:
        cr = epg.xtream_creds(cfg)
        if cr:
            base, user, pw = cr
            url = f"{base}/live/{user}/{pw}/{r['stream_id']}.{'ts' if fmt == 'ts' else 'm3u8'}"
    if url:
        _HOSTS.add(urlparse(url).netloc)
    return (url or None), name


def content_type(entity: str, fmt: str, ctype: str) -> str:
    ctype = (ctype or "auto").strip()
    if ctype != "auto":
        return ctype
    if "vlc" in entity.lower():
        return "music"           # VLC-integrationen (telnet) accepterar bara music
    return "video/mp2t" if fmt == "ts" else "application/x-mpegURL"


# ------------------------------------------------------------------ proxy för webbläsaren
def _enc(u: str) -> str:
    return base64.urlsafe_b64encode(u.encode()).decode().rstrip("=")


def _dec(s: str) -> str:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode()


def _rewrite(text: str, base: str) -> str:
    import re
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            out.append(line)
        elif s.startswith("#"):
            def sub(m):
                u = urljoin(base, m.group(1))
                _HOSTS.add(urlparse(u).netloc)
                return f'URI="seg?u={_enc(u)}"'
            out.append(re.sub(r'URI="([^"]+)"', sub, line))
        else:
            u = urljoin(base, s)
            _HOSTS.add(urlparse(u).netloc)
            out.append(f"seg?u={_enc(u)}")
    return "\n".join(out) + "\n"


async def _fetch(request, url: str):
    if urlparse(url).scheme not in ("http", "https") or urlparse(url).netloc not in _HOSTS:
        raise web.HTTPForbidden(text="host not allowed")
    sess = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=30),
                                 headers={"User-Agent": "Mozilla/5.0"})
    try:
        r = await sess.get(url, allow_redirects=True)
    except Exception as e:
        await sess.close()
        raise web.HTTPBadGateway(text=scrub(e))
    if r.status >= 400:
        st = r.status
        r.release()
        await sess.close()
        raise web.HTTPBadGateway(text=f"upstream {st}")
    ct = r.headers.get("Content-Type", "")
    final = str(r.url)
    try:
        if "mpegurl" in ct.lower() or final.split("?")[0].endswith(".m3u8"):
            body = (await r.text(errors="ignore"))
            return web.Response(text=_rewrite(body, final), content_type="application/vnd.apple.mpegurl",
                                headers={"Cache-Control": "no-store"})
        resp = web.StreamResponse(status=200, headers={"Content-Type": ct or "video/mp2t", "Cache-Control": "no-store"})
        await resp.prepare(request)
        async for chunk in r.content.iter_chunked(64 * 1024):
            await resp.write(chunk)
        await resp.write_eof()
        return resp
    finally:
        r.release()
        await sess.close()


async def playlist(request):
    cid = request.match_info["cid"]
    import state
    import asyncio
    url, _ = await asyncio.to_thread(resolve, cid, "hls", state.CFG)
    if not url:
        raise web.HTTPNotFound(text="no stream")
    return await _fetch(request, url)


async def segment(request):
    try:
        u = _dec(request.query.get("u", ""))
    except Exception:
        raise web.HTTPBadRequest()
    return await _fetch(request, u)
