"""Påminnelser Pro – Home Assistant-add-on (ingress-panel + schemaläggare)."""
import asyncio
import ipaddress
import json
import logging
import os
import shutil
from datetime import datetime

from aiohttp import web

import engine
import ha
import installer
import recur
import state
import store
from engine import ApiError

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# Endast HA Core, Supervisor/ingress och den egna containern får anropa API:t (andra add-ons nekas).
ALLOWED = [ipaddress.ip_network(n) for n in ("172.30.32.0/24", "127.0.0.0/8", "::1/128")]


def J(data, status=200):
    return web.json_response(data, status=status, dumps=lambda o: json.dumps(o, ensure_ascii=False))


@web.middleware
async def guard(request, handler):
    if os.environ.get("RP_ALLOW_ALL") != "1":
        try:
            ip = ipaddress.ip_address(request.remote or "127.0.0.1")
        except ValueError:
            ip = None
        if ip is None or not any(ip in n for n in ALLOWED):
            return J({"error": "forbidden"}, 403)
    try:
        return await handler(request)
    except ApiError as e:
        return J({"error": e.code, "detail": e.detail}, e.status)
    except web.HTTPException:
        raise
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
        return J({"error": "err_bad_request", "detail": str(e)[:200]}, 400)
    except Exception as e:
        log.exception("API error")
        return J({"error": "err_internal", "detail": str(e)[:200]}, 500)


async def body(request):
    try:
        return await request.json()
    except Exception:
        raise ApiError("err_bad_request")


def rid_of(request):
    return int(request.match_info["id"])


def changed():
    """Efter ändring: räkna om sensorer direkt."""
    asyncio.create_task(engine.publish_sensors())


# ------------------------------------------------------------------ sidor
async def index(request):
    return web.FileResponse(os.path.join(WEB_DIR, "index.html"), headers={"Cache-Control": "no-store"})


async def cards_js(request):
    return web.FileResponse(os.path.join(WEB_DIR, "reminders-pro-cards.js"), headers={
        "Cache-Control": "no-store", "Content-Type": "text/javascript; charset=utf-8",
        "Content-Disposition": 'attachment; filename="reminders-pro-cards.js"'})


# ------------------------------------------------------------------ API
async def api_status(request):
    t = engine.now()
    total, active, _ = await asyncio.to_thread(engine.counts_sync)
    pend = await asyncio.to_thread(engine.pending_list_sync)
    return J({"version": state.VERSION, "tz": state.STATE["tz"], "lang": state.lang(), "now": t, "total": total,
              "active": active, "pending": len(pend), "ha_connected": bool(ha.TOKEN)})


async def api_reminders(request):
    return J(await asyncio.to_thread(engine.list_sync))


async def api_reminder_get(request):
    return J(await asyncio.to_thread(engine.get_sync, rid_of(request)))


async def api_reminder_add(request):
    rid = await asyncio.to_thread(engine.insert_sync, await body(request))
    changed()
    return J(await asyncio.to_thread(engine.get_sync, rid), 201)


async def api_reminder_update(request):
    rid = rid_of(request)
    await asyncio.to_thread(engine.update_sync, rid, await body(request))
    changed()
    return J(await asyncio.to_thread(engine.get_sync, rid))


async def api_reminder_del(request):
    await asyncio.to_thread(engine.delete_sync, rid_of(request))
    changed()
    return J({"ok": True})


async def api_reminder_toggle(request):
    en = await asyncio.to_thread(engine.toggle_sync, rid_of(request))
    changed()
    return J({"enabled": bool(en)})


async def api_reminder_pause(request):
    b = await body(request)
    until = b.get("until")
    if b.get("days"):
        until = engine.now() + int(float(b["days"]) * 86400)
    await asyncio.to_thread(engine.pause_sync, rid_of(request), until)
    changed()
    return J({"ok": True, "paused_until": until or None})


async def api_reminder_skip(request):
    key = await asyncio.to_thread(engine.skip_next_sync, rid_of(request))
    changed()
    return J({"skipped": key})


async def api_reminder_dup(request):
    rid = await asyncio.to_thread(engine.duplicate_sync, rid_of(request))
    changed()
    return J(await asyncio.to_thread(engine.get_sync, rid), 201)


