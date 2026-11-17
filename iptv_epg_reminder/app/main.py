"""IPTV EPG Reminders – Home Assistant add-on (ingress dashboard + scheduler)."""
import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

from aiohttp import web

import engine
import epg
import ha
import state
import store
import stream
from i18n import tr, LANGS
from util import compile_query, scrub

VERSION = "2.0.0"
WEB_DIR = os.path.join(os.path.dirname(__file__), "web")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")

LOCK = asyncio.Lock()
ENT_RX = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
NUM_RX = re.compile(r"^\d{1,5}$")


def rows(c, sql, args=()):
    return [dict(r) for r in c.execute(sql, args)]


def ERR(code, detail=None, status=400):
    d = {"error": code}
    if detail:
        d["detail"] = detail
    return d, status


# ------------------------------------------------------------------ sök
def time_range(when: str, now: int):
    z = state.tz()
    dt = datetime.fromtimestamp(now, z)
    sod = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if when == "now":
        return now, now + 1
    if when == "today":
        return now, int((sod + timedelta(days=1)).timestamp())
    if when == "tomorrow":
        return int((sod + timedelta(days=1)).timestamp()), int((sod + timedelta(days=2)).timestamp())
    if when == "week":
        return now, now + 7 * 86400
    return now, 2**40


def search_sync(p: dict):
    now = int(time.time())
    kind = p.get("kind", "live_prog")
    q = compile_query(p.get("q", ""))
    cat = p.get("cat") or ""
    limit = min(int(p.get("limit") or 150), 500)
    offset = int(p.get("offset") or 0)
    c = store.conn()
    try:
        out, total = [], 0
        if kind == "live_prog":
            lo, hi = time_range(p.get("when", "today"), now)
            chq = compile_query(p.get("channel", ""))
            in_descr = p.get("descr") in ("1", "true", True)
            sql = ("select p.channel_id,p.start,p.stop,p.title,p.descr,p.category,c.name cname,c.icon,"
                   "(c.stream_id is not null and c.stream_id!='') playable "
                   "from programs p left join channels c on c.id=p.channel_id where p.stop>? and p.start<?")
            args = [lo, hi]
            if cat:
                sql += " and c.cat=?"
                args.append(cat)
            if p.get("fav") in ("1", "true"):
                sql += " and p.channel_id in (select channel_id from favorites)"
            sql += " order by p.start, c.name"
            have = {(r["channel_id"], r["start"]) for r in c.execute(
                "select channel_id,start from reminders where kind='program' and enabled=1")}
            for r in c.execute(sql, args):
                if chq and not chq(r["cname"] or r["channel_id"]):
                    continue
                if q and not q(r["title"], r["descr"] if in_descr else None, (r["cname"], r["category"])):
                    continue
                total += 1
                if total <= offset or len(out) >= limit:
                    continue
                d = dict(r)
                d["has_reminder"] = (r["channel_id"], r["start"]) in have
                out.append(d)
        elif kind == "live_chan":
            sql = "select id,name,icon,cat,(stream_id is not null and stream_id!='') playable from channels"
            args, where = [], []
            if cat:
                where.append("cat=?")
                args.append(cat)
            if p.get("fav") in ("1", "true"):
                where.append("id in (select channel_id from favorites)")
            if where:
                sql += " where " + " and ".join(where)
            sql += " order by name collate nocase"
            favs = {r[0] for r in c.execute("select channel_id from favorites")}
            cmap = engine.get_cmap(c)
            for r in c.execute(sql, args):
                if q and not q(r["name"]):
                    continue
                total += 1
                if total <= offset or len(out) >= limit:
                    continue
                d = dict(r)
                d["fav"] = r["id"] in favs
                d["number"] = cmap.get(r["id"])
                now_p = c.execute("select title,start,stop from programs where channel_id=? and start<=? and stop>? limit 1",
                                  (r["id"], now, now)).fetchone()
                d["now"] = dict(now_p) if now_p else None
                out.append(d)
        else:
            sql = "select * from catalog where kind=?"
            args = [kind]
            if cat:
                sql += " and cat=?"
                args.append(cat)
            sql += " order by " + ("name collate nocase" if q else "added desc, name collate nocase")
            for r in c.execute(sql, args):
                if q and not q(r["name"]):
                    continue
                total += 1
                if total <= offset or len(out) >= limit:
                    continue
                out.append(dict(r))
        return {"total": total, "items": out}
    finally:
        c.close()


