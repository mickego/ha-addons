"""Hämtning och parsning av XMLTV, Xtream-katalog och M3U."""
import asyncio
import gzip
import logging
import os
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlparse

import aiohttp

import store
from util import parse_xmltv_time, scrub

log = logging.getLogger("epg")


def _timeout():
    return aiohttp.ClientTimeout(total=900, sock_connect=30, sock_read=180)


def _headers(cfg):
    return {"User-Agent": cfg.get("user_agent") or "Mozilla/5.0", "Accept-Encoding": "gzip"}


# ---------------------------------------------------------------- XMLTV
async def download(url: str, cfg: dict) -> str:
    fd, path = tempfile.mkstemp(prefix="epg_", suffix=".xml")
    os.close(fd)
    try:
        async with aiohttp.ClientSession(timeout=_timeout(), headers=_headers(cfg)) as s:
            async with s.get(url) as r:
                r.raise_for_status()
                with open(path, "wb") as f:
                    async for chunk in r.content.iter_chunked(1 << 16):
                        f.write(chunk)
        return path
    except Exception:
        os.unlink(path)
        raise


def _parse_sync(path: str, days_forward: int) -> dict:
    now = int(time.time())
    lo, hi = now - 3600, now + days_forward * 86400
    with open(path, "rb") as fh:
        magic = fh.read(2)
    opener = gzip.open if magic == b"\x1f\x8b" else open

    c = store.conn()
    n_ch = n_pr = 0
    try:
        c.execute("delete from programs")
        c.execute("delete from channels where src='e'")
        batch_p, batch_c = [], []

        def flush():
            nonlocal batch_p, batch_c
            if batch_c:
                c.executemany("insert or ignore into channels(id,name,icon,cat,src) values(?,?,?,?,'e')", batch_c)
                batch_c = []
            if batch_p:
                c.executemany("insert or replace into programs values(?,?,?,?,?,?)", batch_p)
                batch_p = []

        with opener(path, "rb") as f:
            root = None
            for ev, el in ET.iterparse(f, events=("start", "end")):
                if ev == "start":
                    if root is None:
                        root = el
                    continue
                if el.tag == "channel":
                    cid = el.get("id")
                    if cid:
                        name = el.findtext("display-name") or cid
                        ic = el.find("icon")
                        batch_c.append((cid, name.strip(), ic.get("src") if ic is not None else None, None))
                        n_ch += 1
                    el.clear()
                elif el.tag == "programme":
                    st = parse_xmltv_time(el.get("start"))
                    sp = parse_xmltv_time(el.get("stop")) if el.get("stop") else None
                    if st is not None:
                        if sp is None:
                            sp = st + 1800
                        if sp > lo and st < hi:
                            title = (el.findtext("title") or "").strip()
                            sub = (el.findtext("sub-title") or "").strip()
                            if sub and sub.casefold() not in title.casefold():
                                title = f"{title}: {sub}" if title else sub
                            batch_p.append((
                                el.get("channel"), st, sp, title,
                                (el.findtext("desc") or "").strip(),
                                (el.findtext("category") or "").strip(),
                            ))
                            n_pr += 1
                    el.clear()
                    if len(batch_p) >= 5000:
                        flush()
                        if root is not None:
                            root.clear()
        flush()
        c.execute("delete from programs where channel_id is null")
        store.set_setting(c, "epg_updated", now)
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    return {"channels": n_ch, "programs": n_pr}


async def refresh_epg(cfg: dict) -> dict:
    url = cfg.get("epg_url")
    if not url:
        raise RuntimeError("Ingen EPG-URL konfigurerad")
    log.info("Hämtar EPG ...")
    path = await download(url, cfg)
    try:
        res = await asyncio.to_thread(_parse_sync, path, int(cfg.get("epg_days") or 7))
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    log.info("EPG klar: %s", res)
    return res


# ---------------------------------------------------------------- Xtream
def xtream_creds(cfg: dict):
    """Returnerar (bas-url, användare, lösenord) eller None."""
    for key in ("xtream_url", "epg_url"):
        u = cfg.get(key)
        if not u:
            continue
        p = urlparse(u)
        q = parse_qs(p.query)
        if q.get("username") and q.get("password"):
            return f"{p.scheme}://{p.netloc}", q["username"][0], q["password"][0]
    return None


async def _xt(session, creds, action, **extra):
    base, user, pw = creds
    params = {"username": user, "password": pw, "action": action, **extra}
    async with session.get(f"{base}/player_api.php", params=params) as r:
        r.raise_for_status()
        return await r.json(content_type=None)


def _s(v):
    return "" if v is None else str(v)


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


