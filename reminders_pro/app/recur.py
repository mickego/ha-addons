"""Återkomstmotor för Påminnelser Pro.

Regelformat (JSON, alla tider är lokal väggklocktid i HA:s tidszon):
{
  "freq": "once|minute|hour|day|week|month|year",
  "interval": 1,                       # var N:e minut/timme/dag/vecka/månad/år
  "start": "2026-11-22" | "2026-11-22T08:00",   # första möjliga tillfälle (och förankring)
  "end": "2027-01-01" | "2027-01-01T12:00" | null,  # sista tillfälle (bara datum = hela dagen)
  "count": null | N,                   # högst N tillfällen (undantagsdatum räknas inte)
  "times": ["08:00","12:00"],          # klockslag per dag (day/week/month/year)
  "series": [{"from":"08:00","to":"17:00","every":20}],  # upprepade klockslag (minuter)
  "window": {"from":"08:00","to":"17:00"},  # bara minute/hour: aktivt tidsfönster
  "weekdays": [0,4],                   # 0=mån … 6=sön (week, och som filter för day/minute/hour)
  "monthdays": [15,-1],                # dag i månaden, -1 = sista dagen (month/year)
  "nth": {"n":[-1],"wd":4},            # t.ex. sista fredagen; wd 0-6, 7=vilken dag som helst, 8=vardag, 9=helgdag
  "months": [3],                       # bara year
  "overflow": "clamp|skip",            # dag 31 i kort månad: sista dagen eller hoppa över
  "exdates": ["2026-12-24","2026-12-25T08:00"]
}
Sommar-/vintertid: väggklockstider (times/series) följer lokal tid. Ett klockslag som inte
finns (vårens hopp) flyttas fram till första giltiga tid; ett som finns två gånger (höstens
tillbakahopp) utlöses en gång. minute/hour är verkligt förflutna intervall (var 2:a timme är
alltid 2 timmar), medan fönster och veckodagsfilter följer lokal tid.
"""
from __future__ import annotations

import calendar
import math
from datetime import date, datetime, timedelta, timezone

FREQS = ("once", "minute", "hour", "day", "week", "month", "year")
MAX_SCAN = 200_000          # högsta antal steg per sökning
MAX_COUNT = 100_000


class RuleError(ValueError):
    """Ogiltig regel. args[0] är en felkod (översätts i gränssnittet)."""


# --------------------------------------------------------------------------- hjälpare
def _hm(s) -> int:
    try:
        h, m = str(s).strip().split(":")[:2]
        h, m = int(h), int(m)
    except Exception:
        raise RuleError("err_time")
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise RuleError("err_time")
    return h * 60 + m


def _date(s) -> date:
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        raise RuleError("err_date")


def _parse_dt(s):
    """'YYYY-MM-DD' eller 'YYYY-MM-DDTHH:MM' -> (date, minutes|None)."""
    s = str(s).strip().replace(" ", "T")
    d = _date(s)
    if len(s) > 10:
        return d, _hm(s[11:16])
    return d, None