def grid_sync(p: dict):
    now = int(time.time())
    z = state.tz()
    hours = min(max(int(p.get("hours") or 3), 1), 12)
    if p.get("from"):
        frm = int(p["from"])
    elif p.get("day") not in (None, ""):
        dt = datetime.fromtimestamp(now, z).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=int(p["day"]))
        frm = int(dt.timestamp()) + int(p.get("hour") or 18) * 3600
        if int(p["day"]) == 0:
            frm = now - now % 1800 - 1800
    else:
        frm = now - now % 1800 - 1800
    to = frm + hours * 3600
    chq = compile_query(p.get("q", ""))
    hl = compile_query(p.get("hl", ""))
    cat = p.get("cat") or ""
    only_fav = p.get("fav") in ("1", "true")
    limit = min(int(p.get("limit") or 80), 300)
    c = store.conn()
    try:
        cmap = engine.get_cmap(c)
        favs = {r[0] for r in c.execute("select channel_id from favorites")}
        have = {(r["channel_id"], r["start"]) for r in c.execute(
            "select channel_id,start from reminders where kind='program' and enabled=1")}
        sql = ("select p.channel_id,p.start,p.stop,p.title,p.descr,p.category,c.name cname,c.icon,c.stream_id sid from programs p "
               "left join channels c on c.id=p.channel_id where p.stop>? and p.start<?")
        args = [frm, to]
        if cat:
            sql += " and c.cat=?"
            args.append(cat)
        sql += " order by c.name collate nocase, p.channel_id, p.start"
        chans = {}
        for r in c.execute(sql, args):
            if only_fav and r["channel_id"] not in favs:
                continue
            name = r["cname"] or r["channel_id"]
            if chq and not chq(name):
                continue
            ch = chans.get(r["channel_id"])
            if ch is None:
                ch = chans[r["channel_id"]] = {"id": r["channel_id"], "name": name, "icon": r["icon"],
                                               "number": cmap.get(r["channel_id"]), "fav": r["channel_id"] in favs, "playable": bool(r["sid"]),
                                               "programs": []}
            ch["programs"].append({"start": r["start"], "stop": r["stop"], "title": r["title"],
                                   "descr": (r["descr"] or "")[:400], "category": r["category"],
                                   "has_reminder": (r["channel_id"], r["start"]) in have,
                                   "hit": bool(hl and hl(r["title"]))})
        lst = sorted(chans.values(), key=lambda x: not x["fav"])
        return {"from": frm, "to": to, "hours": hours, "now": now, "total": len(lst), "channels": lst[:limit]}
    finally:
        c.close()


