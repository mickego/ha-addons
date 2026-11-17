"""Hjälpfunktioner: wildcard-sökning, tidsparsning."""
import re
from datetime import datetime, timedelta, timezone


def _term(t: str):
    """Returnerar (full, partial) matchare för en söktermsträng.

    * och ? är wildcards. Med wildcard måste hela titeln matcha (ankrad),
      t.ex. 'Rapport*' = börjar med Rapport, '*fotboll*' = innehåller fotboll.
    Utan wildcard används "innehåller" (skiftlägesokänsligt).
    """
    t = t.strip()
    if "*" in t or "?" in t:
        rx = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in t)
        full = re.compile("^" + rx + "$", re.I | re.S)
        part = re.compile(rx, re.I | re.S)
        return (lambda s: bool(full.match(s))), (lambda s: bool(part.search(s)))
    tl = t.casefold()
    f = lambda s: tl in s.casefold()
    return f, f


def compile_query(q: str):
    """Kompilerar en sökfråga till en funktion f(title, descr=None) -> bool.

    Flera sökord separeras med komma, semikolon eller radbrytning (ELLER).
    Ett sökord som börjar med - eller ! är ett uteslutande (får inte matcha).
    Returnerar None om frågan är tom (= matcha allt).
    """
    inc, exc = [], []
    for part in re.split(r"[,;\n]+", q or ""):
        part = part.strip()
        if not part:
            continue
        if part[0] in "-!" and len(part) > 1:
            exc.append(_term(part[1:]))
        else:
            inc.append(_term(part))
    if not inc and not exc:
        return None

    def match(title: str, descr: str | None = None, extra=()) -> bool:
        """extra = andra fält (kanalnamn, kategori) som uteslutande sökord också testas mot."""
        title = title or ""
        for full, part in exc:
            if full(title) or (descr and part(descr)):
                return False
            for x in extra:
                if x and full(x):
                    return False
        if not inc:
            return True
        for full, part in inc:
            if full(title) or (descr and part(descr)):
                return True
        return False

    return match


_XT = re.compile(r"(\d{8,14})\s*([+-]\d{4})?")


def parse_xmltv_time(s: str) -> int | None:
    m = _XT.match((s or "").strip())
    if not m:
        return None
    digits = m.group(1).ljust(14, "0")
    try:
        dt = datetime.strptime(digits, "%Y%m%d%H%M%S")
    except ValueError:
        return None
    delta = timedelta(0)
    off = m.group(2)
    if off:
        sign = 1 if off[0] == "+" else -1
        delta = sign * timedelta(hours=int(off[1:3]), minutes=int(off[3:5]))
    return int((dt.replace(tzinfo=timezone.utc) - delta).timestamp())


def scrub(x) -> str:
    """Maskar lösenord/användarnamn i URL:er i felmeddelanden."""
    t = str(x)
    t = re.sub(r"(password|username)=[^&'\s)]*", r"\1=***", t, flags=re.I)
    return t