def to_ts(d: date, minutes: int, tz) -> int:
    """Lokal väggklocktid -> UTC-sekunder. fold=0: glapp flyttas fram, dubbeltid ger första."""
    dt = datetime(d.year, d.month, d.day, minutes // 60, minutes % 60, tzinfo=tz)
    return int(dt.timestamp())


def local_dt(ts: int, tz) -> datetime:
    return datetime.fromtimestamp(ts, tz)


def _wd_match(wd_code: int, d: date) -> bool:
    w = d.weekday()
    if wd_code <= 6:
        return w == wd_code
    if wd_code == 7:
        return True
    if wd_code == 8:
        return w < 5
    return w >= 5


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _add_months(y: int, m: int, k: int):
    idx = y * 12 + (m - 1) + k
    return idx // 12, idx % 12 + 1


# --------------------------------------------------------------------------- validering
def normalize(rule: dict) -> dict:
    """Validerar och rensar en regel. Kastar RuleError(kod)."""
    if not isinstance(rule, dict):
        raise RuleError("err_rule")
    r: dict = {}
    freq = rule.get("freq", "day")
    if freq not in FREQS:
        raise RuleError("err_freq")
    r["freq"] = freq
    try:
        r["interval"] = max(1, min(int(rule.get("interval") or 1), 100_000))
    except Exception:
        raise RuleError("err_interval")
    if not rule.get("start"):
        raise RuleError("err_start")
    d, m = _parse_dt(rule["start"])
    r["start"] = d.isoformat() if m is None else f"{d.isoformat()}T{m // 60:02d}:{m % 60:02d}"
    if freq == "once" and m is None:
        raise RuleError("err_time")
    if rule.get("end"):
        d2, m2 = _parse_dt(rule["end"])
        r["end"] = d2.isoformat() if m2 is None else f"{d2.isoformat()}T{m2 // 60:02d}:{m2 % 60:02d}"
        if (d2, m2 if m2 is not None else 1440) < (d, m if m is not None else 0):
            raise RuleError("err_end_before_start")
    else:
        r["end"] = None
    if rule.get("count") not in (None, "", 0):
        try:
            c = int(rule["count"])
        except Exception:
            raise RuleError("err_count")
        if not 1 <= c <= MAX_COUNT:
            raise RuleError("err_count")
        r["count"] = c
    else:
        r["count"] = None
    times = sorted({_hm(t) for t in (rule.get("times") or [])})
    r["times"] = [f"{t // 60:02d}:{t % 60:02d}" for t in times]
    series = []
    for s in rule.get("series") or []:
        a, b, ev = _hm(s.get("from")), _hm(s.get("to")), int(s.get("every") or 0)
        if ev < 1 or b < a:
            raise RuleError("err_series")
        series.append({"from": f"{a // 60:02d}:{a % 60:02d}", "to": f"{b // 60:02d}:{b % 60:02d}", "every": ev})
    r["series"] = series
    if freq in ("day", "week", "month", "year") and not r["times"] and not series:
        raise RuleError("err_no_times")
    w = rule.get("window")
    if w and (w.get("from") or w.get("to")):
        r["window"] = {"from": f"{_hm(w.get('from') or '00:00') // 60:02d}:{_hm(w.get('from') or '00:00') % 60:02d}",
                       "to": f"{_hm(w.get('to') or '23:59') // 60:02d}:{_hm(w.get('to') or '23:59') % 60:02d}"}
    else:
        r["window"] = None
    wds = sorted({int(x) for x in (rule.get("weekdays") or [])})
    if any(x < 0 or x > 6 for x in wds):
        raise RuleError("err_weekday")
    r["weekdays"] = wds
    if freq == "week" and not wds:
        r["weekdays"] = [d.weekday()]
    md = sorted({int(x) for x in (rule.get("monthdays") or [])})
    if any(x == 0 or x < -31 or x > 31 for x in md):
        raise RuleError("err_monthday")
    r["monthdays"] = md
    nth = rule.get("nth")
    if nth and nth.get("n"):
        ns = sorted({int(x) for x in nth["n"]})
        if any(x == 0 or x < -5 or x > 5 for x in ns):
            raise RuleError("err_nth")
        wd = int(nth.get("wd", 0))
        if not 0 <= wd <= 9:
            raise RuleError("err_weekday")
        r["nth"] = {"n": ns, "wd": wd}
    else:
        r["nth"] = None
    months = sorted({int(x) for x in (rule.get("months") or [])})
    if any(x < 1 or x > 12 for x in months):
        raise RuleError("err_month")
    r["months"] = months
    r["overflow"] = "skip" if rule.get("overflow") == "skip" else "clamp"
    ex = []
    for x in rule.get("exdates") or []:
        dd, mm = _parse_dt(x)
        ex.append(dd.isoformat() if mm is None else f"{dd.isoformat()}T{mm // 60:02d}:{mm % 60:02d}")
    r["exdates"] = sorted(set(ex))
    return r


# --------------------------------------------------------------------------- tider per dag
def _tod_minutes(r) -> list[int]:
    out = {_hm(t) for t in r["times"]}
    for s in r["series"]:
        a, b = _hm(s["from"]), _hm(s["to"])
        out.update(range(a, b + 1, s["every"]))
    return sorted(out)


def _month_days(r, y: int, m: int) -> list[date]:
    last = calendar.monthrange(y, m)[1]
    days = set()
    for dd in r["monthdays"]:
        if dd < 0:
            x = last + dd + 1
            if x >= 1:
                days.add(x)
        elif dd <= last:
            days.add(dd)
        elif r["overflow"] == "clamp":
            days.add(last)
    if r["nth"]:
        cand = [d for d in range(1, last + 1) if _wd_match(r["nth"]["wd"], date(y, m, d))]
        for n in r["nth"]["n"]:
            i = n - 1 if n > 0 else n
            if -len(cand) <= i < len(cand):
                days.add(cand[i])
    return [date(y, m, d) for d in sorted(days)]


class _Ctx:
    """Förberäknade värden för en regel."""

    def __init__(self, rule: dict, tz):
        self.r = rule if rule.get("_n") else {**normalize(rule), "_n": 1}
        r = self.r
        self.tz = tz
        d, m = _parse_dt(r["start"])
        self.start_date = d
        self.start_min = m or 0
        self.start_ts = to_ts(d, self.start_min, tz)
        if r["end"]:
            d2, m2 = _parse_dt(r["end"])
            self.end_ts = to_ts(d2, m2, tz) if m2 is not None else to_ts(d2, 23 * 60 + 59, tz) + 59
        else:
            self.end_ts = None
        self.tod = _tod_minutes(r) if r["freq"] not in ("minute", "hour", "once") else []
        self.ex_dates = {x for x in r["exdates"] if len(x) == 10}
        self.ex_times = {x for x in r["exdates"] if len(x) > 10}
        self.cnt = r["count"]
        # standardvärden härledda från startdatum
        self.monthdays_eff = r["monthdays"]
        if r["freq"] in ("month", "year") and not r["monthdays"] and not r["nth"]:
            r = {**r, "monthdays": [d.day]}
            self.r = r
        self.months_eff = r["months"] or [d.month]

    def excluded(self, ts: int) -> bool:
        dt = local_dt(ts, self.tz)
        if dt.date().isoformat() in self.ex_dates:
            return True
        return dt.strftime("%Y-%m-%dT%H:%M") in self.ex_times


# --------------------------------------------------------------------------- generatorer
def _dates(c: _Ctx, from_date: date):
    """Kandidatdatum (stigande, >= from_date) för day/week/month/year, förankrade vid start."""
    r = c.r
    n = r["interval"]
    base = c.start_date
    wds = r["weekdays"]
    limit_date = None
    if c.end_ts:
        limit_date = local_dt(c.end_ts, c.tz).date()
    f = r["freq"]
    empty = 0
    if f == "day":
        if from_date > base:
            k = math.ceil((from_date - base).days / n)
        else:
            k = 0
        d = base + timedelta(days=k * n)
        while True:
            if limit_date and d > limit_date:
                return
            if not wds or d.weekday() in wds:
                yield d
                empty = 0
            else:
                empty += 1
                if empty > 7 * 400:
                    return
            d += timedelta(days=n)
    elif f == "week":
        b = _monday(base)
        wk = _monday(from_date)
        k = max(0, math.ceil((wk - b).days / 7 / n))
        while True:
            w0 = b + timedelta(weeks=k * n)
            if limit_date and w0 > limit_date:
                return
            for wd in wds:
                d = w0 + timedelta(days=wd)
                if d >= from_date:
                    yield d
            k += 1
    elif f == "month":
        bidx = base.year * 12 + base.month - 1
        fidx = from_date.year * 12 + from_date.month - 1
        k = max(0, math.ceil((fidx - bidx) / n))
        while True:
            y, m = _add_months(base.year, base.month, k * n)
            if limit_date and date(y, m, 1) > limit_date:
                return
            got = False
            for d in _month_days(r, y, m):
                if d >= from_date:
                    got = True
                    yield d
            empty = 0 if got else empty + 1
            if empty > 1200:
                return
            k += 1
    elif f == "year":
        k = max(0, math.ceil((from_date.year - base.year) / n))
        while True:
            y = base.year + k * n
            if y > 9000 or (limit_date and y > limit_date.year):
                return
            for m in c.months_eff:
                for d in _month_days(r, y, m):
                    if d >= from_date:
                        yield d
            k += 1


def _raw(c: _Ctx, from_ts: int | None):
    """Alla tillfällen (stigande) efter from_ts (inklusive), före undantag/antal."""
    r = c.r
    f = r["freq"]
    lo = c.start_ts if from_ts is None else max(c.start_ts, from_ts)
    if f == "once":
        if c.start_ts >= lo:
            yield c.start_ts
        return
    if f in ("minute", "hour"):
        step = r["interval"] * (60 if f == "minute" else 3600)
        k = max(0, math.ceil((lo - c.start_ts) / step))
        wds = set(r["weekdays"])
        win = r["window"]
        wa = _hm(win["from"]) if win else 0
        wb = _hm(win["to"]) if win else 1439
        steps = 0
        while True:
            t = c.start_ts + k * step
            if c.end_ts and t > c.end_ts:
                return
            steps += 1
            if steps > MAX_SCAN:
                return
            k += 1
            dt = local_dt(t, c.tz)
            if wds and dt.weekday() not in wds:
                continue
            mm = dt.hour * 60 + dt.minute
            if win:
                ok = (wa <= mm <= wb) if wa <= wb else (mm >= wa or mm <= wb)
                if not ok:
                    continue
            yield t
    else:
        start_d = c.start_date
        if from_ts is not None:
            fd = local_dt(lo, c.tz).date() - timedelta(days=1)
            fd = max(fd, start_d)
        else:
            fd = start_d
        last = None
        for d in _dates(c, fd):
            seen = set()
            for mm in c.tod:
                t = to_ts(d, mm, c.tz)
                if t in seen:
                    continue
                seen.add(t)
            for t in sorted(seen):
                if t < lo:
                    continue
                if c.end_ts and t > c.end_ts:
                    return
                if last is not None and t <= last:
                    continue
                last = t
                yield t


def iter_occurrences(rule: dict, tz, from_ts: int | None = None):
    """Alla tillfällen >= from_ts i stigande ordning (hänsyn till start/slut/undantag/antal)."""
    c = rule if isinstance(rule, _Ctx) else _Ctx(rule, tz)
    if c.cnt is None:
        for t in _raw(c, from_ts):
            if not c.excluded(t):
                yield t
        return
    n = 0
    for t in _raw(c, None):
        if c.excluded(t):
            continue
        n += 1
        if n > c.cnt:
            return
        if from_ts is None or t >= from_ts:
            yield t


def next_after(rule: dict, tz, after_ts: int, inclusive: bool = False) -> int | None:
    """Första tillfället efter (eller vid, om inclusive) after_ts."""
    c = _Ctx(rule, tz)
    frm = after_ts if inclusive else after_ts + 1
    for t in iter_occurrences(c, tz, frm):
        return t
    return None


def occurrences_between(rule: dict, tz, start_ts: int, end_ts: int, limit: int = 500) -> list[int]:
    c = _Ctx(rule, tz)
    out = []
    for t in iter_occurrences(c, tz, start_ts):
        if t > end_ts or len(out) >= limit:
            break
        out.append(t)
    return out


def preview(rule: dict, tz, n: int = 10, after_ts: int | None = None) -> list[int]:
    import time as _t
    c = _Ctx(rule, tz)
    frm = int(_t.time()) if after_ts is None else after_ts
    out = []
    for t in iter_occurrences(c, tz, frm):
        out.append(t)
        if len(out) >= n:
            break
    return out


def total_remaining(rule: dict, tz, after_ts: int):
    """Antal kvarvarande tillfällen om count är satt, annars None."""
    c = _Ctx(rule, tz)
    if c.cnt is None:
        return None
    return sum(1 for _ in iter_occurrences(c, tz, after_ts))


def index_of(rule: dict, tz, ts: int) -> int | None:
    """Vilket tillfälle i ordningen (1-baserat) ts är. Används för {n}."""
    i = 0
    for t in iter_occurrences(_Ctx(rule, tz), tz, None):
        i += 1
        if t == ts:
            return i
        if t > ts or i > 50_000:
            return None
    return None