# ------------------------------------------------------------------ validering
def clean_actions(lst):
    out = []
    for a in lst or []:
        t = a.get("type")
        when = a.get("when") if a.get("when") in ("notify", "start") else "notify"
        targets = [str(x) for x in (a.get("targets") or [])]
        vol = a.get("volume")
        vol = None if vol in (None, "") else max(0, min(100, float(vol)))
        if t == "tts":
            text = (a.get("text") or "").strip()
            if not text:
                return None, ERR("err_tts_text")
            if not targets:
                return None, ERR("err_pick_player")
            out.append({"type": t, "when": when, "text": text, "targets": targets, "tts_entity": (a.get("tts_entity") or "").strip(),
                        "language": (a.get("language") or "").strip(), "volume": vol})
        elif t == "sound":
            value = (a.get("value") or "").strip()
            if not value:
                return None, ERR("err_sound_value")
            if not targets:
                return None, ERR("err_pick_player")
            out.append({"type": t, "when": when, "source": "url" if a.get("source") == "url" else "file", "value": value,
                        "targets": targets, "volume": vol, "content_type": (a.get("content_type") or "music").strip()})
        elif t == "play":
            if not targets:
                return None, ERR("err_pick_player")
            fmt = "ts" if a.get("fmt") == "ts" else "hls"
            out.append({"type": t, "when": when, "channel_id": (a.get("channel_id") or "").strip(), "fmt": fmt,
                        "targets": targets, "volume": vol, "content_type": (a.get("content_type") or "auto").strip()})
        elif t == "service":
            svc = (a.get("service") or "").strip()
            if not ENT_RX.match(svc):
                return None, ERR("err_service_name")
            raw = (a.get("data") or "").strip() or "{}"
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise ValueError
            except ValueError:
                return None, ERR("err_service_json")
            out.append({"type": t, "when": when, "service": svc, "data": raw})
        elif t == "set_entity":
            ent = (a.get("entity_id") or "").strip()
            if not ENT_RX.match(ent):
                return None, ERR("err_entity_id")
            out.append({"type": t, "when": when, "entity_id": ent, "value": str(a.get("value", ""))})
        else:
            return None, ERR("err_action_type")
    return out, None


def clean_opts(o):
    o = o or {}
    out = {}
    for k in ("title_tpl", "msg_tpl"):
        if (o.get(k) or "").strip():
            out[k] = o[k].strip()[:400]
    for k in ("buttons", "only_home", "ignore_quiet"):
        if o.get(k):
            out[k] = True
    if o.get("snooze_min"):
        out["snooze_min"] = max(1, min(int(o["snooze_min"]), 240))
    pre = o.get("pre") or {}
    if (pre.get("entity") or "").strip():
        out["pre"] = {"entity": pre["entity"].strip(), "wait": max(0, min(float(pre.get("wait") or 0), 60))}
    return out


