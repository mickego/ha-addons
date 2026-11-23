"""Mallar: {variabel}, {state:entitet}, {attr:entitet:attribut}, {name:entitet} (alla språk)."""
import re

CANON = ["title", "message", "category", "date", "time", "weekday", "n", "remaining", "next", "id", "attempt", "now", "age"]
ALIAS = {
    # svenska
    "titel": "title", "rubrik": "title", "text": "message", "meddelande": "message", "anteckning": "message",
    "kategori": "category", "datum": "date", "tid": "time", "klockan": "time", "veckodag": "weekday",
    "nummer": "n", "nr": "n", "kvar": "remaining", "nästa": "next", "försök": "attempt", "nu": "now",
    "ålder": "age", "alder": "age", "alter": "age", "âge": "age", "ikä": "age", "years": "age",
    # tyska
    "titel_de": "title", "nachricht": "message", "kategorie": "category", "zeit": "time", "wochentag": "weekday",
    "nächste": "next", "versuch": "attempt", "jetzt": "now",
    # franska
    "titre": "title", "catégorie": "category", "heure": "time", "jour": "weekday", "prochain": "next",
    "essai": "attempt", "maintenant": "now",
    # norska
    "tittel": "title", "melding": "message", "dato": "date", "ukedag": "weekday", "neste": "next", "forsøk": "attempt",
    # finska
    "otsikko": "title", "viesti": "message", "luokka": "category", "päivä": "date", "aika": "time",
    "viikonpäivä": "weekday", "seuraava": "next", "yritys": "attempt", "nyt": "now",
}
KINDS = {"state": "state", "värde": "state", "wert": "state", "valeur": "state", "verdi": "state", "arvo": "state",
         "attr": "attr", "attribut": "attr", "attribut_fi": "attr", "attribute": "attr",
         "name": "name", "namn": "name", "navn": "name", "nom": "name", "nimi": "name"}
TOKEN = re.compile(r"\{([^{}\n]+)\}")


def uses(text, key) -> bool:
    """Används variabeln (eller något av dess alias) i texten? Låter dyra värden räknas ut bara vid behov."""
    if not isinstance(text, str) or "{" not in text:
        return False
    names = {key} | {a for a, c in ALIAS.items() if c == key}
    for m in TOKEN.finditer(text):
        if m.group(1).strip().lower() in names:
            return True
    return False


def _parse(token: str):
    tk = token.strip()
    if ":" in tk:
        kind, rest = tk.split(":", 1)
        kind = KINDS.get(kind.strip().lower())
        if not kind:
            return None
        rest = rest.strip()
        if kind == "attr":
            if ":" not in rest:
                return None
            ent, attr = rest.rsplit(":", 1)
            return ("attr", ent.strip(), attr.strip())
        return (kind, rest)
    key = ALIAS.get(tk.lower(), tk.lower())
    if key in CANON:
        return ("var", key)
    return None


async def render(text, ctx: dict, get_state) -> str:
    """Ersätter kända tokens. Okända tokens lämnas orörda."""
    if not isinstance(text, str) or "{" not in text:
        return text
    needed, parsed = set(), {}
    for m in TOKEN.finditer(text):
        p = _parse(m.group(1))
        parsed[m.group(0)] = p
        if p and p[0] in ("state", "attr", "name"):
            needed.add(p[1])
    states = {}
    for ent in needed:
        try:
            states[ent] = await get_state(ent)
        except Exception:
            states[ent] = None

    def sub(m):
        p = parsed.get(m.group(0))
        if not p:
            return m.group(0)
        if p[0] == "var":
            return str(ctx.get(p[1], ""))
        st = states.get(p[1])
        if st is None:
            return ""
        if p[0] == "state":
            return str(st.get("state", ""))
        if p[0] == "name":
            return str((st.get("attributes") or {}).get("friendly_name", p[1]))
        return str((st.get("attributes") or {}).get(p[2], ""))

    return TOKEN.sub(sub, text)


async def render_json(obj, ctx, get_state):
    if isinstance(obj, str):
        return await render(obj, ctx, get_state)
    if isinstance(obj, list):
        return [await render_json(x, ctx, get_state) for x in obj]
    if isinstance(obj, dict):
        return {k: await render_json(v, ctx, get_state) for k, v in obj.items()}
    return obj