async def api_reminder_test(request):
    await engine.test_fire(rid_of(request))
    return J({"ok": True})


async def api_test_action(request):
    try:
        res = await engine.test_action((await body(request)).get("action") or {})
        return J({"ok": True, "detail": str(res)[:200]})
    except ApiError:
        raise
    except Exception as e:
        return J({"ok": False, "detail": str(e)[:300]})


async def api_preview(request):
    b = await body(request)
    return J(await asyncio.to_thread(engine.preview_sync, b.get("rule") or {}, int(b.get("n") or 10), b.get("after")))


async def api_schedule(request):
    days = max(1, min(int(request.query.get("days", 14)), 120))
    return J(await asyncio.to_thread(engine.agenda_sync, days))


async def api_categories(request):
    return J(await asyncio.to_thread(engine.categories_sync))


async def api_category_save(request):
    cid = await asyncio.to_thread(engine.category_save_sync, await body(request))
    return J({"id": cid})


async def api_category_del(request):
    await asyncio.to_thread(engine.category_delete_sync, rid_of(request))
    return J({"ok": True})


async def api_pending(request):
    return J(await asyncio.to_thread(engine.pending_list_sync))


async def api_pending_act(request):
    kind = request.match_info["kind"]
    if kind not in ("done", "skip", "snooze"):
        raise ApiError("err_bad_request")
    b = await body(request) if request.can_read_body else {}
    ok = await engine.ack(rid_of(request), kind, b.get("minutes"), source="ui")
    return J({"ok": ok})


async def api_targets(request):
    return J(await ha.targets())


async def api_entities(request):
    return J(await ha.search_entities(request.query.get("q", "")))


async def api_settings(request):
    d = await asyncio.to_thread(engine.defaults_sync)
    return J(d)


async def api_settings_set(request):
    b = await body(request)
    cur = await asyncio.to_thread(engine.defaults_sync)
    new = dict(cur)
    for k in store.DEFAULTS:
        if k in b:
            new[k] = b[k]
    for k in ("snooze_min", "grace_min", "repeat_every_min", "repeat_max", "keep_history_days"):
        new[k] = max(0, int(new[k]))
    new["snooze_choices"] = sorted({max(1, int(x)) for x in new.get("snooze_choices") or [5, 10, 30, 60]})[:8]
    for k in ("quiet_from", "quiet_to"):
        recur._hm(new[k])
    new["quiet_mode"] = "skip" if new.get("quiet_mode") == "skip" else "delay"
    new["quiet_enabled"] = bool(new["quiet_enabled"])
    new["home_entities"] = [str(x) for x in new.get("home_entities") or []]
    new["default_targets"] = [str(x) for x in new.get("default_targets") or []]
    await asyncio.to_thread(engine.setting_set_sync, "defaults", new)
    return J(new)


async def api_lang(request):
    lg = (await body(request)).get("lang")
    if lg not in state.LANGS:
        raise ApiError("err_bad_request")
    state.STATE["lang"] = lg
    await asyncio.to_thread(engine.setting_set_sync, "lang", lg)
    changed()
    return J({"lang": lg})


async def api_history(request):
    def q():
        c = store.conn()
        try:
            lim = max(1, min(int(request.query.get("limit", 150)), 500))
            return [dict(r) for r in c.execute("select * from history order by id desc limit ?", (lim,))]
        finally:
            c.close()
    return J(await asyncio.to_thread(q))


async def api_history_clear(request):
    def q():
        c = store.conn()
        try:
            c.execute("delete from history")
            c.commit()
        finally:
            c.close()
    await asyncio.to_thread(q)
    return J({"ok": True})


async def api_export(request):
    data = await asyncio.to_thread(engine.export_sync)
    return web.Response(text=json.dumps(data, ensure_ascii=False, indent=1), content_type="application/json", headers={
        "Content-Disposition": 'attachment; filename="reminders-pro-export.json"'})


async def api_import(request):
    b = await body(request)
    n = await asyncio.to_thread(engine.import_sync, b.get("data"), "replace" if b.get("mode") == "replace" else "merge")
    changed()
    return J({"imported": n})