def build_fields(b, d, cmap, existing=None):
    """Bygger databasfält från ett API-anrop. Returnerar (fält, fel)."""
    kind = existing["kind"] if existing else b.get("kind")
    if kind not in ("program", "rule", "time"):
        return None, ERR("err_unknown_type")
    ntype = b.get("ntype") or "push"
    if ntype not in ha.NOTIFY_TYPES:
        return None, ERR("err_unknown_ntype")
    targets = [str(t) for t in (b.get("targets") or [])]
    scope = "live" if kind == "time" else (existing["scope"] if existing else (b.get("scope") or "live"))
    lead = 0 if kind == "time" else max(0, min(int(b.get("lead") or 0), 1440))
    tune = 1 if (b.get("tune") and scope == "live") else 0
    tune_number = (str(b.get("tune_number") or "").strip()) or None
    tune_entity = (b.get("tune_entity") or "").strip() or None
    tune_when = b.get("tune_when") if b.get("tune_when") in ("start", "notify") else "start"
    if tune_number and not NUM_RX.match(tune_number):
        return None, ERR("err_number_digits")
    actions, err = clean_actions(b.get("actions"))
    if err:
        return None, err
    try:
        opts = clean_opts(b.get("opts"))
    except (TypeError, ValueError):
        return None, ERR("err_bad_options")
    if ntype not in ("persistent", "none") and not targets:
        return None, ERR("err_pick_device")
    if ntype == "none" and not tune and not actions:
        return None, ERR("err_nothing_to_do")
    if tune:
        if not tune_entity:
            tune_entity = d.get("tune_entity") or None
        if not tune_entity:
            return None, ERR("err_pick_remote")
        cid = existing["channel_id"] if existing and kind == "program" else b.get("channel_id")
        if not tune_number and kind in ("program", "time") and not cmap.get(cid):
            return None, ERR("err_need_number")
    f = dict(scope=scope, label=b.get("label") or b.get("title") or b.get("pattern") or b.get("channel_pattern"),
             lead=lead, ntype=ntype, targets=json.dumps(targets), tune=tune, tune_entity=tune_entity,
             tune_number=tune_number, tune_when=tune_when, actions=json.dumps(actions), opts=json.dumps(opts))
    if not existing:
        f.update(kind=kind, enabled=1, created=int(time.time()), channel_id=b.get("channel_id"))
    if kind == "program":
        if not existing:
            if not b.get("channel_id") or not b.get("start"):
                return None, ERR("err_missing_program")
            f.update(start=b.get("start"), stop=b.get("stop"), title=b.get("title"))
        else:
            f["label"] = b.get("label") or existing["label"]
    elif kind == "rule":
        if not (b.get("pattern") or b.get("channel_pattern")):
            return None, ERR("err_pattern_needed")
        f.update(pattern=b.get("pattern"), channel_pattern=b.get("channel_pattern"), in_descr=1 if b.get("in_descr") else 0)
        if existing:
            f["channel_id"] = b.get("channel_id") or existing.get("channel_id")
    else:
        at = str(b.get("at_time") or "").strip()
        if not re.fullmatch(r"\d{1,2}:\d{2}", at) or int(at.split(":")[0]) > 23 or int(at.split(":")[1]) > 59:
            return None, ERR("err_time_invalid")
        at = f"{int(at.split(':')[0]):02d}:{at.split(':')[1]}"
        repeat = b.get("repeat") or "once"
        if repeat == "once":
            try:
                dt = datetime.strptime(f"{b.get('date')} {at}", "%Y-%m-%d %H:%M").replace(tzinfo=state.tz())
            except ValueError:
                return None, ERR("err_date_invalid")
            if int(dt.timestamp()) <= time.time():
                return None, ERR("err_time_past")
            f.update(start=int(dt.timestamp()), at_time=at, days=None)
        else:
            days = {"daily": list(range(7)), "weekdays": list(range(5))}.get(repeat) or \
                sorted({int(x) for x in (b.get("days") or []) if str(x).isdigit() and 0 <= int(x) <= 6})
            if not days:
                return None, ERR("err_pick_weekday")
            f.update(at_time=at, days=json.dumps(days), start=None)
        f["label"] = b.get("label") or engine.T("default_label")
        f["channel_id"] = b.get("channel_id")
    return f, None


# ------------------------------------------------------------------ uppdatering
async def do_refresh():
    if LOCK.locked():
        return
    async with LOCK:
        state.STATE["refreshing"] = True
        state.STATE["errors"] = []
        try:
            try:
                res = await epg.refresh_catalog(state.CFG)
                if res.get("new"):
                    await engine.new_titles_alert(res["new"])
            except Exception as e:
                log.error("catalog: %s", scrub(e))
                state.STATE["errors"].append(f"Catalog: {scrub(e)}")
            if state.CFG.get("epg_url"):
                try:
                    await epg.refresh_epg(state.CFG)
                except Exception as e:
                    log.error("epg: %s", scrub(e))
                    state.STATE["errors"].append(f"EPG: {scrub(e)}")
            state.STATE["last_refresh"] = int(time.time())
        finally:
            state.STATE["refreshing"] = False


async def scheduler_loop():
    while True:
        try:
            await engine.tick()
        except Exception:
            log.exception("scheduler")
        await asyncio.sleep(30)


async def refresh_loop():
    await asyncio.sleep(3)
    hours = max(1, int(state.CFG.get("refresh_hours") or 6))
    age = time.time() - await asyncio.to_thread(engine.setting_get_sync, "epg_updated", 0)
    if age > hours * 3600:
        await do_refresh()
    while True:
        await asyncio.sleep(hours * 3600)
        await do_refresh()


# ------------------------------------------------------------------ HTTP
def J(data, status=200):
    return web.json_response(data, status=status)


def JE(pair):
    return web.json_response(pair[0], status=pair[1])


async def hls_js(request):
    return web.FileResponse(os.path.join(WEB_DIR, "hls.min.js"), headers={"Content-Type": "text/javascript; charset=utf-8"})


