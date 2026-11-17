"""Motorn: förekomster, schemaläggning, åtgärder, notiser, snooze och sensorer."""
import asyncio
import json
import logging
import secrets
import time
import zlib
from datetime import datetime, timedelta, timezone

import ha
import state
import store
import stream
import tpl
from i18n import tr
from util import compile_query, scrub

log = logging.getLogger("engine")
AUDIBLE = ("tts", "sound", "play")
_LAST_PUB = {"ts": 0}


def T(key, **kw):
    return tr(state.lang(), key, **kw)


# ------------------------------------------------------------------ hjälp
def _j(v, default):
    try:
        return json.loads(v) if v else default
    except Exception:
        return default


def rem_dict(r):
    d = dict(r)
    d["targets"] = _j(d.get("targets"), [])
    d["days"] = _j(d.get("days"), None)
    d["actions"] = _j(d.get("actions"), [])
    d["opts"] = _j(d.get("opts"), {})
    d["enabled"] = bool(d.get("enabled"))
    d["in_descr"] = bool(d.get("in_descr"))
    d["tune"] = bool(d.get("tune"))
    return d


def get_cmap(c):
    return {r["channel_id"]: r["number"] for r in c.execute("select channel_id,number from channel_map")}


def load_defaults_sync():
    c = store.conn()
    try:
        return store.load_defaults(c, state.CFG)
    finally:
        c.close()


def hist_sync(label, ntype, targets, ok, err=""):
    c = store.conn()
    try:
        store.add_history(c, label, ntype, targets, ok, err)
    finally:
        c.close()


async def hist(label, ntype, targets, ok, err=""):
    await asyncio.to_thread(hist_sync, label, ntype, targets, ok, err)


def setting_set_sync(k, v):
    c = store.conn()
    try:
        store.set_setting(c, k, v)
    finally:
        c.close()


def setting_get_sync(k, default=None):
    c = store.conn()
    try:
        return store.get_setting(c, k, default)
    finally:
        c.close()


# ------------------------------------------------------------------ tidspåminnelser
def _occurrence(rem, now):
    """Aktuell förekomst (epoch, nyckel, slut) för en tidspåminnelse, annars None."""
    if not rem["days"]:
        if rem["start"] <= now < rem["start"] + 900:
            return rem["start"], f"t:{rem['start']}", rem["start"] + 900
        return None
    try:
        hh, mm = map(int, (rem["at_time"] or "0:0").split(":"))
    except ValueError:
        return None
    dt = datetime.fromtimestamp(now, state.tz()).replace(hour=hh, minute=mm, second=0, microsecond=0)
    fire = int(dt.timestamp())
    if dt.weekday() in rem["days"] and fire <= now < fire + 300:
        return fire, f"t:{dt:%Y-%m-%d}", fire + 300
    return None


