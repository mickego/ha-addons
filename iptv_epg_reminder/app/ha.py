"""Home Assistant-klient (Supervisor-proxy): tjänster, tillstånd, entiteter, websocket."""
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

NOTIFY_TYPES = ["push", "plain", "persistent", "tts", "none"]

_STATES_CACHE = {"ts": 0, "data": []}


def _hdr():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


async def _req(method, path, **kw):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        async with s.request(method, f"{BASE}{path}", headers=_hdr(), **kw) as r:
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


async def all_states(max_age=20):
    if time.time() - _STATES_CACHE["ts"] > max_age:
        _STATES_CACHE["data"] = await _req("GET", "/states")
        _STATES_CACHE["ts"] = time.time()
    return _STATES_CACHE["data"]


async def get_state(entity_id: str):
    if not TOKEN:
        return None
    try:
        return await _req("GET", f"/states/{entity_id}")
    except Exception:
        return None


async def search_entities(q: str, limit=25):
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
    """Listar notify-tjänster, mediaspelare, remotes, personer och tts-motorer."""
    notify, players, tts, remotes, persons = [], [], [], [], []
    try:
        services = await _req("GET", "/services")
        for d in services:
            if d.get("domain") == "notify":
                for name in (d.get("services") or {}):
                    if name in ("send_message", "notify", "persistent_notification"):
                        continue
                    pretty = name.replace("mobile_app_", "📱 ").replace("_", " ")
                    notify.append({"id": f"notify.{name}", "name": pretty, "mobile": name.startswith("mobile_app_")})
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
            elif eid.startswith("remote."):
                remotes.append({"id": eid, "name": fn})
            elif eid.startswith("person."):
                persons.append({"id": eid, "name": fn, "state": st.get("state")})
    except Exception as e:
        log.warning("states: %s", e)
    notify.sort(key=lambda x: (not x["mobile"], x["name"]))
    for lst in (players, remotes, persons, tts):
        lst.sort(key=lambda x: x["name"])
    return {"notify": notify, "media_players": players, "tts_entities": tts, "remotes": remotes, "persons": persons}


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
    """Skapar/uppdaterar en (virtuell) entitet via states-API:t. Försvinner vid HA-omstart."""
    if not TOKEN:
        log.info("[dev] state %s=%s", entity_id, state)
        return
    await _req("POST", f"/states/{entity_id}", json={"state": str(state), "attributes": attributes or {}})


async def send(ntype: str, targets_: list, title: str, message: str, *, tag: str, image: str | None,
               tts_entity: str = "", language: str = "sv", buttons: list | None = None) -> list[str]:
    """Skickar en notis. Returnerar lista med felmeddelanden (tom = allt ok)."""
    errors = []
    if ntype == "none":
        return errors
    if ntype == "persistent":
        try:
            await call("persistent_notification", "create",
                       {"title": title, "message": message, "notification_id": tag})
        except Exception as e:
            errors.append(str(e))
        return errors

    if ntype == "tts":
        ent = tts_entity
        if not ent:
            lst = (await targets()).get("tts_entities") or []
            ent = lst[0]["id"] if lst else ""
        if not ent:
            return ["No tts entity found"]
        for t in targets_:
            try:
                await call("tts", "speak", {"entity_id": ent, "media_player_entity_id": t,
                                            "message": f"{title}. {message}", "language": language})
            except Exception as e:
                errors.append(f"{t}: {e}")
        return errors

    for t in targets_:
        svc = t.split(".", 1)[1] if t.startswith("notify.") else t
        payload = {"title": title, "message": message}
        if ntype == "push":
            data = {"tag": tag, "ttl": 0, "priority": "high", "channel": "EPG-reminders",
                    "importance": "high"}
            if image:
                data["image"] = image
            if buttons:
                data["actions"] = buttons
            payload["data"] = data
        try:
            await call("notify", svc, payload)
        except Exception as e:
            errors.append(f"{t}: {e}")
    if not targets_:
        errors.append("No devices selected")
    return errors


async def tune(entity: str, number: str, delay: float = 0.4, suffix: str = ""):
    """Slår siffrorna på en remote-entitet (11 -> 1, 1) och ev. ett avslutande kommando."""
    cmds = list(str(number))
    if suffix:
        cmds.append(suffix)
    data = {"entity_id": entity, "command": cmds}
    if delay and len(cmds) > 1:
        data["delay_secs"] = delay
    await call("remote", "send_command", data)


async def ws_listen(handler):
    """Lyssnar på knapptryck i mobilnotiser (mobile_app_notification_action m.fl.)."""
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
                    for i, et in enumerate(("mobile_app_notification_action", "ios.notification_action_fired"), 1):
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