async def cards_js(request):
    return web.FileResponse(os.path.join(WEB_DIR, "epg-cards.js"), headers={
        "Cache-Control": "no-store", "Content-Type": "text/javascript; charset=utf-8",
        "Content-Disposition": 'attachment; filename="epg-cards.js"'})


async def index(request):
    return web.FileResponse(os.path.join(WEB_DIR, "index.html"), headers={"Cache-Control": "no-store"})


async def api_status(request):
    def q():
        c = store.conn()
        try:
            return {
                "channels": c.execute("select count(*) from channels").fetchone()[0],
                "programs": c.execute("select count(*) from programs").fetchone()[0],
                "movies": c.execute("select count(*) from catalog where kind='movie'").fetchone()[0],
                "series": c.execute("select count(*) from catalog where kind='series'").fetchone()[0],
                "epg_updated": store.get_setting(c, "epg_updated", 0),
                "catalog_updated": store.get_setting(c, "catalog_updated", 0),
                "reminders": c.execute("select count(*) from reminders where enabled=1").fetchone()[0],
            }
        finally:
            c.close()

    d = await asyncio.to_thread(q)
    host = urlparse(state.CFG.get("epg_url") or "").netloc
    d.update(tz=state.STATE["tz"], refreshing=state.STATE["refreshing"], errors=state.STATE["errors"], version=VERSION,
             epg_host=host, xtream=bool(epg.xtream_creds(state.CFG)), now=int(time.time()), lang=state.lang(),
             configured=bool(state.CFG.get("epg_url") or state.CFG.get("playlist_url")), in_ha=bool(ha.TOKEN))
    return J(d)


async def api_categories(request):
    kind = request.query.get("kind", "live")

    def q():
        c = store.conn()
        try:
            return rows(c, "select id,name from categories where kind=? order by name collate nocase", (kind,))
        finally:
            c.close()

    return J(await asyncio.to_thread(q))


async def api_search(request):
    return J(await asyncio.to_thread(search_sync, dict(request.query)))


async def api_grid(request):
    return J(await asyncio.to_thread(grid_sync, dict(request.query)))


async def api_targets(request):
    t = await ha.targets()
    t["types"] = ha.NOTIFY_TYPES
    return J(t)


async def api_entities(request):
    return J(await ha.search_entities(request.query.get("q", "")))


async def api_schedule(request):
    return J(await asyncio.to_thread(engine.schedule_sync))


def list_rem_sync():
    c = store.conn()
    try:
        return [engine.rem_dict(r) for r in c.execute("select * from reminders order by kind desc, created desc")]
    finally:
        c.close()


async def api_reminders(request):
    return J(await asyncio.to_thread(list_rem_sync))


def _insert_sync(b):
    c = store.conn()
    try:
        d = store.load_defaults(c, state.CFG)
        f, err = build_fields(b, d, engine.get_cmap(c))
        if err:
            return None, err
        cur = c.execute(f"insert into reminders({','.join(f)}) values({','.join('?' * len(f))})", list(f.values()))
        if f.get("tune_number") and b.get("remember_number") and b.get("channel_id"):
            c.execute("insert or replace into channel_map values(?,?)", (b["channel_id"], f["tune_number"]))
        c.commit()
        return cur.lastrowid, None
    finally:
        c.close()


def _update_sync(rid, b):
    c = store.conn()
    try:
        row = c.execute("select * from reminders where id=?", (rid,)).fetchone()
        if not row:
            return None, ERR("err_not_found", status=404)
        existing = engine.rem_dict(row)
        d = store.load_defaults(c, state.CFG)
        f, err = build_fields(b, d, engine.get_cmap(c), existing)
        if err:
            return None, err
        sets = ",".join(f"{k}=?" for k in f)
        c.execute(f"update reminders set {sets} where id=?", list(f.values()) + [rid])
        c.execute("delete from fired where reminder_id=?", (rid,))
        if f.get("tune_number") and b.get("remember_number") and (b.get("channel_id") or existing.get("channel_id")):
            c.execute("insert or replace into channel_map values(?,?)",
                      (b.get("channel_id") or existing["channel_id"], f["tune_number"]))
        c.commit()
        return rid, None
    finally:
        c.close()