def next_fire(rem, now, fired):
    if not rem["days"]:
        if rem["start"] + 900 > now and (rem["id"], f"t:{rem['start']}|notify") not in fired:
            return rem["start"]
        return None
    try:
        hh, mm = map(int, (rem["at_time"] or "0:0").split(":"))
    except ValueError:
        return None
    base = datetime.fromtimestamp(now, state.tz())
    for add in range(0, 8):
        dt = (base + timedelta(days=add)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        fire = int(dt.timestamp())
        if dt.weekday() in rem["days"] and (
                fire > now or (fire + 300 > now and (rem["id"], f"t:{dt:%Y-%m-%d}|notify") not in fired)):
            return fire
    return None


# ------------------------------------------------------------------ förekomster
def occurrences(c, rem, now):
    out = []
    if rem["kind"] == "program":
        if now < (rem["stop"] or 0):
            ch = c.execute("select name,icon from channels where id=?", (rem["channel_id"],)).fetchone()
            out.append({"key": "p", "channel_id": rem["channel_id"], "cname": (ch["name"] if ch else None) or rem["channel_id"],
                        "icon": ch["icon"] if ch else None, "title": rem["title"], "start": rem["start"],
                        "stop": rem["stop"], "descr": "", "category": ""})
    elif rem["kind"] == "rule":
        chq = compile_query(rem["channel_pattern"] or "")
        q = compile_query(rem["pattern"] or "")
        if not chq and not q:
            return out
        for p in c.execute(
                "select p.channel_id,p.start,p.stop,p.title,p.descr,p.category,c.name cname,c.icon from programs p "
                "left join channels c on c.id=p.channel_id where p.stop>? and p.start<=?",
                (now, now + rem["lead"] * 60)):
            if chq and not chq(p["cname"] or p["channel_id"]):
                continue
            if q and not q(p["title"], p["descr"] if rem["in_descr"] else None, (p["cname"], p["category"])):
                continue
            out.append({"key": f"{p['channel_id']}:{p['start']}", "channel_id": p["channel_id"],
                        "cname": p["cname"] or p["channel_id"], "icon": p["icon"], "title": p["title"],
                        "start": p["start"], "stop": p["stop"], "descr": p["descr"] or "", "category": p["category"] or ""})
    elif rem["kind"] == "time":
        occ = _occurrence(rem, now)
        if occ:
            fire, key, end = occ
            ch = c.execute("select name,icon from channels where id=?", (rem["channel_id"],)).fetchone() if rem["channel_id"] else None
            out.append({"key": key, "channel_id": rem["channel_id"], "cname": (ch["name"] if ch else None) or "",
                        "icon": ch["icon"] if ch else None, "title": rem["label"] or T("default_label"),
                        "start": fire, "stop": end, "descr": "", "category": ""})
    return out


def stage_plan(rem):
    acts = rem["actions"]
    if rem["kind"] == "time":
        work = rem["ntype"] != "none" or bool(acts) or rem["tune"]
        return ["notify"] if work else []
    plan = []
    if (rem["ntype"] != "none" or any(a.get("when", "notify") == "notify" for a in acts)
            or (rem["tune"] and rem["tune_when"] == "notify")):
        plan.append("notify")
    if any(a.get("when") == "start" for a in acts) or (rem["tune"] and rem["tune_when"] == "start"):
        plan.append("start")
    return plan


def due_jobs(now):
    c = store.conn()
    jobs = []
    try:
        c.execute("delete from reminders where kind='program' and stop<?", (now - 86400,))
        c.execute("delete from reminders where kind='time' and days is null and start<?", (now - 86400,))
        c.execute("delete from fired where ts<?", (now - 30 * 86400,))
        c.execute("delete from ctxs where created<?", (now - 2 * 86400,))
        fired = {(r["reminder_id"], r["key"]) for r in c.execute("select reminder_id,key from fired")}
        for r in c.execute("select * from reminders where enabled=1 and scope='live'"):
            rem = rem_dict(r)
            plan = stage_plan(rem)
            if not plan:
                continue
            for occ in occurrences(c, rem, now):
                for stage in plan:
                    if rem["kind"] == "time":
                        t, end = occ["start"], occ["stop"]
                    elif stage == "notify":
                        t, end = occ["start"] - rem["lead"] * 60, occ["stop"]
                    else:
                        t, end = occ["start"], occ["start"] + 180
                    key = f"{occ['key']}|{stage}"
                    if t <= now < end and (rem["id"], key) not in fired:
                        jobs.append({"rem": rem, "occ": occ, "stage": stage, "key": key})
        for j in jobs:
            c.execute("insert or ignore into fired values(?,?,?)", (j["rem"]["id"], j["key"], now))
        c.commit()
        return jobs
    finally:
        c.close()


# ------------------------------------------------------------------ schema (för UI och sensorer)
def schedule_sync(limit=80, horizon_days=7):
    now = int(time.time())
    c = store.conn()
    try:
        fired = {(r["reminder_id"], r["key"]) for r in c.execute("select reminder_id,key from fired")}
        cmap = get_cmap(c)
        out = []

        def row(rem, via, channel_id, cname, icon, title, start, stop, fire_at):
            num = (rem["tune_number"] or cmap.get(channel_id)) if rem["tune"] else None
            return {"reminder_id": rem["id"], "via": via, "kind": rem["kind"], "label": rem["label"],
                    "channel_id": channel_id, "channel": cname, "icon": icon, "title": title, "start": start,
                    "stop": stop, "fire_at": fire_at, "lead": rem["lead"], "ntype": rem["ntype"],
                    "targets": rem["targets"], "tune": rem["tune"], "tune_number": num,
                    "tune_when": rem["tune_when"], "tune_entity": rem["tune_entity"],
                    "n_actions": len(rem["actions"]), "days": rem["days"], "at_time": rem["at_time"]}

        for r in c.execute("select * from reminders where enabled=1 and scope='live'"):
            rem = rem_dict(r)
            if rem["kind"] == "program":
                if rem["stop"] > now and (rem["id"], "p|notify") not in fired:
                    ch = c.execute("select name,icon from channels where id=?", (rem["channel_id"],)).fetchone()
                    out.append(row(rem, "program", rem["channel_id"], (ch["name"] if ch else None) or rem["channel_id"],
                                   ch["icon"] if ch else None, rem["title"], rem["start"], rem["stop"],
                                   rem["start"] - rem["lead"] * 60))
            elif rem["kind"] == "rule":
                chq = compile_query(rem["channel_pattern"] or "")
                q = compile_query(rem["pattern"] or "")
                if not chq and not q:
                    continue
                n = 0
                for p in c.execute(
                        "select p.channel_id,p.start,p.stop,p.title,p.descr,p.category,c.name cname,c.icon from programs p "
                        "left join channels c on c.id=p.channel_id where p.stop>? and p.start<? order by p.start",
                        (now, now + horizon_days * 86400)):
                    if (rem["id"], f"{p['channel_id']}:{p['start']}|notify") in fired:
                        continue
                    if chq and not chq(p["cname"] or p["channel_id"]):
                        continue
                    if q and not q(p["title"], p["descr"] if rem["in_descr"] else None, (p["cname"], p["category"])):
                        continue
                    out.append(row(rem, "rule", p["channel_id"], p["cname"] or p["channel_id"], p["icon"], p["title"],
                                   p["start"], p["stop"], p["start"] - rem["lead"] * 60))
                    n += 1
                    if n >= 25:
                        break
            elif rem["kind"] == "time":
                fa = next_fire(rem, now, fired)
                if fa is None:
                    continue
                ch = c.execute("select name,icon from channels where id=?", (rem["channel_id"],)).fetchone() if rem["channel_id"] else None
                num = (rem["tune_number"] or cmap.get(rem["channel_id"])) if rem["tune"] else None
                cname = (ch["name"] if ch else None) or (f"#{num}" if num else "")
                out.append(row(rem, "time", rem["channel_id"], cname, ch["icon"] if ch else None,
                               rem["label"] or T("default_label"), fa, fa, fa))
        for s in c.execute("select * from snoozes order by fire_at"):
            ctx = _j(s["ctx"], {})
            o = ctx.get("occ", {})
            out.append({"reminder_id": s["rem_id"], "via": "snooze", "kind": "snooze", "label": "", "channel_id": o.get("channel_id"),
                        "channel": o.get("cname"), "icon": o.get("icon"), "title": o.get("title"), "start": o.get("start"),
                        "stop": o.get("stop"), "fire_at": s["fire_at"], "lead": 0, "ntype": "push", "targets": [],
                        "tune": False, "tune_number": None, "tune_when": "start", "tune_entity": None,
                        "n_actions": 0, "days": None, "at_time": None, "snooze_id": s["id"]})
        out.sort(key=lambda x: x["fire_at"])
        return out[:limit]
    finally:
        c.close()


# ------------------------------------------------------------------ villkor
def quiet_now(d, now):
    if not d.get("quiet_enabled"):
        return False
    try:
        fh, fm = map(int, d["quiet_from"].split(":"))
        th, tm = map(int, d["quiet_to"].split(":"))
    except Exception:
        return False
    dt = datetime.fromtimestamp(now, state.tz())
    cur, a, b = dt.hour * 60 + dt.minute, fh * 60 + fm, th * 60 + tm
    return (a <= cur < b) if a <= b else (cur >= a or cur < b)


async def anyone_home(d):
    ents = d.get("home_entities") or []
    if not ents:
        return True
    for e in ents:
        st = await ha.get_state(e)
        if st and st.get("state") == "home":
            return True
    return False


# ------------------------------------------------------------------ kontext
def build_ctx(rem, occ, now, cmap):
    z = state.tz()
    st = datetime.fromtimestamp(occ["start"], z)
    number = rem["tune_number"] or cmap.get(occ["channel_id"]) or ""
    minutes = max(0, round((occ["start"] - now) / 60))
    ctx = {
        "title": occ["title"] or "", "channel": occ["cname"] or "", "number": number,
        "start": st.strftime("%H:%M"), "end": datetime.fromtimestamp(occ["stop"], z).strftime("%H:%M") if occ.get("stop") else "",
        "date": st.strftime("%Y-%m-%d"), "time": datetime.fromtimestamp(now, z).strftime("%H:%M"),
        "minutes": str(minutes), "label": rem["label"] or T("default_label"), "lead": str(rem["lead"]),
        "description": (occ.get("descr") or "")[:200], "category": occ.get("category") or "", "reminder_id": str(rem["id"]),
        "channel_id": occ.get("channel_id") or "",
    }
    if rem["kind"] == "time":
        s = T("time_status", time=ctx["start"])
        if occ["cname"]:
            s += T("time_channel", channel=occ["cname"])
        if rem["tune"] and number:
            s += T("time_tune", number=number)
    elif now >= occ["start"]:
        s = T("status_running", channel=ctx["channel"], start=ctx["start"])
    elif minutes <= 0:
        s = T("status_now", channel=ctx["channel"], start=ctx["start"])
    else:
        s = T("status_future", minutes=minutes, channel=ctx["channel"], start=ctx["start"])
    if not ctx["channel"] and number:
        ctx["channel"] = f"#{number}"
    ctx["status"] = s
    return ctx


async def render(text, ctx):
    return await tpl.render(text, ctx, ha.get_state)


# ------------------------------------------------------------------ primär notis
def _save_ctx(token, rem_id, payload):
    c = store.conn()
    try:
        c.execute("insert or replace into ctxs values(?,?,?,?)", (token, rem_id, json.dumps(payload), int(time.time())))
        c.commit()
    finally:
        c.close()


async def send_primary(rem, occ, ctx, now, d, prefix="", default_title=None, default_msg=None):
    opts = rem["opts"]
    default_title = default_title or ("⏰ {label}" if rem["kind"] == "time" else "📺 {title}")
    title = prefix + await render(opts.get("title_tpl") or default_title, ctx)
    message = await render(opts.get("msg_tpl") or default_msg or "{status}", ctx)
    buttons = None
    if rem["ntype"] == "push" and opts.get("buttons"):
        token = secrets.token_hex(4)
        entity = rem["tune_entity"] or d.get("tune_entity")
        _save_ctx(token, rem["id"], {"occ": occ, "ctx": ctx, "entity": entity})
        n = int(opts.get("snooze_min") or d.get("snooze_min") or 10)
        buttons = [{"action": f"EPG|snooze|{n}|{token}", "title": T("snooze_btn", n=n)}]
        if ctx["number"] and entity:
            buttons.append({"action": f"EPG|tune|0|{token}", "title": T("tune_btn", number=ctx["number"])})
        if ctx.get("channel_id") and d.get("play_entities"):
            buttons.append({"action": f"EPG|play|0|{token}", "title": T("play_btn")})
    tag = f"epg_{rem['id']}_{occ['start']}_{zlib.crc32((occ['cname'] or '').encode()) % 100000}"
    errs = await ha.send(rem["ntype"], rem["targets"], title, message, tag=tag, image=occ.get("icon"),
                         tts_entity=d.get("tts_entity") or "", language=d.get("tts_language") or state.lang(),
                         buttons=buttons)
    await hist(f"{title} – {message}", rem["ntype"], rem["targets"], not errs, "; ".join(errs))
    if errs:
        log.warning("Notisfel: %s", errs)
    return title, message


async def fire_reminder_event(rem, ctx, title, message):
    data = {**ctx, "title": ctx["title"], "message": message, "notification_title": title, "reminder_id": rem["id"]}
    await ha.fire_event("iptv_epg_reminder", data)
    await asyncio.to_thread(setting_set_sync, "last_trigger", {
        "ts": int(time.time()), "title": ctx["title"], "message": message, "channel": ctx["channel"],
        "number": ctx["number"], "reminder_id": rem["id"], "label": rem["label"] or ""})


# ------------------------------------------------------------------ åtgärder
def _on(v: str) -> bool:
    return str(v).strip().lower() in ("on", "true", "1", "yes", "ja", "på", "pa")


async def _volume(act, targets):
    vol = act.get("volume")
    if vol in (None, ""):
        return
    for mp in targets:
        try:
            await ha.call("media_player", "volume_set", {"entity_id": mp, "volume_level": max(0, min(100, float(vol))) / 100})
        except Exception as e:
            log.warning("volym: %s", scrub(e))


async def run_action(act, ctx, d):
    """Utför en åtgärd. Returnerar en kort beskrivning, kastar vid fel."""
    t = act["type"]
    if t == "tts":
        text = await render(act.get("text", ""), ctx)
        ent = act.get("tts_entity") or d.get("tts_entity")
        if not ent:
            lst = (await ha.targets()).get("tts_entities") or []
            ent = lst[0]["id"] if lst else ""
        if not ent:
            raise RuntimeError("No tts entity (set one under Settings or in the action)")
        targets = act.get("targets") or []
        await _volume(act, targets)
        await ha.call("tts", "speak", {"entity_id": ent, "media_player_entity_id": targets, "message": text,
                                      "language": act.get("language") or d.get("tts_language") or state.lang()})
        return text
    if t == "sound":
        value = (await render(act.get("value", ""), ctx)).strip()
        if act.get("source", "file") == "file" and not value.startswith(("/", "http", "media-source://")):
            value = f"media-source://media_source/local/{value}"
        targets = act.get("targets") or []
        await _volume(act, targets)
        for mp in targets:
            await ha.call("media_player", "play_media", {"entity_id": mp, "media_content_id": value,
                                                          "media_content_type": act.get("content_type") or "music"})
        return value
    if t == "play":
        targets = act.get("targets") or []
        cid = (act.get("channel_id") or "").strip() or ctx.get("channel_id") or ""
        if not cid and ctx.get("number"):          # tidspåminnelse: slå upp kanalen via kanalnumret
            _, cmap = await asyncio.to_thread(_ctx_data)
            cid = next((k for k, v in cmap.items() if str(v) == str(ctx["number"])), "")
        await _volume(act, targets)
        return await do_play(targets, cid, act.get("fmt") or d.get("play_fmt") or "hls",
                             act.get("content_type") or d.get("play_ctype") or "auto")
    if t == "service":
        domain, svc = act["service"].strip().split(".", 1)
        data = await tpl.render_json(json.loads(act.get("data") or "{}"), ctx, ha.get_state)
        await ha.call(domain, svc, data)
        return act["service"]
    if t == "set_entity":
        ent = act["entity_id"].strip()
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
        else:
            await ha.set_state(ent, v, {"friendly_name": ent, "source": "EPG reminders"})
        return f"{ent} = {v}"
    raise RuntimeError(f"Unknown action {t}")


async def do_play_vod(entities, kind, vid, ext, ctype, label):
    if not entities:
        raise RuntimeError("No media player chosen")
    url, ext = await asyncio.to_thread(stream.resolve_vod, kind, vid, ext, state.CFG)
    if not url:
        raise RuntimeError("Movies/series require an Xtream source")
    for mp in entities:
        await ha.call("media_player", "play_media", {
            "entity_id": mp, "media_content_id": url,
            "media_content_type": stream.content_type_vod(mp, ext, ctype)})
    return label


async def do_play(entities, cid, fmt, ctype):
    """Spelar en kanal på mediaspelare. Kastar vid fel. Returnerar kanalnamnet (aldrig adressen)."""
    if not cid:
        raise RuntimeError("No channel to play")
    if not entities:
        raise RuntimeError("No media player chosen")
    fmt = "ts" if fmt == "ts" else "hls"
    url, name = await asyncio.to_thread(stream.resolve, cid, fmt, state.CFG)
    if not url:
        raise RuntimeError(f"No stream for this channel ({name or cid}) – requires an Xtream or M3U source")
    for mp in entities:
        await ha.call("media_player", "play_media", {
            "entity_id": mp, "media_content_id": url,
            "media_content_type": stream.content_type(mp, fmt, ctype), "extra": {"stream_type": "LIVE"}})
    return name


async def do_play_logged(entities, cid, fmt, ctype, vod=None):
    err = ""
    name = cid
    try:
        if vod:
            name = await do_play_vod(entities, vod["kind"], vod["id"], vod.get("ext", ""), ctype, vod.get("name") or vod["id"])
        else:
            name = await do_play(entities, cid, fmt, ctype)
    except Exception as e:
        err = scrub(e)
    await hist(f"{T('a_play')}: {name}", "play", entities, not err, err)
    return err


async def run_action_logged(act, ctx, rem, d, quiet, home_ok):
    t = act["type"]
    what = T("a_" + t)
    if t in AUDIBLE and quiet:
        await hist(T("hist_skip_quiet", what=what), t, [], True)
        return
    if t in AUDIBLE and not home_ok:
        await hist(T("hist_skip_home", what=what), t, [], True)
        return
    try:
        detail = await run_action(act, ctx, d)
        await hist(f"{what}: {detail}", t, act.get("targets") or [], True)
    except Exception as e:
        log.warning("Åtgärd %s misslyckades: %s", t, scrub(e))
        await hist(f"{what}", t, act.get("targets") or [], False, scrub(e))


async def do_tune(entity, number, cname, title, rem_id, d):
    err = ""
    cname = cname or f"#{number}"
    try:
        await ha.tune(entity, number, float(d.get("tune_delay") or 0.4), (d.get("tune_suffix") or "").strip())
    except Exception as e:
        err = scrub(e)
        log.warning("Kanalbyte misslyckades: %s", err)
    await ha.fire_event("iptv_epg_tune", {"entity_id": entity, "channel_number": number, "channel": cname,
                                          "program": title, "reminder_id": rem_id})
    await hist(T("hist_tune", number=number, channel=cname, title=title), "tune", [entity], not err, err)
    await asyncio.to_thread(setting_set_sync, "last_tune", {"ts": int(time.time()), "number": number, "channel": cname,
                                                            "entity": entity, "title": title})
    return err


async def run_tune(rem, occ, ctx, d, home_ok):
    number, entity = ctx["number"], rem["tune_entity"] or d.get("tune_entity")
    title = ctx["title"]
    if not home_ok:
        await hist(T("hist_skip_home", what=T("a_tune")), "tune", [], True)
        return
    if not entity or not number:
        await hist(T("hist_tune_skip", title=title), "tune", [], False,
                   T("missing_entity") if not entity else T("missing_number"))
        return
    pre = rem["opts"].get("pre") or {}
    if pre.get("entity"):
        try:
            await ha.call("homeassistant", "turn_on", {"entity_id": pre["entity"]})
            await hist(f"{T('a_pre')}: {pre['entity']}", "pre", [pre["entity"]], True)
            await asyncio.sleep(max(0, min(float(pre.get("wait") or 0), 60)))
        except Exception as e:
            await hist(T("a_pre"), "pre", [pre["entity"]], False, scrub(e))
    await do_tune(entity, number, occ["cname"] or f"#{number}", title, rem["id"], d)


# ------------------------------------------------------------------ jobb
def _ctx_data(rem_id=None):
    c = store.conn()
    try:
        return store.load_defaults(c, state.CFG), get_cmap(c)
    finally:
        c.close()


async def run_job(job):
    rem, occ, stage = job["rem"], job["occ"], job["stage"]
    now = int(time.time())
    d, cmap = await asyncio.to_thread(_ctx_data)
    ctx = build_ctx(rem, occ, now, cmap)
    opts = rem["opts"]
    quiet = quiet_now(d, now) and not opts.get("ignore_quiet")
    home_ok = True
    if opts.get("only_home"):
        home_ok = await anyone_home(d)
    if stage == "notify":
        if rem["ntype"] != "none":
            title, message = await send_primary(rem, occ, ctx, now, d)
        else:
            title, message = ctx["title"], ctx["status"]
        await fire_reminder_event(rem, ctx, title, message)
    for act in rem["actions"]:
        when = "notify" if rem["kind"] == "time" else act.get("when", "notify")
        if when == stage:
            await run_action_logged(act, ctx, rem, d, quiet, home_ok)
    tune_stage = "notify" if rem["kind"] == "time" else rem["tune_when"]
    if rem["tune"] and tune_stage == stage:
        await run_tune(rem, occ, ctx, d, home_ok)
    asyncio.create_task(publish_sensors())


# ------------------------------------------------------------------ snooze + knappar
def due_snoozes(now):
    c = store.conn()
    try:
        rows = [dict(r) for r in c.execute("select * from snoozes where fire_at<=?", (now,))]
        for r in rows:
            c.execute("delete from snoozes where id=?", (r["id"],))
        c.commit()
        out = []
        for r in rows:
            rr = c.execute("select * from reminders where id=? and enabled=1", (r["rem_id"],)).fetchone()
            if rr:
                out.append((rem_dict(rr), _j(r["ctx"], {})))
        return out
    finally:
        c.close()


async def run_snooze(item):
    rem, payload = item
    now = int(time.time())
    d, cmap = await asyncio.to_thread(_ctx_data)
    occ = payload.get("occ") or {}
    ctx = build_ctx(rem, occ, now, cmap)
    await send_primary(rem, occ, ctx, now, d, prefix="💤 ")


def _load_token(token):
    c = store.conn()
    try:
        r = c.execute("select * from ctxs where token=?", (token,)).fetchone()
        if not r:
            return None
        rem = c.execute("select * from reminders where id=?", (r["rem_id"],)).fetchone()
        return (rem_dict(rem) if rem else None), _j(r["ctx"], {})
    finally:
        c.close()


def _add_snooze(rem_id, payload, minutes):
    c = store.conn()
    try:
        c.execute("insert into snoozes(fire_at,rem_id,ctx) values(?,?,?)",
                  (int(time.time()) + minutes * 60, rem_id, json.dumps(payload)))
        c.commit()
    finally:
        c.close()


async def handle_action_event(ev):
    if ev.get("event_type") == "iptv_epg_play":
        return await handle_play_event(ev)
    data = ev.get("data") or {}
    action = data.get("action") or data.get("actionName") or ""
    if not str(action).startswith("EPG|"):
        return
    parts = action.split("|")
    if len(parts) < 4:
        return
    kind, arg, token = parts[1], parts[2], parts[3]
    loaded = await asyncio.to_thread(_load_token, token)
    if not loaded or not loaded[0]:
        return
    rem, payload = loaded
    if kind == "snooze":
        minutes = max(1, min(int(arg or 10), 240))
        await asyncio.to_thread(_add_snooze, rem["id"], payload, minutes)
        await hist(f"💤 {payload.get('ctx', {}).get('title', '')} +{minutes} min", "snooze", [], True)
    elif kind == "tune":
        d, _ = await asyncio.to_thread(_ctx_data)
        ctx = payload.get("ctx", {})
        entity = payload.get("entity") or d.get("tune_entity")
        if entity and ctx.get("number"):
            await do_tune(entity, ctx["number"], ctx.get("channel", ""), ctx.get("title", ""), rem["id"], d)
    elif kind == "play":
        d, _ = await asyncio.to_thread(_ctx_data)
        cid = (payload.get("ctx") or {}).get("channel_id")
        if cid and d.get("play_entities"):
            await do_play_logged(d["play_entities"], cid, d.get("play_fmt"), d.get("play_ctype"))
    asyncio.create_task(publish_sensors())


async def handle_play_event(ev):
    """Event iptv_epg_play från t.ex. dashboardkort: {channel_id|number, entity_id|entity_ids, fmt}."""
    data = ev.get("data") or {}
    d, cmap = await asyncio.to_thread(_ctx_data)
    cid = str(data.get("channel_id") or "")
    if not cid and data.get("number"):
        cid = next((k for k, v in cmap.items() if str(v) == str(data["number"])), "")
    ents = data.get("entity_ids") or data.get("entity_id") or d.get("play_entities") or []
    if isinstance(ents, str):
        ents = [ents]
    await do_play_logged([str(x) for x in ents], cid, data.get("fmt") or d.get("play_fmt"), data.get("content_type") or d.get("play_ctype"))


# ------------------------------------------------------------------ sensorer
async def publish_sensors():
    try:
        sched = await asyncio.to_thread(schedule_sync, 50)
        last = await asyncio.to_thread(setting_get_sync, "last_trigger", None)
        last_tune = await asyncio.to_thread(setting_get_sync, "last_tune", None)
        count = await asyncio.to_thread(_count_active)
        now = int(time.time())
        iso = lambda ts: datetime.fromtimestamp(ts, timezone.utc).isoformat()
        nxt = sched[0] if sched else None
        await ha.set_state("sensor.epg_next_reminder", iso(nxt["fire_at"]) if nxt else "unknown", {
            "friendly_name": T("sensor_next"), "icon": "mdi:bell-ring", "device_class": "timestamp",
            "title": nxt["title"] if nxt else None, "channel": nxt["channel"] if nxt else None,
            "start": iso(nxt["start"]) if nxt and nxt["start"] else None,
            "minutes_until": max(0, round((nxt["fire_at"] - now) / 60)) if nxt else None,
            "channel_number": nxt["tune_number"] if nxt else None, "reminder_id": nxt["reminder_id"] if nxt else None,
            "upcoming": [{"title": s["title"], "channel": s["channel"], "fire_at": iso(s["fire_at"]),
                          "start": iso(s["start"]) if s["start"] else None, "channel_number": s["tune_number"],
                          "reminder_id": s["reminder_id"]} for s in sched[:12]]})
        await ha.set_state("sensor.epg_last_triggered", iso(last["ts"]) if last else "unknown", {
            "friendly_name": T("sensor_last"), "icon": "mdi:history", "device_class": "timestamp",
            **({k: last[k] for k in ("title", "message", "channel", "number", "reminder_id", "label")} if last else {})})
        await ha.set_state("sensor.epg_active_reminders", count, {
            "friendly_name": T("sensor_count"), "icon": "mdi:format-list-checks", "unit_of_measurement": "st" if state.lang() == "sv" else "pcs",
            "scheduled_next_7_days": len(sched), **(await asyncio.to_thread(_tune_cfg))})
        nowch = await asyncio.to_thread(_now_on_channels, now)
        await ha.set_state("sensor.epg_now_on_favorites", len(nowch), {
            "friendly_name": T("sensor_now"), "icon": "mdi:television-guide", "channels": nowch})
        await ha.set_state("sensor.epg_last_channel_change", last_tune["number"] if last_tune else "unknown", {
            "friendly_name": T("sensor_tune"), "icon": "mdi:television-classic",
            **({"channel": last_tune["channel"], "entity_id": last_tune["entity"], "program": last_tune["title"],
                "changed_at": iso(last_tune["ts"])} if last_tune else {})})
        _LAST_PUB["ts"] = time.time()
    except Exception as e:
        log.warning("sensorer: %s", scrub(e))


def _tune_cfg():
    d, _ = _ctx_data()
    return {"tune_entity": d.get("tune_entity") or "", "tune_delay": float(d.get("tune_delay") or 0.4),
            "tune_suffix": (d.get("tune_suffix") or "").strip()}


def _now_on_channels(now, limit=12):
    """Vad som går just nu (och nästa program) på favoritkanaler – annars kanaler med sparat nummer."""
    c = store.conn()
    try:
        cmap = get_cmap(c)
        ids = [r["channel_id"] for r in c.execute("select channel_id from favorites")]
        if not ids:
            ids = list(cmap)
        out = []
        for cid in ids:
            ch = c.execute("select name from channels where id=?", (cid,)).fetchone()
            if not ch:
                continue
            cur = c.execute("select title,start,stop from programs where channel_id=? and start<=? and stop>? order by start desc limit 1",
                            (cid, now, now)).fetchone()
            nxt = c.execute("select title,start from programs where channel_id=? and start>? order by start limit 1",
                            (cid, now)).fetchone()
            out.append({"id": cid, "channel": ch["name"] or cid, "number": cmap.get(cid),
                        "title": cur["title"] if cur else None, "start": cur["start"] if cur else None,
                        "stop": cur["stop"] if cur else None,
                        "next_title": nxt["title"] if nxt else None, "next_start": nxt["start"] if nxt else None})
            if len(out) >= limit:
                break
        return out
    finally:
        c.close()


def _count_active():
    c = store.conn()
    try:
        return c.execute("select count(*) from reminders where enabled=1").fetchone()[0]
    finally:
        c.close()


# ------------------------------------------------------------------ tick
async def tick():
    now = int(time.time())
    jobs = await asyncio.to_thread(due_jobs, now)
    snoozed = await asyncio.to_thread(due_snoozes, now)
    tasks = [run_job(j) for j in jobs] + [run_snooze(s) for s in snoozed]
    if tasks:
        for r in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(r, Exception):
                log.error("jobb misslyckades: %s", scrub(r))
    if time.time() - _LAST_PUB["ts"] >= 60:
        await publish_sensors()


# ------------------------------------------------------------------ nya titlar (serier/filmer)
async def new_titles_alert(new: dict):
    def rules(kind):
        c = store.conn()
        try:
            return [rem_dict(r) for r in c.execute(
                "select * from reminders where kind='rule' and enabled=1 and scope=?", (kind,))]
        finally:
            c.close()

    d, cmap = await asyncio.to_thread(_ctx_data)
    now = int(time.time())
    for kind, names in new.items():
        for rem in await asyncio.to_thread(rules, kind):
            q = compile_query(rem["pattern"] or "")
            if not q:
                continue
            hits = [n for n in names if q(n)]
            if not hits:
                continue
            key = "movie" if kind == "movie" else "series"
            title = (T(f"new_{key}_one", name=hits[0]) if len(hits) == 1 else T(f"new_{key}_many", n=len(hits)))
            occ = {"key": "new", "channel_id": "", "cname": "", "icon": None, "title": hits[0], "start": now, "stop": now,
                   "descr": "", "category": ""}
            ctx = build_ctx(rem, occ, now, cmap)
            ctx["status"] = ", ".join(hits[:8])
            ctx["title"] = hits[0]
            await send_primary(rem, occ, ctx, now, d, default_title=title, default_msg="{status}")
            await ha.fire_event("iptv_epg_new_titles", {"kind": kind, "titles": hits[:50], "reminder_id": rem["id"]})
            for act in rem["actions"]:
                await run_action_logged(act, ctx, rem, d, quiet_now(d, now) and not rem["opts"].get("ignore_quiet"), True)
