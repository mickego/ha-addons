"""Schemaläggare, notiser, kvittering/upprepning och sensorer för Påminnelser Pro."""
import asyncio
import heapq
import itertools
import json
import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

import ha
import recur
import state
import store
import tpl
from i18n import S, T

log = logging.getLogger("engine")

ALERT = ("push", "notify", "persistent", "tts", "sound")
ACTION_TYPES = ALERT + ("service", "set_entity", "event")
_LAST_PUB = {"ts": 0.0}
_PUB_LOCK = asyncio.Lock()


def now() -> int:
    return state.now()


def tzinfo():
    return state.tz()


class ApiError(Exception):
    def __init__(self, code, detail=None, status=400):
        super().__init__(code)
        self.code, self.detail, self.status = code, detail, status


# ------------------------------------------------------------------ rader <-> dict
def rem_dict(r):
    d = dict(r)
    d["rule"] = store.jl(d.get("rule"), {})
    d["actions"] = store.jl(d.get("actions"), [])
    d["opts"] = store.jl(d.get("opts"), {})
    return d


def defaults_sync():
    c = store.conn()
    try:
        return store.load_defaults(c, state.CFG)
    finally:
        c.close()


def setting_get_sync(k, default=None):
    c = store.conn()
    try:
        return store.get_setting(c, k, default)
    finally:
        c.close()


def setting_set_sync(k, v):
    c = store.conn()
    try:
        store.set_setting(c, k, v)
    finally:
        c.close()


def hist_sync(kind, title="", detail="", rem_id=None, occ_ts=None):
    c = store.conn()
    try:
        store.add_history(c, kind, title, detail, rem_id, occ_ts, ts=now())
        c.commit()
    finally:
        c.close()


async def hist(kind, title="", detail="", rem_id=None, occ_ts=None):
    await asyncio.to_thread(hist_sync, kind, title, detail, rem_id, occ_ts)


# ------------------------------------------------------------------ validering
def _json_text(v, code="err_json"):
    if v in (None, ""):
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    try:
        obj = json.loads(v)
    except Exception:
        raise ApiError(code)
    if not isinstance(obj, (dict, list)):
        raise ApiError(code)
    return str(v).strip()


def _strs(v):
    return [str(x).strip() for x in (v or []) if str(x).strip()]


def clean_actions(lst):
    out = []
    for a in lst or []:
        t = a.get("type")
        if t not in ACTION_TYPES:
            raise ApiError("err_action_type", t)
        x = {"type": t, "enabled": bool(a.get("enabled", True))}
        if "repeat" in a and t in ALERT:
            x["repeat"] = bool(a["repeat"])
        if t in ("push", "notify"):
            x["targets"] = _strs(a.get("targets"))
            x["title"] = str(a.get("title") or "").strip()
            x["message"] = str(a.get("message") or "").strip()
            if t == "notify":
                x["data"] = _json_text(a.get("data"))
        elif t == "persistent":
            x["title"] = str(a.get("title") or "").strip()
            x["message"] = str(a.get("message") or "").strip()
        elif t == "tts":
            x.update(targets=_strs(a.get("targets")), text=str(a.get("text") or "").strip(),
                     tts_entity=str(a.get("tts_entity") or "").strip(), language=str(a.get("language") or "").strip())
            if a.get("volume") not in (None, ""):
                x["volume"] = max(0, min(100, int(a["volume"])))
        elif t == "sound":
            x.update(targets=_strs(a.get("targets")), source="url" if a.get("source") == "url" else "file",
                     value=str(a.get("value") or "").strip(), content_type=str(a.get("content_type") or "music").strip())
            if a.get("volume") not in (None, ""):
                x["volume"] = max(0, min(100, int(a["volume"])))
        elif t == "service":
            svc = str(a.get("service") or "").strip()
            if not re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", svc):
                raise ApiError("err_service", svc)
            x.update(service=svc, data=_json_text(a.get("data")))
        elif t == "set_entity":
            ent = str(a.get("entity_id") or "").strip()
            if not re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", ent):
                raise ApiError("err_entity", ent)
            x.update(entity_id=ent, value=str(a.get("value") if a.get("value") is not None else ""))
        elif t == "event":
            ev = str(a.get("event") or "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_]+", ev):
                raise ApiError("err_event", ev)
            x.update(event=ev, data=_json_text(a.get("data")))
        out.append(x)
    return out


def clean_opts(o):
    o = o or {}
    r = o.get("repeat") or {}
    out = {
        "repeat": {"enabled": bool(r.get("enabled")),
                   "every_min": max(1, min(int(r.get("every_min") or 5), 1440)),
                   "max": max(1, min(int(r.get("max") or 12), 1000))},
        "buttons": bool(o.get("buttons", True)),
        "ignore_quiet": bool(o.get("ignore_quiet")),
        "only_home": bool(o.get("only_home")),
        "urgent": bool(o.get("urgent")),
        "auto_delete": bool(o.get("auto_delete")),
        "duration_min": max(1, min(int(o.get("duration_min") or 15), 1440)),
        "url": str(o.get("url") or "").strip(),
    }
    for k, lo, hi in (("snooze_min", 1, 1440), ("grace_min", 0, 10080)):
        if o.get(k) not in (None, ""):
            out[k] = max(lo, min(int(o[k]), hi))
    return out


def build_fields(b, existing=None):
    """Validerar ett API-objekt till kolumnvärden."""
    title = str(b.get("title") or "").strip()
    if not title:
        raise ApiError("err_title")
    try:
        rule = recur.normalize(b.get("rule") or {})
    except recur.RuleError as e:
        raise ApiError(str(e.args[0]))
    rule = {k: v for k, v in rule.items() if k != "_n"}
    actions = clean_actions(b.get("actions"))
    opts = clean_opts(b.get("opts"))
    cat = b.get("category_id")
    return {
        "title": title[:200], "note": str(b.get("note") or "")[:2000],
        "category_id": int(cat) if cat not in (None, "", 0, "0") else None,
        "rule": json.dumps(rule, ensure_ascii=False),
        "actions": json.dumps(actions, ensure_ascii=False),
        "opts": json.dumps(opts, ensure_ascii=False),
        "enabled": 0 if b.get("enabled") is False else 1,
    }, rule