async def api_reminder_add(request):
    rid, err = await asyncio.to_thread(_insert_sync, await request.json())
    return JE(err) if err else J({"id": rid})


async def api_reminder_update(request):
    rid, err = await asyncio.to_thread(_update_sync, int(request.match_info["id"]), await request.json())
    return JE(err) if err else J({"id": rid})


async def api_reminder_del(request):
    rid = int(request.match_info["id"])

    def d():
        c = store.conn()
        c.execute("delete from reminders where id=?", (rid,))
        c.execute("delete from fired where reminder_id=?", (rid,))
        c.execute("delete from snoozes where rem_id=?", (rid,))
        c.commit()
        c.close()

    await asyncio.to_thread(d)
    asyncio.create_task(engine.publish_sensors())
    return J({"ok": True})


async def api_reminder_toggle(request):
    rid = int(request.match_info["id"])

    def t():
        c = store.conn()
        c.execute("update reminders set enabled=1-enabled where id=?", (rid,))
        c.commit()
        c.close()

    await asyncio.to_thread(t)
    asyncio.create_task(engine.publish_sensors())
    return J({"ok": True})


async def api_snooze_del(request):
    sid = int(request.match_info["id"])

    def d():
        c = store.conn()
        c.execute("delete from snoozes where id=?", (sid,))
        c.commit()
        c.close()

    await asyncio.to_thread(d)
    return J({"ok": True})


async def api_saved(request):
    def q():
        c = store.conn()
        try:
            return rows(c, "select id,kind,pattern from saved order by id")
        finally:
            c.close()

    return J(await asyncio.to_thread(q))


async def api_saved_add(request):
    b = await request.json()
    if not (b.get("pattern") or "").strip():
        return JE(ERR("err_empty_keyword"))

    def a():
        c = store.conn()
        if not c.execute("select 1 from saved where kind=? and pattern=?", (b["kind"], b["pattern"].strip())).fetchone():
            c.execute("insert into saved(kind,pattern,created) values(?,?,?)", (b["kind"], b["pattern"].strip(), int(time.time())))
            c.commit()
        c.close()

    await asyncio.to_thread(a)
    return J({"ok": True})


async def api_saved_del(request):
    sid = int(request.match_info["id"])

    def d():
        c = store.conn()
        c.execute("delete from saved where id=?", (sid,))
        c.commit()
        c.close()

    await asyncio.to_thread(d)
    return J({"ok": True})


async def api_settings(request):
    d = await asyncio.to_thread(engine.load_defaults_sync)
    d["lang"] = state.lang()
    return J(d)


async def api_settings_set(request):
    b = await request.json()

    def s():
        c = store.conn()
        cur = store.load_defaults(c, state.CFG)
        for k, default in store.DEFAULTS.items():
            if k in b:
                v = b[k]
                if isinstance(default, bool):
                    v = bool(v)
                elif isinstance(default, int):
                    v = int(float(v or 0))
                elif isinstance(default, float):
                    v = float(v or default)
                elif isinstance(default, list):
                    v = [str(x) for x in (v or [])]
                else:
                    v = str(v or "").strip()
                cur[k] = v
        store.set_setting(c, "defaults", cur)
        c.close()

    await asyncio.to_thread(s)
    return J({"ok": True})


async def api_lang(request):
    b = await request.json()
    lang = b.get("lang") if b.get("lang") in LANGS else "sv"
    state.STATE["lang"] = lang
    await asyncio.to_thread(engine.setting_set_sync, "lang", lang)
    asyncio.create_task(engine.publish_sensors())
    return J({"ok": True, "lang": lang})


async def api_favorites(request):
    def q():
        c = store.conn()
        try:
            return [r[0] for r in c.execute("select channel_id from favorites")]
        finally:
            c.close()

    return J(await asyncio.to_thread(q))


