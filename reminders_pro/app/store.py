"""SQLite-lagring."""
import json
import os
import sqlite3
import time

DB_PATH = os.environ.get("RP_DB", "/data/reminders_pro.db")

SCHEMA = """
create table if not exists categories(
  id integer primary key autoincrement, name text not null, color text default '#6c8cff', icon text default 'mdi:bell');
create table if not exists reminders(
  id integer primary key autoincrement,
  title text not null, note text default '',
  category_id integer,
  rule text not null,            -- JSON: återkomstregel (se recur.py)
  actions text default '[]',     -- JSON: lista med notis-/åtgärdssteg
  opts text default '{}',        -- JSON: repetition, tysta timmar, hemma, knappar m.m.
  enabled integer default 1,
  paused_until integer,          -- UTC-sekunder, null = ej pausad
  next_at integer,               -- nästa tillfälle (UTC), null = inga fler
  last_fired integer, fired_count integer default 0,
  created integer, updated integer);
create index if not exists ix_rem_next on reminders(next_at);
create table if not exists pending(
  id integer primary key autoincrement,
  rem_id integer, occ_ts integer, token text unique,
  status text,                   -- deferred | open | snoozed | done | skipped | expired
  due_at integer,                -- när nästa utskick (uppskjutet/snooze/upprepning) ska ske
  sent integer default 0, repeat_every integer default 0, repeat_max integer default 0,
  snapshot text,                 -- JSON: titel, text, åtgärder, tillval vid utlösning
  created integer, closed integer);
create index if not exists ix_pend_status on pending(status, due_at);
create table if not exists history(
  id integer primary key autoincrement, ts integer, rem_id integer, occ_ts integer,
  kind text, title text, detail text);
create index if not exists ix_hist_occ on history(rem_id, occ_ts);
create table if not exists settings(k text primary key, v text);
"""


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.row_factory = sqlite3.Row
    c.execute("pragma journal_mode=wal")
    c.execute("pragma synchronous=normal")
    return c


def init():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = conn()
    c.executescript(SCHEMA)
    for stmt in ("alter table reminders add column adv_checked integer",
                 "alter table categories add column sensor integer default 0"):
        try:
            c.execute(stmt)
        except sqlite3.OperationalError:
            pass
    c.commit()
    c.close()


DEFAULTS = {
    "snooze_min": 10,
    "snooze_choices": [5, 10, 30, 60],
    "quiet_enabled": False, "quiet_from": "22:00", "quiet_to": "07:00", "quiet_mode": "delay",   # delay | skip
    "home_entities": [],
    "tts_entity": "", "tts_language": "",
    "default_targets": [],
    "grace_min": 60,                 # så sent får en missad påminnelse fortfarande skickas
    "repeat_every_min": 5, "repeat_max": 12,
    "keep_history_days": 60,
}


def load_defaults(c, cfg=None):
    d = dict(DEFAULTS)
    if cfg:
        d["snooze_min"] = int(cfg.get("default_snooze_min") or d["snooze_min"])
        d["tts_entity"] = cfg.get("tts_entity") or ""
        d["tts_language"] = cfg.get("tts_language") or ""
    d.update(get_setting(c, "defaults", {}) or {})
    return d


def get_setting(c, k, default=None):
    r = c.execute("select v from settings where k=?", (k,)).fetchone()
    if not r:
        return default
    try:
        return json.loads(r["v"])
    except Exception:
        return default


def set_setting(c, k, v):
    c.execute("insert or replace into settings(k,v) values(?,?)", (k, json.dumps(v)))
    c.commit()


def jl(v, default):
    if v is None or v == "":
        return default
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return default


def add_history(c, kind, title="", detail="", rem_id=None, occ_ts=None, ts=None):
    c.execute("insert into history(ts,rem_id,occ_ts,kind,title,detail) values(?,?,?,?,?,?)",
              (ts or int(time.time()), rem_id, occ_ts, kind, title, detail))
