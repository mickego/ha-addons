"""Delat tillstånd: konfiguration, tidszon, språk, klocka."""
import json
import os
import time
from zoneinfo import ZoneInfo

VERSION = "1.3.1"
LANGS = ("sv", "en", "de", "fr", "nb", "fi")
OPTIONS_FILE = os.environ.get("OPTIONS_FILE", "/data/options.json")
CFG: dict = {}
STATE = {"tz": "UTC", "lang": "sv"}


def now() -> int:
    """Nuvarande tid i UTC-sekunder (kan bytas ut i tester)."""
    return int(time.time())


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
    return STATE["lang"] if STATE["lang"] in LANGS else "sv"