async def api_favorites_set(request):
    b = await request.json()

    def s():
        c = store.conn()
        if b.get("on"):
            c.execute("insert or ignore into favorites values(?)", (b["channel_id"],))
        else:
            c.execute("delete from favorites where channel_id=?", (b["channel_id"],))
        c.commit()
        c.close()

    await asyncio.to_thread(s)
    return J({"ok": True})


async def api_history(request):
    def q():
        c = store.conn()
        try:
            out = rows(c, "select * from history order by id desc limit 40")
            for r in out:
                r["targets"] = json.loads(r["targets"] or "[]")
            return out
        finally:
            c.close()

    return J(await asyncio.to_thread(q))


async def api_refresh(request):
    asyncio.create_task(do_refresh())
    return J({"ok": True})


def _sample_ctx():
    now = datetime.now(state.tz())
    return {"title": "Test program", "channel": "Test channel", "number": "11", "start": now.strftime("%H:%M"),
            "end": (now + timedelta(minutes=30)).strftime("%H:%M"), "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"), "minutes": "10", "status": engine.T("status_future", minutes=10, channel="Test channel", start=now.strftime("%H:%M")),
            "label": "Test", "lead": "10", "description": "Sample description", "category": "Sport", "reminder_id": "0"}


async def api_test(request):
    b = await request.json()
    ntype = b.get("ntype") or "push"
    d = await asyncio.to_thread(engine.load_defaults_sync)
    ctx = _sample_ctx()
    title = await engine.render(b.get("title_tpl") or engine.T("test_title"), ctx)
    msg = await engine.render(b.get("msg_tpl") or engine.T("test_msg"), ctx)
    errs = await ha.send(ntype, b.get("targets") or [], title, msg, tag="epg_test", image=None,
                         tts_entity=d.get("tts_entity") or "", language=d.get("tts_language") or state.lang())
    return J({"ok": not errs, "errors": errs})


async def api_test_action(request):
    b = await request.json()
    acts, err = clean_actions([b.get("action") or {}])
    if err:
        return J({"ok": False, "errors": [err[0]["error"]], "code": err[0]["error"]})
    d = await asyncio.to_thread(engine.load_defaults_sync)
    try:
        detail = await engine.run_action(acts[0], _sample_ctx(), d)
        return J({"ok": True, "detail": detail})
    except Exception as e:
        return J({"ok": False, "errors": [scrub(e)]})


async def api_channelmap(request):
    def q():
        c = store.conn()
        try:
            return rows(c, "select m.channel_id,m.number,coalesce(ch.name,m.channel_id) name from channel_map m "
                           "left join channels ch on ch.id=m.channel_id order by name collate nocase")
        finally:
            c.close()

    return J(await asyncio.to_thread(q))


async def api_channelmap_set(request):
    b = await request.json()
    num = str(b.get("number") or "").strip()
    if not b.get("channel_id") or not NUM_RX.match(num):
        return JE(ERR("err_number_digits"))

    def s():
        c = store.conn()
        c.execute("insert or replace into channel_map values(?,?)", (b["channel_id"], num))
        c.commit()
        c.close()

    await asyncio.to_thread(s)
    return J({"ok": True})


async def api_channelmap_del(request):
    cid = request.query.get("channel_id", "")

    def d():
        c = store.conn()
        c.execute("delete from channel_map where channel_id=?", (cid,))
        c.commit()
        c.close()

    await asyncio.to_thread(d)
    return J({"ok": True})


async def api_play(request):
    b = await request.json()
    d = await asyncio.to_thread(engine.load_defaults_sync)
    ents = [str(x) for x in (b.get("targets") or d.get("play_entities") or [])]
    if not ents:
        return J({"ok": False, "errors": ["err_pick_player"]})
    err = await engine.do_play_logged(ents, str(b.get("channel_id") or ""), b.get("fmt") or d.get("play_fmt"),
                                      b.get("content_type") or d.get("play_ctype"))
    return J({"ok": not err, "errors": [err] if err else []})