async def refresh_catalog(cfg: dict) -> dict:
    """Hämtar live/filmer/serier. Returnerar {'new': {kind: [namn,...]}, 'counts': {...}}."""
    creds = xtream_creds(cfg)
    if not creds and not cfg.get("playlist_url"):
        return {"new": {}, "counts": {}}
    if not creds:
        return await _refresh_m3u(cfg)

    if "\u2022" in creds[2] or "%E2%80%A2" in creds[2].upper():
        raise RuntimeError("Lösenordet i URL:en består av punkter (••••). Ange det riktiga lösenordet i epg_url.")
    out = {"new": {}, "counts": {}}
    async with aiohttp.ClientSession(timeout=_timeout(), headers=_headers(cfg)) as s:
        data = {}
        for kind, cat_act, list_act in (
            ("live", "get_live_categories", "get_live_streams"),
            ("movie", "get_vod_categories", "get_vod_streams"),
            ("series", "get_series_categories", "get_series"),
        ):
            try:
                cats = await _xt(s, creds, cat_act)
                items = await _xt(s, creds, list_act)
                if not isinstance(items, list):
                    items = []
                if not isinstance(cats, list):
                    cats = []
                data[kind] = (cats, items)
            except Exception as e:  # en typ får misslyckas utan att hela uppdateringen faller
                log.warning("Xtream %s misslyckades: %s", kind, scrub(e))

    if not data:
        raise RuntimeError("Xtream-inloggning misslyckades – kontrollera användarnamn, lösenord och adress i epg_url")

    def write():
        c = store.conn()
        try:
            for kind, (cats, items) in data.items():
                old_ids = {r["id"] for r in c.execute("select id from catalog where kind=?", (kind,))} if kind != "live" else set()
                c.execute("delete from categories where kind=?", (kind,))
                c.executemany(
                    "insert or replace into categories values(?,?,?)",
                    [(kind, _s(x.get("category_id")), _s(x.get("category_name"))) for x in cats],
                )
                if kind == "live":
                    c.execute("delete from channels where src='x'")
                    rows = []
                    for it in items:
                        sid = _s(it.get("stream_id"))
                        cid = _s(it.get("epg_channel_id")).strip() or f"x{sid}"
                        rows.append((cid, _s(it.get("name")).strip(), _s(it.get("stream_icon")) or None,
                                     _s(it.get("category_id")), "x", sid))
                    c.executemany("insert or replace into channels(id,name,icon,cat,src,stream_id) values(?,?,?,?,?,?)", rows)
                else:
                    c.execute("delete from catalog where kind=?", (kind,))
                    rows = []
                    for it in items:
                        iid = _s(it.get("stream_id") if kind == "movie" else it.get("series_id"))
                        year = _s(it.get("year") or it.get("releaseDate") or it.get("release_date"))[:4]
                        rows.append((kind, iid, _s(it.get("name")).strip(), _s(it.get("category_id")), year,
                                     _s(it.get("rating")), _s(it.get("stream_icon") or it.get("cover")),
                                     _int(it.get("added") or it.get("last_modified"))))
                    c.executemany("insert or replace into catalog values(?,?,?,?,?,?,?,?)", rows)
                    if old_ids:
                        new_rows = [r for r in rows if r[1] not in old_ids]
                        out["new"][kind] = [r[2] for r in new_rows][:500]
                out["counts"][kind] = len(items)
            store.set_setting(c, "catalog_updated", int(time.time()))
            c.commit()
        finally:
            c.close()

    await asyncio.to_thread(write)
    log.info("Katalog klar: %s", out["counts"])
    return out


# ---------------------------------------------------------------- M3U
_EXT = re.compile(r'(\w[\w-]*)="([^"]*)"')


async def _refresh_m3u(cfg: dict) -> dict:
    async with aiohttp.ClientSession(timeout=_timeout(), headers=_headers(cfg)) as s:
        async with s.get(cfg["playlist_url"]) as r:
            r.raise_for_status()
            text = await r.text(errors="ignore")

    def write():
        c = store.conn()
        try:
            c.execute("delete from channels where src='x'")
            c.execute("delete from categories where kind='live'")
            cats, rows, n = {}, [], 0
            attrs = None
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("#EXTINF"):
                    attrs = dict(_EXT.findall(line))
                    attrs["_name"] = line.rsplit(",", 1)[-1].strip()
                elif line and not line.startswith("#") and attrs is not None:
                    n += 1
                    grp = attrs.get("group-title", "")
                    cid = cats.setdefault(grp, str(len(cats) + 1))
                    rows.append((attrs.get("tvg-id") or f"x{n}", attrs.get("tvg-name") or attrs["_name"],
                                 attrs.get("tvg-logo") or None, cid, "x", str(n), line))
                    attrs = None
            c.executemany("insert or replace into channels(id,name,icon,cat,src,stream_id,url) values(?,?,?,?,?,?,?)", rows)
            c.executemany("insert into categories values('live',?,?)", [(v, k) for k, v in cats.items()])
            store.set_setting(c, "catalog_updated", int(time.time()))
            c.commit()
            return n
        finally:
            c.close()

    n = await asyncio.to_thread(write)
    return {"new": {}, "counts": {"live": n}}