def compute_next(rule, from_ts):
    return recur.next_after(rule, tzinfo(), from_ts, inclusive=True)


def insert_sync(b):
    f, rule = build_fields(b)
    t = now()
    nxt = compute_next(rule, t - 20) if f["enabled"] else None
    c = store.conn()
    try:
        cur = c.execute(
            "insert into reminders(title,note,category_id,rule,actions,opts,enabled,next_at,created,updated) "
            "values(?,?,?,?,?,?,?,?,?,?)",
            (f["title"], f["note"], f["category_id"], f["rule"], f["actions"], f["opts"], f["enabled"], nxt, t, t))
        c.commit()
        return cur.lastrowid
    finally:
        c.close()


def update_sync(rid, b):
    f, rule = build_fields(b)
    t = now()
    c = store.conn()
    try:
        old = c.execute("select * from reminders where id=?", (rid,)).fetchone()
        if not old:
            raise ApiError("err_not_found", status=404)
        enabled = f["enabled"]
        nxt = compute_next(rule, t - 20) if enabled else None
        paused = old["paused_until"]
        if "paused_until" in b:
            paused = None if b["paused_until"] in (None, "", 0) else int(b["paused_until"])
        c.execute("update reminders set title=?,note=?,category_id=?,rule=?,actions=?,opts=?,enabled=?,next_at=?,updated=?, "
                  "paused_until=? where id=?",
                  (f["title"], f["note"], f["category_id"], f["rule"], f["actions"], f["opts"], enabled, nxt, t, paused, rid))
        c.commit()
    finally:
        c.close()


def delete_sync(rid):
    c = store.conn()
    try:
        c.execute("delete from reminders where id=?", (rid,))
        c.execute("update pending set status='expired', closed=? where rem_id=? and status in ('open','snoozed','deferred')",
                  (now(), rid))
        c.commit()
    finally:
        c.close()


def toggle_sync(rid, enabled=None):
    c = store.conn()
    try:
        r = c.execute("select * from reminders where id=?", (rid,)).fetchone()
        if not r:
            raise ApiError("err_not_found", status=404)
        en = (0 if r["enabled"] else 1) if enabled is None else (1 if enabled else 0)
        nxt = compute_next(store.jl(r["rule"], {}), now() - 20) if en else None
        c.execute("update reminders set enabled=?, next_at=?, paused_until=null where id=?", (en, nxt, rid))
        c.commit()
        return en
    finally:
        c.close()


def pause_sync(rid, until_ts):
    """Pausar till given tidpunkt (0/None = ta bort pausen). Tillfällen under pausen hoppas över."""
    c = store.conn()
    try:
        r = c.execute("select * from reminders where id=?", (rid,)).fetchone()
        if not r:
            raise ApiError("err_not_found", status=404)
        c.execute("update reminders set paused_until=? where id=?", (int(until_ts) if until_ts else None, rid))
        c.commit()
    finally:
        c.close()


def skip_next_sync(rid):
    """Lägger nästa tillfälle som undantag (räknas inte mot 'antal gånger')."""
    c = store.conn()
    try:
        r = c.execute("select * from reminders where id=?", (rid,)).fetchone()
        if not r or not r["next_at"]:
            raise ApiError("err_not_found", status=404)
        rule = store.jl(r["rule"], {})
        key = datetime.fromtimestamp(r["next_at"], tzinfo()).strftime("%Y-%m-%dT%H:%M")
        rule["exdates"] = sorted(set(rule.get("exdates") or []) | {key})
        nxt = compute_next(rule, r["next_at"] + 1)
        c.execute("update reminders set rule=?, next_at=? where id=?", (json.dumps(rule), nxt, rid))
        store.add_history(c, "skip_next", r["title"], key, rid, r["next_at"], ts=now())
        c.commit()
        return key
    finally:
        c.close()


def duplicate_sync(rid):
    c = store.conn()
    try:
        r = c.execute("select * from reminders where id=?", (rid,)).fetchone()
        if not r:
            raise ApiError("err_not_found", status=404)
        d = rem_dict(r)
        d["title"] = d["title"] + " (2)"
    finally:
        c.close()
    return insert_sync(d)


# ------------------------------------------------------------------ kategorier
def categories_sync():
    c = store.conn()
    try:
        return [dict(r) for r in c.execute("select * from categories order by name collate nocase")]
    finally:
        c.close()


def category_save_sync(b):
    name = str(b.get("name") or "").strip()
    if not name:
        raise ApiError("err_name")
    color = str(b.get("color") or "#6c8cff")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ApiError("err_color")
    icon = str(b.get("icon") or "mdi:bell")[:60]
    c = store.conn()
    try:
        if b.get("id"):
            c.execute("update categories set name=?,color=?,icon=? where id=?", (name, color, icon, int(b["id"])))
            cid = int(b["id"])
        else:
            cid = c.execute("insert into categories(name,color,icon) values(?,?,?)", (name, color, icon)).lastrowid
        c.commit()
        return cid
    finally:
        c.close()


def category_delete_sync(cid):
    c = store.conn()
    try:
        c.execute("update reminders set category_id=null where category_id=?", (cid,))
        c.execute("delete from categories where id=?", (cid,))
        c.commit()
    finally:
        c.close()


# ------------------------------------------------------------------ vyer
def _cat_map(c):
    return {r["id"]: dict(r) for r in c.execute("select * from categories")}


def view(rem, cats, t, c=None):
    """Remindern som API-objekt med härledd status."""
    paused = bool(rem["paused_until"] and rem["paused_until"] > t)
    if not rem["enabled"]:
        st = "off"
    elif paused:
        st = "paused"
    elif rem["next_at"] is None:
        st = "ended"
    else:
        st = "active"
    cat = cats.get(rem["category_id"])
    out = {**{k: rem[k] for k in ("id", "title", "note", "category_id", "rule", "actions", "opts", "enabled",
                                  "paused_until", "next_at", "last_fired", "fired_count")},
           "status": st, "category": cat}
    if rem["rule"].get("count") and rem["next_at"]:
        try:
            out["remaining"] = recur.total_remaining(rem["rule"], tzinfo(), rem["next_at"])
        except Exception:
            out["remaining"] = None
    return out


