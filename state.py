"""Delat tillstånd: konfiguration, tidszon, språk."""
import json
import os
from zoneinfo import ZoneInfo

OPTIONS_FILE = os.environ.get("OPTIONS_FILE", "/data/options.json")
CFG: dict = {}
STATE = {"tz": "UTC", "lang": "sv", "refreshing": False, "errors": [], "last_refresh": 0}


def load_cfg():
    global CFG
    try:
        with open(OPTIONS_FILE) as f:
            CFG = json.load(f)
    except Exception:
        CFG = {}
    CFG.setdefault("language", "sv")
    return CFG


def tz():
    try:
        return ZoneInfo(STATE["tz"])
    except Exception:
        return ZoneInfo("UTC")


def lang() -> str:
    return STATE["lang"] if STATE["lang"] in ("sv", "en", "de", "fr", "nb", "fi") else "sv"
