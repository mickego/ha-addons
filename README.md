# Home Assistant add-ons

Two add-ons for Home Assistant. Add this repository under *Settings → Add-ons → Add-on store → ⋮ → Repositories*.

---

# Reminders Pro · Påminnelser Pro

**EN** – A pure reminder add-on with total freedom: every 3rd day, every other week on Monday and Thursday, every other month, the last Friday of the month, 3 March every year, every 20 minutes between 08 and 17 … with start, end, "after N times", exceptions and pause, and correct summer/winter time. Notify by mobile push (with **Done · Snooze · Skip**), repeat until acknowledged, persistent notification, voice, sound, any notify service (Telegram, e-mail …), call a service, set an entity or fire an event. Quiet hours, "only if someone is home", calendar entity, sensors and dashboard cards that work through Nabu Casa. Swedish, English, German, French, Norwegian and Finnish.

**SV** – Ett rent påminnelse-add-on med full frihet: var 3:e dag, varannan vecka mån+tors, varannan månad, sista fredagen i månaden, varje år 3 mars, var 20:e minut mellan 08 och 17 … med start, slut, ”efter N gånger”, undantag, paus och rätt sommar-/vintertid. Meddela via mobilpush (med **Klart · Snooze · Hoppa över**), upprepa tills kvitterat, persistent notis, röst, ljud, valfri notify-tjänst, anropa tjänst, sätt entitet eller skicka event. Tysta timmar, ”bara om någon är hemma”, kalenderentitet, sensorer och dashboardkort som fungerar via Nabu Casa.

Open the **Påminnelser** panel in the sidebar after starting the add-on. Documentation: the *Documentation* tab and the **Help** tab in the panel. Illustrated guides (PDF, Swedish and English) are in `reminders_pro/docs/`.

### Highlights
- No-code form with a live preview of the next 10 occurrences
- Intervals, calendar rules, several times per day, start/end/count/exceptions/pause
- Push with Done · Snooze · Skip, repeat until acknowledged, TTS, sound, any notify service
- Own text with `{title}`, `{date}`, `{state:sensor.x}` …
- Quiet hours (postpone or skip), only-if-home
- `calendar.reminders_pro`, `sensor.reminders_pro_*`, events, dashboard cards
- Own buttons that toggle entities, start automations or call services; Android TV / Fire TV notification; conditions on entity state
- Categories/colours, export/import

---

# IPTV EPG Reminders · IPTV EPG Påminnelser

**EN** – Search live programs, series and movies (wildcards), browse a TV-guide grid, and set reminders that use Home Assistant notifications. Reminders can also read text aloud (TTS), play sound from a file or URL, call any service, set entities and change channel on your TV box. Written messages can include variables and live entity values. Built-in help, Swedish/English interface.

**SV** – Sök live-program, serier och filmer (wildcards), bläddra i en tablå och sätt påminnelser via Home Assistants notiser. Påminnelser kan också läsa upp text (TTS), spela ljud från fil eller URL, anropa valfri tjänst, sätta entiteter och byta kanal på TV-boxen. Egna texter kan innehålla variabler och värden från entiteter. Inbyggd hjälp, svenskt/engelskt gränssnitt.

Open the **EPG** panel in the sidebar after starting the add-on. Full documentation: see the *Documentation* tab and the **Help** tab inside the panel.

### Highlights
- Search with `*`, `?`, comma = OR, `-exclude`
- Program, rule (watch) and time reminders; edit with ✎
- Notification: push, simple, persistent, voice, or none
- Your own title/message with `{title}`, `{channel}`, `{state:sensor.x}` …
- Actions: read aloud, sound (file/URL), any service, set entity
- Channel change with optional "turn TV on first"
- Snooze and "change channel" buttons in mobile notifications
- Quiet hours, only-if-home, favorites
- Sensors `sensor.epg_*` and events `iptv_epg_reminder` / `iptv_epg_tune` / `iptv_epg_new_titles`