async def api_tune_now(request):
    b = await request.json()
    d = await asyncio.to_thread(engine.load_defaults_sync)
    cmap = await asyncio.to_thread(lambda: (lambda c: (engine.get_cmap(c), c.close())[0])(store.conn()))
    num = str(b.get("number") or "").strip() or cmap.get(b.get("channel_id") or "", "")
    entity = (b.get("entity") or "").strip() or d.get("tune_entity") or ""
    if not NUM_RX.match(num):
        return J({"ok": False, "errors": ["err_need_number"]})
    if not entity:
        return J({"ok": False, "errors": ["err_pick_remote"]})
    if b.get("remember") and b.get("channel_id"):
        def s():
            c = store.conn()
            c.execute("insert or replace into channel_map values(?,?)", (b["channel_id"], num))
            c.commit()
            c.close()

        await asyncio.to_thread(s)
    err = await engine.do_tune(entity, num, b.get("name") or f"#{num}", engine.T("manual_tune"), 0, d)
    return J({"ok": not err, "errors": [err] if err else []})


@web.middleware
async def errors(request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception as e:
        log.exception("API error")
        return J({"error": "err_internal", "detail": scrub(e)}, 500)


async def on_start(app):
    store.init()
    state.load_cfg()
    conf = await ha.config()
    state.STATE["tz"] = conf.get("time_zone") or os.environ.get("TZ") or "UTC"
    saved = await asyncio.to_thread(engine.setting_get_sync, "lang", None)
    state.STATE["lang"] = saved if saved in LANGS else (state.CFG.get("language") if state.CFG.get("language") in LANGS else "sv")
    app["tasks"] = [asyncio.create_task(scheduler_loop()), asyncio.create_task(refresh_loop()),
                    asyncio.create_task(ha.ws_listen(engine.handle_action_event))]


async def on_stop(app):
    for t in app["tasks"]:
        t.cancel()


def make_app():
    app = web.Application(middlewares=[errors], client_max_size=2**20)
    app.add_routes([
        web.get("/", index),
        web.get("/epg-cards.js", cards_js),
        web.get("/stream/seg", stream.segment),
        web.get("/stream/{cid}.m3u8", stream.playlist),
        web.post("/api/play", api_play),
        web.get("/hls.min.js", hls_js),
        web.get("/api/status", api_status),
        web.get("/api/categories", api_categories),
        web.get("/api/search", api_search),
        web.get("/api/grid", api_grid),
        web.get("/api/targets", api_targets),
        web.get("/api/entities", api_entities),
        web.get("/api/schedule", api_schedule),
        web.get("/api/reminders", api_reminders),
        web.post("/api/reminders", api_reminder_add),
        web.put("/api/reminders/{id}", api_reminder_update),
        web.delete("/api/reminders/{id}", api_reminder_del),
        web.post("/api/reminders/{id}/toggle", api_reminder_toggle),
        web.delete("/api/snoozes/{id}", api_snooze_del),
        web.get("/api/saved", api_saved),
        web.post("/api/saved", api_saved_add),
        web.delete("/api/saved/{id}", api_saved_del),
        web.get("/api/settings", api_settings),
        web.post("/api/settings", api_settings_set),
        web.post("/api/lang", api_lang),
        web.get("/api/favorites", api_favorites),
        web.post("/api/favorites", api_favorites_set),
        web.get("/api/history", api_history),
        web.get("/api/channelmap", api_channelmap),
        web.post("/api/channelmap", api_channelmap_set),
        web.delete("/api/channelmap", api_channelmap_del),
        web.post("/api/refresh", api_refresh),
        web.post("/api/test", api_test),
        web.post("/api/test_action", api_test_action),
        web.post("/api/tune_now", api_tune_now),
    ])
    app.on_startup.append(on_start)
    app.on_cleanup.append(on_stop)
    return app


if __name__ == "__main__":
    web.run_app(make_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8099")), print=None)