def list_sync():
    c = store.conn()
    try:
        cats = _cat_map(c)
        t = now()
        rows = [rem_dict(r) for r in c.execute("select * from reminders order by id")]
        open_p = {r["rem_id"]: r["id"] for r in c.execute("select rem_id,id from pending where status in ('open','snoozed','deferred')")}
        out = []
        for r in rows:
            v = view(r, cats, t)
            v["pending_id"] = open_p.get(r["id"])
            out.append(v)
        return out
    finally:
        c.close()


def get_sync(rid):
    c = store.conn()
    try:
        r = c.execute("select * from reminders where id=?", (rid,)).fetchone()
        if not r:
            raise ApiError("err_not_found", status=404)
        return view(rem_dict(r), _cat_map(c), now())
    finally:
        c.close()


def preview_sync(rule, n=10, after=None):
    try:
        rl = recur.normalize(rule)
    except recur.RuleError as e:
        raise ApiError(str(e.args[0]))
    tz = tzinfo()
    t = now() if after is None else int(after)
    items = recur.preview(rl, tz, max(1, min(n, 50)), t)
    out = {"items": [{"ts": x, "local": datetime.fromtimestamp(x, tz).strftime("%Y-%m-%dT%H:%M"),
                      "weekday": datetime.fromtimestamp(x, tz).weekday()} for x in items]}
    if rl.get("count"):
        out["remaining"] = recur.total_remaining(rl, tz, t)
    return out


def _live(rem, t):
    """Från vilken tidpunkt gäller påminnelsen faktiskt (hänsyn till paus)?"""
    start = t
    if rem["paused_until"] and rem["paused_until"] > t:
        start = rem["paused_until"]
    return start


def upcoming_sync(t, limit=12, days=60, per=12):
    c = store.conn()
    try:
        cats = _cat_map(c)
        rows = [rem_dict(r) for r in c.execute("select * from reminders where enabled=1 and next_at is not null")]
    finally:
        c.close()
    tz = tzinfo()
    horizon = t + days * 86400

    def stream(r):
        gen = itertools.takewhile(lambda x: x <= horizon, itertools.islice(recur.iter_occurrences(r["rule"], tz, _live(r, t)), per))
        return ((ts, r["id"], r) for ts in gen)
    streams = [stream(r) for r in rows]
    out = []
    for ts, _, r in heapq.merge(*streams, key=lambda x: (x[0], x[1])):
        cat = cats.get(r["category_id"]) or {}
        out.append({"ts": ts, "rem_id": r["id"], "title": r["title"], "note": r["note"],
                    "category": cat.get("name"), "color": cat.get("color"), "icon": cat.get("icon")})
        if len(out) >= limit:
            break
    return out


def agenda_sync(days=14, limit=400):
    t = now()
    return upcoming_sync(t, limit=limit, days=days, per=60)


def events_between_sync(start, end, limit_per=300, limit=3000):
    c = store.conn()
    try:
        cats = _cat_map(c)
        rows = [rem_dict(r) for r in c.execute("select * from reminders where enabled=1")]
    finally:
        c.close()
    tz = tzinfo()
    out = []
    for r in rows:
        lo = max(start, r["paused_until"] or 0)
        cat = cats.get(r["category_id"]) or {}
        dur = int(r["opts"].get("duration_min") or 15) * 60
        for ts in recur.occurrences_between(r["rule"], tz, lo, end, limit_per):
            out.append({"uid": f"rp-{r['id']}-{ts}", "rem_id": r["id"], "title": r["title"], "description": r["note"],
                        "start": ts, "end": ts + dur, "category": cat.get("name"), "color": cat.get("color")})
            if len(out) >= limit:
                return sorted(out, key=lambda x: x["start"])
    return sorted(out, key=lambda x: x["start"])


