"""Installerar (valfritt) kalenderintegrationen och Lovelace-korten i Home Assistants konfigurationsmapp."""
import asyncio
import io
import json
import logging
import os
import shutil
import zipfile

import ha
import state

log = logging.getLogger("installer")
HA_CONFIG = os.environ.get("HA_CONFIG_DIR", "/homeassistant")
APP = os.path.dirname(os.path.abspath(__file__))
SRC_INT = os.path.join(APP, "integration", "reminders_pro")
SRC_CARD = os.path.join(APP, "web", "reminders-pro-cards.js")
CARD_NAME = "reminders-pro-cards.js"
_RESTART = {"needed": False}


def _dst_int():
    return os.path.join(HA_CONFIG, "custom_components", "reminders_pro")


def _dst_card():
    return os.path.join(HA_CONFIG, "www", CARD_NAME)


async def base_url() -> str:
    info = await ha.addon_info()
    host = info.get("hostname")
    if not host:
        h = os.environ.get("HOSTNAME", "")
        host = h.replace("addon_", "", 1).replace("_", "-") if h else "local-reminders-pro"
    return f"http://{host}:8099"


def _installed_version():
    try:
        with open(os.path.join(_dst_int(), "manifest.json")) as f:
            return json.load(f).get("version")
    except Exception:
        return None


def _same_file(a, b):
    try:
        with open(a, "rb") as x, open(b, "rb") as y:
            return x.read() == y.read()
    except Exception:
        return False


async def status() -> dict:
    mounted = os.path.isdir(HA_CONFIG)
    return {"mounted": mounted, "url": await base_url(), "version": state.VERSION,
            "integration_installed": _installed_version() is not None,
            "integration_version": _installed_version(),
            "integration_current": _installed_version() == state.VERSION,
            "card_installed": os.path.exists(_dst_card()),
            "card_current": _same_file(SRC_CARD, _dst_card()),
            "restart_needed": _RESTART["needed"],
            "options": {"install_integration": state.CFG.get("install_integration", True),
                        "install_card": state.CFG.get("install_card", True)}}


async def _register_resource():
    url = f"/local/{CARD_NAME}?v={state.VERSION}"
    try:
        res = await ha.ws_call({"type": "lovelace/resources"})
        mine = [r for r in res or [] if str(r.get("url", "")).split("?")[0] == f"/local/{CARD_NAME}"]
        if mine and mine[0].get("url") == url:
            return True
        if mine:
            await ha.ws_call({"type": "lovelace/resources/update", "resource_id": mine[0]["id"], "res_type": "module", "url": url})
        else:
            await ha.ws_call({"type": "lovelace/resources/create", "res_type": "module", "url": url})
        return True
    except Exception as e:
        log.info("Kunde inte registrera Lovelace-resursen automatiskt (%s). Lägg till %s manuellt.", e, url)
        return False


async def install_all(force: bool = False) -> dict:
    """Kopierar integration och kort. Kastar aldrig – returnerar status med ev. fel."""
    out = {"integration": "skipped", "card": "skipped", "resource": None}
    if not os.path.isdir(HA_CONFIG):
        log.info("Konfigurationsmappen är inte monterad – hoppar över installation av integration/kort.")
        return {**await status(), **out}
    try:
        if force or state.CFG.get("install_integration", True):
            if force or _installed_version() != state.VERSION:
                dst = _dst_int()
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copytree(SRC_INT, dst, dirs_exist_ok=True)
                url = await base_url()
                with open(os.path.join(dst, "const.py"), "w") as f:
                    f.write(f'"""Genererad av add-onet."""\nDOMAIN = "reminders_pro"\nDEFAULT_URL = "{url}"\n')
                with open(os.path.join(dst, "manifest.json")) as f:
                    man = json.load(f)
                man["version"] = state.VERSION
                with open(os.path.join(dst, "manifest.json"), "w") as f:
                    json.dump(man, f, indent=2)
                _RESTART["needed"] = True
                out["integration"] = "installed"
                log.info("Integrationen installerad i %s – starta om Home Assistant och lägg till 'Reminders Pro'.", dst)
            else:
                out["integration"] = "current"
        if force or state.CFG.get("install_card", True):
            os.makedirs(os.path.dirname(_dst_card()), exist_ok=True)
            if not _same_file(SRC_CARD, _dst_card()):
                shutil.copyfile(SRC_CARD, _dst_card())
                out["card"] = "installed"
            else:
                out["card"] = "current"
            out["resource"] = await _register_resource()
    except Exception as e:
        log.warning("Installation misslyckades: %s", e)
        out["error"] = str(e)
    return {**await status(), **out}


async def integration_zip() -> bytes:
    """Zip med custom_components/reminders_pro/ (för manuell installation) – packas upp i konfigurationsmappen."""
    url = await base_url()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(SRC_INT):
            if "__pycache__" in root:
                continue
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, SRC_INT)
                arc = f"custom_components/reminders_pro/{rel}"
                if rel == "const.py":
                    z.writestr(arc, f'"""Genererad av add-onet."""\nDOMAIN = "reminders_pro"\nDEFAULT_URL = "{url}"\n')
                elif rel == "manifest.json":
                    man = json.load(open(full))
                    man["version"] = state.VERSION
                    z.writestr(arc, json.dumps(man, indent=2))
                else:
                    z.write(full, arc)
    return buf.getvalue()