async def api_quick(request):
    rid = await asyncio.to_thread(engine.quick_sync, await body(request))
    changed()
    return J({"id": rid}, 201)


async def api_calendar(request):
    q = request.query
    t = engine.now()

    def parse(v, default):
        if not v:
            return default
        try:
            return int(float(v))
        except ValueError:
            return int(datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp())
    s, e = parse(q.get("start"), t - 86400), parse(q.get("end"), t + 30 * 86400)
    if e - s > 400 * 86400:
        e = s + 400 * 86400
    return J(await asyncio.to_thread(engine.events_between_sync, s, e))


async def api_ics(request):
    txt = await asyncio.to_thread(engine.ics_sync)
    return web.Response(text=txt, content_type="text/calendar", charset="utf-8")


async def api_integration(request):
    return J(await installer.status())


async def api_integration_zip(request):
    return web.Response(body=await installer.integration_zip(), content_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="reminders-pro-integration.zip"'})


async def api_integration_install(request):
    return J(await installer.install_all(force=True))


# ------------------------------------------------------------------ livscykel
async def scheduler_loop():
    while True:
        try:
            await engine.tick()
        except Exception:
            log.exception("scheduler")
        await asyncio.sleep(15)


async def on_start(app):
    store.init()
    state.load_cfg()
    conf = await ha.config()
    state.STATE["tz"] = conf.get("time_zone") or os.environ.get("TZ") or "UTC"
    saved = await asyncio.to_thread(engine.setting_get_sync, "lang", None)
    cfg_lang = state.CFG.get("language")
    state.STATE["lang"] = saved if saved in state.LANGS else (cfg_lang if cfg_lang in state.LANGS else "sv")
    app["tasks"] = [asyncio.create_task(scheduler_loop()),
                    asyncio.create_task(ha.ws_listen(engine.handle_event)),
                    asyncio.create_task(installer.install_all())]


async def on_stop(app):
    for t in app["tasks"]:
        t.cancel()


def make_app():
    app = web.Application(middlewares=[guard], client_max_size=4 * 2**20)
    app.add_routes([
        web.get("/", index),
        web.get("/reminders-pro-cards.js", cards_js),
        web.get("/calendar.ics", api_ics),
        web.get("/api/status", api_status),
        web.get("/api/reminders", api_reminders),
        web.post("/api/reminders", api_reminder_add),
        web.get("/api/reminders/{id}", api_reminder_get),
        web.put("/api/reminders/{id}", api_reminder_update),
        web.delete("/api/reminders/{id}", api_reminder_del),
        web.post("/api/reminders/{id}/toggle", api_reminder_toggle),
        web.post("/api/reminders/{id}/pause", api_reminder_pause),
        web.post("/api/reminders/{id}/skip_next", api_reminder_skip),
        web.post("/api/reminders/{id}/duplicate", api_reminder_dup),
        web.post("/api/reminders/{id}/test", api_reminder_test),
        web.post("/api/test_action", api_test_action),
        web.post("/api/preview", api_preview),
        web.get("/api/schedule", api_schedule),
        web.get("/api/categories", api_categories),
        web.post("/api/categories", api_category_save),
        web.delete("/api/categories/{id}", api_category_del),
        web.get("/api/pending", api_pending),
        web.post("/api/pending/{id}/{kind}", api_pending_act),
        web.get("/api/targets", api_targets),
        web.get("/api/entities", api_entities),
        web.get("/api/settings", api_settings),
        web.post("/api/settings", api_settings_set),
        web.post("/api/lang", api_lang),
        web.get("/api/history", api_history),
        web.delete("/api/history", api_history_clear),
        web.get("/api/export", api_export),
        web.post("/api/import", api_import),
        web.post("/api/quick", api_quick),
        web.get("/api/calendar", api_calendar),
        web.get("/api/integration", api_integration),
        web.get("/api/integration.zip", api_integration_zip),
        web.post("/api/integration/install", api_integration_install),
    ])
    app.on_startup.append(on_start)
    app.on_cleanup.append(on_stop)
    return app


if __name__ == "__main__":
    web.run_app(make_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8099")), print=None)
