"""SQLite-lagring."""
import json
import os
import sqlite3
import time

DB_PATH = os.environ.get("EPG_DB", "/data/epg.db")

SCHEMA = """
create table if not exists channels(
  id text primary key, name text, icon text, cat text, src text, stream_id text, url text);
create table if not exists programs(
  channel_id text, start integer, stop integer, title text, descr text, category text,
  primary key(channel_id, start));
create index if not exists ix_prog_start on programs(start);
create index if not exists ix_prog_stop on programs(stop);
create table if not exists catalog(
  kind text, id text, name text, cat text, year text, rating text, cover text, added integer, ext text,
  primary key(kind, id));
create table if not exists categories(kind text, id text, name text, primary key(kind, id));
create table if not exists reminders(
  id integer primary key autoincrement,
  kind text,                 -- 'program' | 'rule'
  scope text default 'live', -- live | movie | series
  label text,
  channel_id text, start integer, stop integer, title text,   -- för kind=program
  pattern text, channel_pattern text, in_descr integer default 0, -- för kind=rule
  lead integer default 10,
  ntype text default 'push',
  targets text default '[]',
  enabled integer default 1,
  created integer);
create table if not exists fired(reminder_id integer, key text, ts integer,
  primary key(reminder_id, key));
create table if not exists saved(
  id integer primary key autoincrement, kind text, pattern text, created integer);
create table if not exists settings(k text primary key, v text);
create table if not exists channel_map(channel_id text primary key, number text);
create table if not exists favorites(channel_id text primary key);
create table if not exists snoozes(id integer primary key autoincrement, fire_at integer, rem_id integer, ctx text);
create table if not exists ctxs(token text primary key, rem_id integer, ctx text, created integer);
create table if not exists history(
  id integer primary key autoincrement, ts integer, label text, ntype text,
  targets text, ok integer, err text);
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
    have = {r[1] for r in c.execute("pragma table_info(reminders)")}
    for col, ddl in (("tune", "integer default 0"), ("tune_entity", "text"),
                     ("tune_number", "text"), ("tune_when", "text default 'start'"),
                     ("at_time", "text"), ("days", "text"),
                     ("actions", "text"), ("opts", "text")):
        if col not in have:
            c.execute(f"alter table reminders add column {col} {ddl}")
    if "ext" not in {r[1] for r in c.execute("pragma table_info(catalog)")}:
        c.execute("alter table catalog add column ext text")
    if "url" not in {r[1] for r in c.execute("pragma table_info(channels)")}:
        c.execute("alter table channels add column url text")
    # Migrering: gamla "fired"-nycklar (före steg-modellen) får steg-suffix så inget skickas om
    legacy = c.execute("select reminder_id,key,ts from fired where key not like '%|%'").fetchall()
    for r in legacy:
        base = r["key"][5:] if r["key"].startswith("tune:") else r["key"]
        for st in ("notify", "start"):
            c.execute("insert or ignore into fired values(?,?,?)", (r["reminder_id"], f"{base}|{st}", r["ts"]))
        c.execute("delete from fired where reminder_id=? and key=?", (r["reminder_id"], r["key"]))
    c.commit()
    c.close()


DEFAULTS = {
    "lead": 10, "ntype": "push", "targets": [],
    "tune_entity": "", "tune_delay": 0.4, "tune_suffix": "", "tune_pre_entity": "", "tune_pre_wait": 8,
    "quiet_enabled": False, "quiet_from": "22:00", "quiet_to": "07:00",
    "home_entities": [], "tts_entity": "", "tts_language": "", "snooze_min": 10,
    "play_entities": [], "play_fmt": "hls", "play_ctype": "auto",
}


def load_defaults(c, cfg=None):
    d = dict(DEFAULTS)
    if cfg:
        d["lead"] = int(cfg.get("default_lead_minutes") or d["lead"])
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


def add_history(c, label, ntype, targets, ok, err=""):
    c.execute(
        "insert into history(ts,label,ntype,targets,ok,err) values(?,?,?,?,?,?)",
        (int(time.time()), label, ntype, json.dumps(targets), 1 if ok else 0, err),
    )
    c.execute("delete from history where id not in (select id from history order by id desc limit 100)")
    c.commit()