def ics_sync(past_days=14, future_days=120):
    t = now()
    evs = events_between_sync(t - past_days * 86400, t + future_days * 86400)
    fmt = lambda ts: datetime.fromtimestamp(ts, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    esc = lambda s: str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Reminders Pro//HA//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Reminders Pro"]
    for e in evs:
        lines += ["BEGIN:VEVENT", f"UID:{e['uid']}@reminders_pro", f"DTSTAMP:{fmt(t)}", f"DTSTART:{fmt(e['start'])}",
                  f"DTEND:{fmt(e['end'])}", f"SUMMARY:{esc(e['title'])}"]
        if e["description"]:
            lines.append(f"DESCRIPTION:{esc(e['description'])}")
        if e["category"]:
            lines.append(f"CATEGORIES:{esc(e['category'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# ------------------------------------------------------------------ tysta timmar / hemma
def _quiet_bounds(d):
    try:
        fh, fm = map(int, d["quiet_from"].split(":"))
        th, tm = map(int, d["quiet_to"].split(":"))
    except Exception:
        return None
    return fh * 60 + fm, th * 60 + tm


def quiet_now(d, t):
    if not d.get("quiet_enabled"):
        return False
    b = _quiet_bounds(d)
    if not b or b[0] == b[1]:
        return False
    dt = datetime.fromtimestamp(t, tzinfo())
    cur, a, e = dt.hour * 60 + dt.minute, b[0], b[1]
    return (a <= cur < e) if a <= e else (cur >= a or cur < e)


def quiet_end_ts(d, t):
    """Nästa gång tysta timmar slutar (UTC)."""
    b = _quiet_bounds(d)
    dt = datetime.fromtimestamp(t, tzinfo())
    end = dt.replace(hour=b[1] // 60, minute=b[1] % 60, second=0, microsecond=0)
    if end <= dt:
        end += timedelta(days=1)
    return int(recur.to_ts(end.date(), b[1], tzinfo()))


async def anyone_home(d):
    ents = d.get("home_entities") or []
    if not ents:
        return True
    for e in ents:
        st = await ha.get_state(e)
        if st and st.get("state") == "home":
            return True
    return False


# ------------------------------------------------------------------ kontext och text
def build_ctx(snap, occ_ts, t, attempt=1):
    tz = tzinfo()
    dt = datetime.fromtimestamp(occ_ts, tz)
    names = S.get(state.lang(), S["en"])["wd"]
    ctx = {
        "title": snap["title"], "message": snap.get("note") or "", "category": snap.get("category") or "",
        "date": dt.strftime("%Y-%m-%d"), "time": dt.strftime("%H:%M"), "weekday": names[dt.weekday()],
        "id": str(snap.get("rem_id") or ""), "attempt": str(attempt),
        "now": datetime.fromtimestamp(t, tz).strftime("%H:%M"), "n": "", "remaining": "", "next": "",
    }
    blob = json.dumps([snap.get("title"), snap.get("note"), snap.get("actions")], ensure_ascii=False)
    if tpl.uses(blob, "n") or tpl.uses(blob, "remaining") or tpl.uses(blob, "next"):
        rule = snap.get("rule")
        if rule:
            try:
                if tpl.uses(blob, "n"):
                    ctx["n"] = str(recur.index_of(rule, tz, occ_ts) or "")
                nx = recur.next_after(rule, tz, occ_ts)
                if nx and tpl.uses(blob, "next"):
                    nd = datetime.fromtimestamp(nx, tz)
                    ctx["next"] = nd.strftime("%Y-%m-%d %H:%M")
                if tpl.uses(blob, "remaining") and rule.get("count"):
                    ctx["remaining"] = str(recur.total_remaining(rule, tz, occ_ts + 1))
            except Exception:
                log.exception("ctx")
    return ctx


async def render(text, ctx):
    return await tpl.render(text, ctx, ha.get_state)


# ------------------------------------------------------------------ åtgärder
def _on(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "on", "yes", "ja", "an", "oui", "päällä", "på")


async def _volume(act, targets):
    if act.get("volume") in (None, ""):
        return
    for mp in targets:
        try:
            await ha.call("media_player", "volume_set", {"entity_id": mp, "volume_level": int(act["volume"]) / 100})
        except Exception as e:
            log.warning("volym: %s", e)


def _buttons(token, d, opts):
    n = int(opts.get("snooze_min") or d.get("snooze_min") or 10)
    return [{"action": f"RP|done|{token}", "title": T("done")},
            {"action": f"RP|snooze|{n}|{token}", "title": T("snooze", n=n)},
            {"action": f"RP|skip|{token}", "title": T("skip")}]


async def run_action(act, snap, ctx, d, token=None, prefix="", needs_ack=False):
    """Utför en åtgärd. Returnerar kort beskrivning, kastar vid fel."""
    t = act["type"]
    opts = snap.get("opts") or {}
    tag = f"rp_{snap.get('rem_id') or 'x'}"
    if t in ("push", "notify", "persistent"):
        title = prefix + await render(act.get("title") or "{title}", ctx)
        msg = await render(act.get("message") or snap.get("note") or T("default_msg"), ctx)
        if t == "persistent":
            await ha.call("persistent_notification", "create", {"title": title, "message": msg, "notification_id": tag})
            return title
        targets = act.get("targets") or []
        if not targets:
            raise RuntimeError("No notification target selected")
        errs = []
        for tg in targets:
            svc = tg.split(".", 1)[1] if tg.startswith("notify.") else tg
            payload = {"title": title, "message": msg}
            if t == "push":
                data = {"tag": tag, "group": "reminders_pro", "ttl": 0, "priority": "high",
                        "channel": "Reminders Pro", "importance": "high"}
                if snap.get("color"):
                    data["color"] = snap["color"]
                if opts.get("url"):
                    data["clickAction"] = data["url"] = opts["url"]
                if opts.get("urgent"):
                    data["channel"] = "alarm_stream"
                    data["push"] = {"interruption-level": "critical", "sound": {"name": "default", "critical": 1, "volume": 1.0}}
                if token and opts.get("buttons", True):
                    data["actions"] = _buttons(token, d, opts)
                    data["sticky"] = "true"
                payload["data"] = data
            elif act.get("data"):
                extra = await tpl.render_json(json.loads(act["data"]), ctx, ha.get_state)
                if isinstance(extra, dict):
                    payload["data"] = extra
            try:
                await ha.call("notify", svc, payload)
            except Exception as e:
                errs.append(f"{tg}: {e}")
        if errs:
            raise RuntimeError("; ".join(errs))
        return title
    if t == "tts":
        text = await render(act.get("text") or "{title}. {message}", ctx)
        ent = act.get("tts_entity") or d.get("tts_entity")
        if not ent:
            lst = (await ha.targets()).get("tts_entities") or []
            ent = lst[0]["id"] if lst else ""
        if not ent:
            raise RuntimeError("No tts entity (set one under Settings or in the action)")
        targets = act.get("targets") or []
        if not targets:
            raise RuntimeError("No media player selected")
        await _volume(act, targets)
        await ha.call("tts", "speak", {"entity_id": ent, "media_player_entity_id": targets, "message": text,
                                      "language": act.get("language") or d.get("tts_language") or state.lang()})
        return text
    if t == "sound":
        value = (await render(act.get("value", ""), ctx)).strip()
        if not value:
            raise RuntimeError("No sound given")
        if act.get("source", "file") == "file" and not value.startswith(("/", "http", "media-source://")):
            value = f"media-source://media_source/local/{value}"
        targets = act.get("targets") or []
        if not targets:
            raise RuntimeError("No media player selected")
        await _volume(act, targets)
        for mp in targets:
            await ha.call("media_player", "play_media", {"entity_id": mp, "media_content_id": value,
                                                          "media_content_type": act.get("content_type") or "music"})
        return value
    if t == "service":
        domain, svc = act["service"].split(".", 1)
        data = await tpl.render_json(json.loads(act.get("data") or "{}"), ctx, ha.get_state)
        await ha.call(domain, svc, data if isinstance(data, dict) else {})
        return act["service"]
    if t == "set_entity":
        ent = act["entity_id"]
        v = await render(str(act.get("value", "")), ctx)
        dom = ent.split(".")[0]
        if dom in ("input_boolean", "switch", "light", "fan", "script", "scene", "automation", "siren", "humidifier"):
            await ha.call("homeassistant", "turn_on" if _on(v) else "turn_off", {"entity_id": ent})
        elif dom == "input_text":
            await ha.call("input_text", "set_value", {"entity_id": ent, "value": v})
        elif dom in ("input_number", "number"):
            await ha.call(dom, "set_value", {"entity_id": ent, "value": float(v)})
        elif dom in ("input_select", "select"):
            await ha.call(dom, "select_option", {"entity_id": ent, "option": v})
        elif dom == "input_datetime":
            await ha.call("input_datetime", "set_datetime", {"entity_id": ent, "datetime": v})
        else:
            await ha.set_state(ent, v, {"friendly_name": ent, "source": "Reminders Pro"})
        return f"{ent} = {v}"
    if t == "event":
        data = await tpl.render_json(json.loads(act.get("data") or "{}"), ctx, ha.get_state)
        await ha.fire_event(act["event"], data if isinstance(data, dict) else {})
        return act["event"]
    raise RuntimeError(f"Unknown action {t}")


async def run_actions(snap, ctx, d, *, token=None, prefix="", needs_ack=False, only_alerts=False):
    """Kör alla aktiva åtgärder. Returnerar (antal_ok, fel)."""
    ok, errs = 0, []
    for act in snap.get("actions") or []:
        if not act.get("enabled", True):
            continue
        if only_alerts and (act["type"] not in ALERT or act.get("repeat") is False):
            continue
        try:
            await run_action(act, snap, ctx, d, token=token, prefix=prefix, needs_ack=needs_ack)
            ok += 1
        except Exception as e:
            errs.append(f"{act['type']}: {e}")
            log.warning("åtgärd %s: %s", act["type"], e)
    return ok, errs


# ------------------------------------------------------------------ utlösning
def _snapshot(rem, cats):
    cat = cats.get(rem["category_id"]) or {}
    return {"rem_id": rem["id"], "title": rem["title"], "note": rem["note"], "category": cat.get("name"),
            "color": cat.get("color"), "actions": rem["actions"], "opts": rem["opts"], "rule": rem["rule"]}


def _needs_ack(snap):
    o = snap.get("opts") or {}
    has_push = any(a["type"] == "push" and a.get("enabled", True) for a in snap.get("actions") or [])
    return bool(o.get("repeat", {}).get("enabled") or (o.get("buttons", True) and has_push))


def _supersede_sync(rem_id):
    c = store.conn()
    try:
        c.execute("update pending set status='expired', closed=? where rem_id=? and status in ('open','snoozed','deferred')",
                  (now(), rem_id))
        c.commit()
    finally:
        c.close()


def _new_pending_sync(snap, occ_ts, status, due_at, d):
    o = snap["opts"]
    rep = o.get("repeat") or {}
    token = secrets.token_hex(4)
    t = now()
    c = store.conn()
    try:
        c.execute("insert into pending(rem_id,occ_ts,token,status,due_at,sent,repeat_every,repeat_max,snapshot,created) "
                  "values(?,?,?,?,?,?,?,?,?,?)",
                  (snap["rem_id"], occ_ts, token, status, due_at, 0,
                   int(rep.get("every_min") or d["repeat_every_min"]) if rep.get("enabled") else 0,
                   int(rep.get("max") or d["repeat_max"]) if rep.get("enabled") else 0,
                   json.dumps(snap, ensure_ascii=False), t))
        c.commit()
        return token
    finally:
        c.close()


def _mark_sent_sync(token, due_at):
    c = store.conn()
    try:
        c.execute("update pending set status='open', sent=sent+1, due_at=? where token=?", (due_at, token))
        c.commit()
        r = c.execute("select sent from pending where token=?", (token,)).fetchone()
        return r["sent"] if r else 1
    finally:
        c.close()


async def deliver(snap, occ_ts, d, token=None, attempt=1, via="schedule", resend=False):
    """Skickar notiser/åtgärder. resend=True (upprepning/snooze) kör bara notisdelen."""
    t = now()
    needs_ack = _needs_ack(snap) and token is not None
    ctx = build_ctx(snap, occ_ts, t, attempt)
    prefix = "💤 " if via == "snooze" else ("🔁 " if resend else "")
    ok, errs = await run_actions(snap, ctx, d, token=token if needs_ack else None, prefix=prefix,
                                 needs_ack=needs_ack, only_alerts=resend)
    if not resend:
        await ha.fire_event("reminders_pro_fired", {**ctx, "reminder_id": snap.get("rem_id"), "via": via, "token": token or ""})
    kind = "error" if errs and not ok else ("repeat" if resend else "fired")
    await hist(kind, snap["title"], "; ".join(errs) if errs else (f"x{attempt}" if resend else via), snap.get("rem_id"), occ_ts)
    return ok, errs


async def fire(rem, occ_ts, via="schedule"):
    """Utlöser en påminnelse (planerad, uppskjuten eller test)."""
    d = await asyncio.to_thread(defaults_sync)
    t = now()
    cats = {c["id"]: c for c in await asyncio.to_thread(categories_sync)}
    snap = _snapshot(rem, cats)
    opts = snap["opts"]
    if via == "schedule":
        if not opts.get("ignore_quiet") and quiet_now(d, t):
            if d.get("quiet_mode") == "skip":
                await hist("quiet_skip", rem["title"], "", rem["id"], occ_ts)
                return
            await asyncio.to_thread(_supersede_sync, rem["id"])
            await asyncio.to_thread(_new_pending_sync, snap, occ_ts, "deferred", quiet_end_ts(d, t), d)
            await hist("quiet_delay", rem["title"], "", rem["id"], occ_ts)
            return
        if opts.get("only_home") and not await anyone_home(d):
            await hist("home_skip", rem["title"], "", rem["id"], occ_ts)
            return
    await asyncio.to_thread(_supersede_sync, rem["id"]) if via != "test" else None
    token = None
    if _needs_ack(snap):
        rep = opts.get("repeat") or {}
        due = t + int(rep.get("every_min") or d["repeat_every_min"]) * 60 if rep.get("enabled") and via != "test" else None
        token = await asyncio.to_thread(_new_pending_sync, snap, occ_ts, "open", due, d)
        await asyncio.to_thread(_mark_sent_sync, token, due)
    ok, errs = await deliver(snap, occ_ts, d, token=token, attempt=1, via=via)
    if via != "test":
        await asyncio.to_thread(_after_fire_sync, rem["id"], t, opts.get("auto_delete") and rem["rule"].get("freq") == "once")
    asyncio.create_task(publish_sensors())


def _after_fire_sync(rem_id, t, delete):
    c = store.conn()
    try:
        c.execute("update reminders set last_fired=?, fired_count=fired_count+1 where id=?", (t, rem_id))
        if delete:
            c.execute("delete from reminders where id=?", (rem_id,))
        c.commit()
    finally:
        c.close()


async def process_due(rem, t):
    """Hanterar förfallna tillfällen för en påminnelse: skicka senaste, hoppa över för gamla."""
    d = await asyncio.to_thread(defaults_sync)
    grace = int(rem["opts"].get("grace_min", d["grace_min"])) * 60
    paused = bool(rem["paused_until"] and rem["paused_until"] > t)
    tz = tzinfo()
    due, missed, nxt, n = [], 0, None, 0
    for occ in recur.iter_occurrences(rem["rule"], tz, rem["next_at"]):
        if occ > t:
            nxt = occ
            break
        n += 1
        if n > 5000:
            nxt = recur.next_after(rem["rule"], tz, t)
            missed += 1
            break
        if not paused and t - occ <= grace:
            due.append(occ)
        elif not paused:
            missed += 1
    await asyncio.to_thread(_set_next_sync, rem["id"], nxt)
    if missed:
        await hist("missed", rem["title"], str(missed), rem["id"])
    if len(due) > 1:
        await hist("merged", rem["title"], str(len(due) - 1), rem["id"])
    if due:
        await fire(rem, due[-1], "schedule")


def _set_next_sync(rid, nxt):
    c = store.conn()
    try:
        c.execute("update reminders set next_at=? where id=?", (nxt, rid))
        c.commit()
    finally:
        c.close()


def due_reminders_sync(t):
    c = store.conn()
    try:
        return [rem_dict(r) for r in c.execute(
            "select * from reminders where enabled=1 and next_at is not null and next_at<=?", (t,))]
    finally:
        c.close()


# ------------------------------------------------------------------ kvittering / upprepning
def _pending_row(c, key):
    if isinstance(key, int) or str(key).isdigit():
        return c.execute("select * from pending where id=?", (int(key),)).fetchone()
    return c.execute("select * from pending where token=?", (str(key),)).fetchone()


def _close_pending_sync(token, status):
    c = store.conn()
    try:
        c.execute("update pending set status=?, closed=?, due_at=null where token=?", (status, now(), token))
        c.commit()
    finally:
        c.close()


async def _clear_notifications(snap):
    tag = f"rp_{snap.get('rem_id') or 'x'}"
    for act in snap.get("actions") or []:
        if act["type"] == "push":
            for tg in act.get("targets") or []:
                await ha.clear_mobile(tg, tag)
        elif act["type"] == "persistent":
            try:
                await ha.call("persistent_notification", "dismiss", {"notification_id": tag})
            except Exception:
                pass


async def ack(key, kind, minutes=None, source="ui"):
    """kind: done | skip | snooze. Returnerar True om något ändrades."""
    def load():
        c = store.conn()
        try:
            r = _pending_row(c, key)
            return dict(r) if r else None
        finally:
            c.close()
    p = await asyncio.to_thread(load)
    if not p or p["status"] not in ("open", "snoozed", "deferred"):
        return False
    snap = store.jl(p["snapshot"], {})
    t = now()

    def upd():
        c = store.conn()
        try:
            if kind == "snooze":
                d = store.load_defaults(c, state.CFG)
                m = max(1, min(int(minutes or snap.get("opts", {}).get("snooze_min") or d["snooze_min"]), 1440))
                c.execute("update pending set status='snoozed', due_at=?, sent=0 where id=?", (t + m * 60, p["id"]))
                store.add_history(c, "snoozed", snap.get("title", ""), f"{m} min", p["rem_id"], p["occ_ts"], ts=t)
                c.commit()
                return m
            st = "done" if kind == "done" else "skipped"
            c.execute("update pending set status=?, closed=?, due_at=null where id=?", (st, t, p["id"]))
            store.add_history(c, st, snap.get("title", ""), source, p["rem_id"], p["occ_ts"], ts=t)
            c.commit()
            return 0
        finally:
            c.close()
    m = await asyncio.to_thread(upd)
    await _clear_notifications(snap)
    await ha.fire_event("reminders_pro_" + ("snoozed" if kind == "snooze" else "done" if kind == "done" else "skipped"),
                        {"reminder_id": p["rem_id"], "title": snap.get("title", ""), "token": p["token"], "minutes": m,
                         "source": source})
    asyncio.create_task(publish_sensors())
    return True


async def run_pending_due(p, t):
    """Uppskjuten (tysta timmar), snoozad eller upprepad påminnelse som är dags att skicka."""
    snap = store.jl(p["snapshot"], {})
    d = await asyncio.to_thread(defaults_sync)
    opts = snap.get("opts") or {}
    st = p["status"]
    if st == "open" and p["repeat_max"] and p["sent"] >= p["repeat_max"]:
        await asyncio.to_thread(_close_pending_sync, p["token"], "expired")
        await hist("unacked", snap.get("title", ""), f"{p['sent']}x", p["rem_id"], p["occ_ts"])
        await ha.fire_event("reminders_pro_unacknowledged",
                            {"reminder_id": p["rem_id"], "title": snap.get("title", ""), "sent": p["sent"]})
        asyncio.create_task(publish_sensors())
        return
    if st == "deferred" and not opts.get("ignore_quiet") and quiet_now(d, t):
        await asyncio.to_thread(_postpone_sync, p["token"], quiet_end_ts(d, t))
        return
    due = t + p["repeat_every"] * 60 if p["repeat_every"] else None
    sent = await asyncio.to_thread(_mark_sent_sync, p["token"], due)
    if st == "deferred":
        await deliver(snap, p["occ_ts"], d, token=p["token"], attempt=1, via="deferred")
        await asyncio.to_thread(_after_fire_sync, p["rem_id"], t, False)
    else:
        await deliver(snap, p["occ_ts"], d, token=p["token"], attempt=sent, via="snooze" if st == "snoozed" else "repeat",
                      resend=True)
    asyncio.create_task(publish_sensors())


def _postpone_sync(token, due):
    c = store.conn()
    try:
        c.execute("update pending set due_at=? where token=?", (due, token))
        c.commit()
    finally:
        c.close()


def due_pending_sync(t):
    c = store.conn()
    try:
        c.execute("update pending set status='expired', closed=?, due_at=null where status='open' and repeat_every=0 and created<?",
                  (t, t - 24 * 3600))
        c.commit()
        return [dict(r) for r in c.execute(
            "select * from pending where status in ('deferred','snoozed','open') and due_at is not null and due_at<=?", (t,))]
    finally:
        c.close()


# ------------------------------------------------------------------ snabbpåminnelse, test
def quick_sync(b):
    """Skapar en engångspåminnelse (event/dashboardkort). b: title, message, minutes|at, targets, repeat."""
    tz = tzinfo()
    t = now()
    title = str(b.get("title") or "").strip() or T("untitled")
    if b.get("at"):
        at = str(b["at"]).replace(" ", "T")
        start = at[:16]
    else:
        m = max(1, min(int(b.get("minutes") or b.get("in_minutes") or 10), 525600))
        dt = datetime.fromtimestamp(t + m * 60, tz)
        if dt.second:
            dt = dt.replace(second=0) + timedelta(minutes=1)
        start = dt.strftime("%Y-%m-%dT%H:%M")
    d = defaults_sync()
    targets = _strs(b.get("targets")) or d.get("default_targets") or []
    body = {"title": title, "note": str(b.get("message") or ""), "rule": {"freq": "once", "start": start},
            "actions": [{"type": "push", "targets": targets}] if targets else [{"type": "persistent"}],
            "opts": {"auto_delete": True, "repeat": b.get("repeat") or {}, "buttons": True}}
    return insert_sync(body)


async def test_fire(rid):
    def load():
        c = store.conn()
        try:
            r = c.execute("select * from reminders where id=?", (rid,)).fetchone()
            return rem_dict(r) if r else None
        finally:
            c.close()
    rem = await asyncio.to_thread(load)
    if not rem:
        raise ApiError("err_not_found", status=404)
    await fire(rem, now(), via="test")


def sample_snapshot():
    return {"rem_id": 0, "title": T("test_title"), "note": T("test_msg"), "category": "", "color": None, "opts": {}, "actions": []}


async def test_action(act):
    cl = clean_actions([act])[0]
    d = await asyncio.to_thread(defaults_sync)
    snap = sample_snapshot()
    if cl["type"] == "tts" and not cl.get("text"):
        cl["text"] = T("test_tts")
    ctx = build_ctx(snap, now(), now())
    return await run_action(cl, snap, ctx, d)


# ------------------------------------------------------------------ händelser från HA
async def handle_event(ev):
    et = ev.get("event_type")
    data = ev.get("data") or {}
    if et == "reminders_pro_command":
        return await handle_command(data)
    action = str(data.get("action") or data.get("actionName") or "")
    if not action.startswith("RP|"):
        return
    parts = action.split("|")
    kind = parts[1] if len(parts) > 1 else ""
    token = parts[-1]
    if kind == "snooze" and len(parts) >= 4:
        await ack(token, "snooze", int(parts[2] or 0) or None, source="push")
    elif kind in ("done", "skip"):
        await ack(token, kind, source="push")


async def handle_command(data):
    cmd = str(data.get("cmd") or data.get("action") or "")
    key = data.get("token") or data.get("pending_id")
    if cmd in ("done", "skip", "snooze") and key:
        await ack(key, cmd, data.get("minutes"), source="command")
    elif cmd == "quick":
        await asyncio.to_thread(quick_sync, data)
        asyncio.create_task(publish_sensors())
    elif cmd in ("trigger", "test") and data.get("id"):
        await test_fire(int(data["id"]))
    elif cmd in ("pause", "resume", "enable", "disable") and data.get("id"):
        rid = int(data["id"])
        if cmd == "pause":
            days = float(data.get("days") or 1)
            await asyncio.to_thread(pause_sync, rid, now() + int(days * 86400))
        elif cmd == "resume":
            await asyncio.to_thread(pause_sync, rid, None)
        else:
            await asyncio.to_thread(toggle_sync, rid, cmd == "enable")
        asyncio.create_task(publish_sensors())


# ------------------------------------------------------------------ sensorer
def pending_list_sync():
    c = store.conn()
    try:
        out = []
        for r in c.execute("select * from pending where status in ('open','snoozed','deferred') order by occ_ts"):
            s = store.jl(r["snapshot"], {})
            out.append({"id": r["id"], "token": r["token"], "rem_id": r["rem_id"], "title": s.get("title", ""),
                        "message": s.get("note", ""), "color": s.get("color"), "occ_ts": r["occ_ts"], "status": r["status"],
                        "sent": r["sent"], "due_at": r["due_at"], "repeat_max": r["repeat_max"]})
        return out
    finally:
        c.close()


def today_sync(t):
    tz = tzinfo()
    dt = datetime.fromtimestamp(t, tz)
    d0 = int(recur.to_ts(dt.date(), 0, tz))
    d1 = int(recur.to_ts(dt.date() + timedelta(days=1), 0, tz)) - 1
    c = store.conn()
    try:
        cats = _cat_map(c)
        rows = [rem_dict(r) for r in c.execute("select * from reminders where enabled=1")]
        hist_rows = c.execute("select rem_id,occ_ts,kind from history where occ_ts between ? and ? and kind in "
                              "('fired','done','skipped','missed','quiet_skip','home_skip','error') order by id", (d0, d1)).fetchall()
    finally:
        c.close()
    st = {(h["rem_id"], h["occ_ts"]): h["kind"] for h in hist_rows}
    items = []
    for r in rows:
        cat = cats.get(r["category_id"]) or {}
        for ts in recur.occurrences_between(r["rule"], tz, d0, d1, 60):
            if r["paused_until"] and ts < r["paused_until"]:
                continue
            k = st.get((r["id"], ts))
            if k is None and ts <= t and ts < (r["created"] or 0):
                continue                      # före påminnelsen skapades: inte "missad"
            status = k or ("upcoming" if ts > t else "missed")
            items.append({"rem_id": r["id"], "title": r["title"], "ts": ts, "status": status,
                          "color": cat.get("color"), "category": cat.get("name")})
    items.sort(key=lambda x: (x["ts"], x["rem_id"]))
    return items


def counts_sync():
    c = store.conn()
    try:
        total = c.execute("select count(*) n from reminders").fetchone()["n"]
        active = c.execute("select count(*) n from reminders where enabled=1 and next_at is not null").fetchone()["n"]
        last = c.execute("select * from reminders where last_fired is not null order by last_fired desc limit 1").fetchone()
        return total, active, (dict(last) if last else None)
    finally:
        c.close()


async def publish_sensors():
    async with _PUB_LOCK:
        try:
            t = now()
            up = await asyncio.to_thread(upcoming_sync, t, 12)
            pend = await asyncio.to_thread(pending_list_sync)
            today = await asyncio.to_thread(today_sync, t)
            total, active, last = await asyncio.to_thread(counts_sync)
            iso = lambda ts: datetime.fromtimestamp(ts, timezone.utc).isoformat()
            tz = tzinfo()
            loc = lambda ts: datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M")
            nxt = up[0] if up else None
            await ha.set_state("sensor.reminders_pro_next", iso(nxt["ts"]) if nxt else "unknown", {
                "friendly_name": T("s_next"), "icon": "mdi:bell-ring", "device_class": "timestamp",
                "title": nxt["title"] if nxt else None, "message": nxt["note"] if nxt else None,
                "category": nxt["category"] if nxt else None, "color": nxt["color"] if nxt else None,
                "reminder_id": nxt["rem_id"] if nxt else None, "local": loc(nxt["ts"]) if nxt else None,
                "minutes_until": max(0, round((nxt["ts"] - t) / 60)) if nxt else None,
                "upcoming": [{"title": u["title"], "category": u["category"], "color": u["color"], "reminder_id": u["rem_id"],
                              "at": iso(u["ts"]), "local": loc(u["ts"])} for u in up]})
            remaining_today = sum(1 for x in today if x["status"] == "upcoming")
            await ha.set_state("sensor.reminders_pro_today", remaining_today, {
                "friendly_name": T("s_today"), "icon": "mdi:calendar-today", "unit_of_measurement": T("pcs"),
                "total": len(today), "done": sum(1 for x in today if x["status"] in ("done", "fired", "skipped")),
                "items": [{"title": x["title"], "time": datetime.fromtimestamp(x["ts"], tz).strftime("%H:%M"),
                           "status": x["status"], "color": x["color"], "reminder_id": x["rem_id"]} for x in today[:60]]})
            await ha.set_state("sensor.reminders_pro_active", active, {
                "friendly_name": T("s_active"), "icon": "mdi:format-list-checks", "unit_of_measurement": T("pcs"), "total": total})
            await ha.set_state("sensor.reminders_pro_unacknowledged", len(pend), {
                "friendly_name": T("s_unack"), "icon": "mdi:bell-alert", "unit_of_measurement": T("pcs"),
                "items": [{"id": p["id"], "token": p["token"], "title": p["title"], "message": p["message"], "color": p["color"],
                           "status": p["status"], "since": iso(p["occ_ts"]), "sent": p["sent"]} for p in pend[:20]]})
            await ha.set_state("binary_sensor.reminders_pro_attention", "on" if pend else "off", {
                "friendly_name": T("s_attn"), "icon": "mdi:bell-alert" if pend else "mdi:bell-check", "count": len(pend)})
            await ha.set_state("sensor.reminders_pro_last", iso(last["last_fired"]) if last else "unknown", {
                "friendly_name": T("s_last"), "icon": "mdi:history", "device_class": "timestamp",
                **({"title": last["title"], "reminder_id": last["id"]} if last else {})})
            _LAST_PUB["ts"] = time.time()
        except Exception as e:
            log.warning("sensorer: %s", e)


# ------------------------------------------------------------------ huvudloop
def cleanup_sync():
    d = defaults_sync()
    cut = now() - int(d.get("keep_history_days", 60)) * 86400
    c = store.conn()
    try:
        c.execute("delete from history where ts<?", (cut,))
        c.execute("delete from pending where status in ('done','skipped','expired') and closed<?", (cut,))
        c.commit()
    finally:
        c.close()


_LAST_CLEAN = {"ts": 0}


async def tick():
    t = now()
    for rem in await asyncio.to_thread(due_reminders_sync, t):
        try:
            await process_due(rem, t)
        except Exception:
            log.exception("process_due %s", rem.get("id"))
    for p in await asyncio.to_thread(due_pending_sync, t):
        try:
            await run_pending_due(p, t)
        except Exception:
            log.exception("pending %s", p.get("id"))
    if time.time() - _LAST_PUB["ts"] >= 60:
        await publish_sensors()
    if time.time() - _LAST_CLEAN["ts"] > 6 * 3600:
        _LAST_CLEAN["ts"] = time.time()
        await asyncio.to_thread(cleanup_sync)


# ------------------------------------------------------------------ export / import
def export_sync():
    c = store.conn()
    try:
        cats = _cat_map(c)
        rems = []
        for r in c.execute("select * from reminders order by id"):
            d = rem_dict(r)
            cat = cats.get(d["category_id"])
            rems.append({"title": d["title"], "note": d["note"], "category": cat["name"] if cat else None,
                         "rule": d["rule"], "actions": d["actions"], "opts": d["opts"], "enabled": bool(d["enabled"])})
        return {"format": "reminders_pro", "version": 1, "exported": datetime.now(timezone.utc).isoformat(),
                "categories": [{"name": v["name"], "color": v["color"], "icon": v["icon"]} for v in cats.values()],
                "reminders": rems, "settings": store.get_setting(c, "defaults", {})}
    finally:
        c.close()


def import_sync(data, mode="merge"):
    if not isinstance(data, dict) or data.get("format") != "reminders_pro":
        raise ApiError("err_import_format")
    # validera allt först så inget sparas halvvägs
    prepared = []
    for r in data.get("reminders") or []:
        build_fields(r)
        prepared.append(r)
    c = store.conn()
    try:
        if mode == "replace":
            c.execute("delete from reminders")
            c.execute("delete from categories")
            c.execute("delete from pending")
            c.commit()
        cat_ids = {r["name"]: r["id"] for r in c.execute("select id,name from categories")}
    finally:
        c.close()
    for cat in data.get("categories") or []:
        if cat.get("name") and cat["name"] not in cat_ids:
            cat_ids[cat["name"]] = category_save_sync(cat)
    n = 0
    for r in prepared:
        b = dict(r)
        b["category_id"] = cat_ids.get(r.get("category"))
        insert_sync(b)
        n += 1
    if data.get("settings") and mode == "replace":
        setting_set_sync("defaults", data["settings"])
    return n
