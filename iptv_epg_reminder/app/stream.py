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


_MIME = {"mp4": "video/mp4", "m4v": "video/mp4", "mkv": "video/x-matroska", "avi": "video/x-msvideo",
         "ts": "video/mp2t", "webm": "video/webm", "mov": "video/quicktime"}


def resolve_vod(kind: str, vid: str, ext: str, cfg: dict):
    """Adress till film (kind=movie) eller serieavsnitt (kind=episode) via Xtream. (url, ext)."""
    cr = epg.xtream_creds(cfg)
    if not cr or not vid:
        return None, ext
    base, user, pw = cr
    if kind == "movie" and not ext:
        c = store.conn()
        try:
            r = c.execute("select ext from catalog where kind='movie' and id=?", (vid,)).fetchone()
        finally:
            c.close()
        ext = (r["ext"] if r else "") or "mp4"
    ext = (ext or "mp4").lstrip(".")
    path = "movie" if kind == "movie" else "series"
    url = f"{base}/{path}/{user}/{pw}/{vid}.{ext}"
    _HOSTS.add(urlparse(url).netloc)
    return url, ext


def content_type_vod(entity: str, ext: str, ctype: str) -> str:
    ctype = (ctype or "auto").strip()
    if ctype != "auto" and not ctype.startswith(("application/x-mpegURL", "video/mp2t")):
        return ctype
    if "vlc" in entity.lower():
        return "music"
    return _MIME.get((ext or "").lower(), "video/mp4")


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


async def vod(request):
    """Proxy med Range-stöd för filmer/avsnitt i webbläsarspelaren."""
    import asyncio
    import state
    kind = request.match_info["kind"]
    vid, ext = request.match_info["id"], request.match_info["ext"]
    if kind not in ("movie", "episode"):
        raise web.HTTPNotFound()
    url, _ = await asyncio.to_thread(resolve_vod, kind, vid, ext, state.CFG)
    if not url:
        raise web.HTTPNotFound(text="no stream")
    hdr = {"User-Agent": "Mozilla/5.0"}
    if request.headers.get("Range"):
        hdr["Range"] = request.headers["Range"]
    sess = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=60), headers=hdr)
    try:
        r = await sess.get(url, allow_redirects=True)
    except Exception as e:
        await sess.close()
        raise web.HTTPBadGateway(text=scrub(e))
    try:
        if r.status >= 400:
            raise web.HTTPBadGateway(text=f"upstream {r.status}")
        h = {k: v for k, v in r.headers.items() if k in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges")}
        h.setdefault("Accept-Ranges", "bytes")
        resp = web.StreamResponse(status=r.status, headers=h)
        await resp.prepare(request)
        async for chunk in r.content.iter_chunked(128 * 1024):
            await resp.write(chunk)
        await resp.write_eof()
        return resp
    except (ConnectionResetError, asyncio.CancelledError):
        raise
    finally:
        r.release()
        await sess.close()


async def series_info(sid: str, cfg: dict):
    """Säsonger/avsnitt för en serie: {season: [{id,title,ext,num}]}."""
    cr = epg.xtream_creds(cfg)
    if not cr:
        raise RuntimeError("Requires an Xtream source")
    base, user, pw = cr
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), headers={"User-Agent": "Mozilla/5.0"}) as s:
        async with s.get(f"{base}/player_api.php", params={"username": user, "password": pw, "action": "get_series_info", "series_id": sid}) as r:
            r.raise_for_status()
            d = await r.json(content_type=None)
    out = {}
    eps = d.get("episodes") or {}
    if isinstance(eps, list):
        eps = {str(i + 1): v for i, v in enumerate(eps)}
    for season, lst in eps.items():
        out[str(season)] = [{"id": str(e.get("id")), "title": e.get("title") or f"E{e.get('episode_num')}",
                             "num": e.get("episode_num"), "ext": e.get("container_extension") or "mp4"} for e in (lst or [])]
    return out
