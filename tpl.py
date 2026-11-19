"""Mallar: {variabel}, {state:entity}, {attr:entity:attribut}, {name:entity}."""
import re

# Svenska alias -> kanoniskt (engelskt) variabelnamn
ALIAS = {
    "titel": "title", "program": "title", "kanal": "channel", "kanalnummer": "number",
    "starttid": "start", "slut": "end", "stop": "end", "datum": "date", "tid": "time",
    "minuter": "minutes", "beskrivning": "description", "kategori": "category",
    "etikett": "label", "namn": "label",
}
CANON = ["title", "channel", "number", "start", "end", "date", "time", "minutes",
         "status", "label", "lead", "description", "category", "reminder_id"]
KINDS = {"state": "state", "värde": "state", "attr": "attr", "attribut": "attr", "name": "name", "namn": "name"}
TOKEN = re.compile(r"\{([^{}\n]+)\}")


def _parse(token: str):
    """Returnerar (typ, argument...) eller None om token inte är en känd variabel."""
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
    """Ersätter alla kända tokens i text. Okända tokens lämnas orörda."""
    if not isinstance(text, str) or "{" not in text:
        return text
    needed = set()
    parsed = {}
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
        v = (st.get("attributes") or {}).get(p[2], "")
        return str(v)

    return TOKEN.sub(sub, text)


async def render_json(obj, ctx, get_state):
    """Renderar alla textvärden i en JSON-struktur."""
    if isinstance(obj, str):
        return await render(obj, ctx, get_state)
    if isinstance(obj, list):
        return [await render_json(x, ctx, get_state) for x in obj]
    if isinstance(obj, dict):
        return {k: await render_json(v, ctx, get_state) for k, v in obj.items()}
    return obj
