"""Home Assistant-klient via Supervisor-proxyn: tjänster, tillstånd, entiteter, websocket."""
import asyncio
import json
import logging
import os
import time

import aiohttp

log = logging.getLogger("ha")

TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
BASE = os.environ.get("HA_API", "http://supervisor/core/api")
WS_URL = os.environ.get("HA_WS", "ws://supervisor/core/websocket")
SUP = os.environ.get("SUPERVISOR_API", "http://supervisor")

_STATES = {"ts": 0, "data": []}


def _hdr():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


async def _req(method, path, base=None, **kw):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        async with s.request(method, f"{base or BASE}{path}", headers=_hdr(), **kw) as r:
            if r.status >= 400:
                raise RuntimeError(f"HA {r.status}: {(await r.text())[:200]}")
            if r.content_type == "application/json":
                return await r.json()
            return await r.text()


async def config() -> dict:
    try:
        return await _req("GET", "/config")
    except Exception as e:
        log.warning("Kunde inte läsa HA-config: %s", e)
        return {}


async def addon_info() -> dict:
    """Supervisor: information om detta add-on (värdnamn m.m.)."""
    try:
        r = await _req("GET", "/addons/self/info", base=SUP)
        return (r or {}).get("data", r) or {}
    except Exception as e:
        log.info("addon_info: %s", e)
        return {}


async def all_states(max_age=20):
    if time.time() - _STATES["ts"] > max_age:
        _STATES["data"] = await _req("GET", "/states")
        _STATES["ts"] = time.time()
    return _STATES["data"]


async def get_state(entity_id: str):
    if not TOKEN:
        return None
    try:
        return await _req("GET", f"/states/{entity_id}")
    except Exception:
        return None


async def search_entities(q: str, limit=30):
    q = (q or "").strip().casefold()
    out = []
    try:
        for st in await all_states():
            eid = st["entity_id"]
            name = (st.get("attributes") or {}).get("friendly_name", "")
            if not q or q in eid.casefold() or q in name.casefold():
                out.append({"id": eid, "name": name, "state": st.get("state")})
                if len(out) >= limit:
                    break
    except Exception as e:
        log.warning("entities: %s", e)
    return out


async def targets() -> dict:
    """Listar notify-tjänster, mediaspelare, TTS-motorer, personer och tjänster att anropa."""
    notify, players, tts, persons, services_out = [], [], [], [], []
    try:
        for d in await _req("GET", "/services"):
            dom = d.get("domain")
            for name in (d.get("services") or {}):
                if dom == "notify":
                    if name in ("send_message", "notify", "persistent_notification"):
                        continue
                    pretty = name.replace("mobile_app_", "📱 ").replace("_", " ")
                    notify.append({"id": f"notify.{name}", "name": pretty, "mobile": name.startswith("mobile_app_")})
                services_out.append(f"{dom}.{name}")
    except Exception as e:
        log.warning("services: %s", e)
    try:
        for st in await all_states(max_age=5):
            eid = st["entity_id"]
            fn = (st.get("attributes") or {}).get("friendly_name", eid)
            if eid.startswith("media_player."):
                players.append({"id": eid, "name": fn})
            elif eid.startswith("tts."):
                tts.append({"id": eid, "name": fn})
            elif eid.startswith("person."):
                persons.append({"id": eid, "name": fn, "state": st.get("state")})
    except Exception as e:
        log.warning("states: %s", e)
    notify.sort(key=lambda x: (not x["mobile"], x["name"]))
    for lst in (players, persons, tts):
        lst.sort(key=lambda x: x["name"])
    return {"notify": notify, "media_players": players, "tts_entities": tts, "persons": persons,
            "services": sorted(services_out)}


async def call(domain: str, service: str, data: dict):
    if not TOKEN:
        log.info("[dev] %s.%s %s", domain, service, data)
        return
    await _req("POST", f"/services/{domain}/{service}", json=data)


async def fire_event(name: str, data: dict):
    if not TOKEN:
        return
    try:
        await _req("POST", f"/events/{name}", json=data)
    except Exception as e:
        log.warning("event: %s", e)


async def set_state(entity_id: str, state, attributes: dict | None = None):
    """Skapar/uppdaterar en virtuell entitet via states-API:t (försvinner vid HA-omstart, publiceras om löpande)."""
    if not TOKEN:
        log.debug("[dev] state %s=%s", entity_id, state)
        return
    await _req("POST", f"/states/{entity_id}", json={"state": str(state), "attributes": attributes or {}})


async def clear_mobile(target: str, tag: str):
    """Tar bort en notis på mobilen (Companion-appen) via tag."""
    svc = target.split(".", 1)[1] if target.startswith("notify.") else target
    if not svc.startswith("mobile_app_"):
        return
    try:
        await call("notify", svc, {"message": "clear_notification", "data": {"tag": tag}})
    except Exception as e:
        log.debug("clear_notification: %s", e)


async def ws_listen(handler, event_types=("mobile_app_notification_action", "ios.notification_action_fired",
                                           "reminders_pro_command")):
    """Lyssnar på knapptryck i mobilnotiser och på kommandon från dashboardkort/automationer."""
    if not TOKEN:
        return
    backoff = 5
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.ws_connect(WS_URL, heartbeat=30) as ws:
                    await ws.receive_json()  # auth_required
                    await ws.send_json({"type": "auth", "access_token": TOKEN})
                    msg = await ws.receive_json()
                    if msg.get("type") != "auth_ok":
                        raise RuntimeError("websocket auth failed")
                    for i, et in enumerate(event_types, 1):
                        await ws.send_json({"id": i, "type": "subscribe_events", "event_type": et})
                    backoff = 5
                    async for m in ws:
                        if m.type != aiohttp.WSMsgType.TEXT:
                            continue
                        d = json.loads(m.data)
                        if d.get("type") == "event":
                            try:
                                await handler(d.get("event") or {})
                            except Exception:
                                log.exception("ws handler")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("websocket: %s – försöker igen om %ss", type(e).__name__, backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 120)


async def ws_call(payload: dict, timeout: float = 15):
    """Skickar ett enskilt websocket-kommando (t.ex. lovelace/resources) och returnerar resultatet."""
    if not TOKEN:
        raise RuntimeError("no token")
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect(WS_URL, timeout=timeout) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": TOKEN})
            msg = await ws.receive_json()
            if msg.get("type") != "auth_ok":
                raise RuntimeError("websocket auth failed")
            await ws.send_json({"id": 1, **payload})
            while True:
                m = await asyncio.wait_for(ws.receive_json(), timeout)
                if m.get("id") == 1 and m.get("type") == "result":
                    if not m.get("success"):
                        raise RuntimeError((m.get("error") or {}).get("message", "ws error"))
                    return m.get("result")
