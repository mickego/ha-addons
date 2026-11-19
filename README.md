# IPTV EPG Reminders · IPTV EPG Påminnelser

**EN** – Search live programs, series and movies (wildcards), browse a TV-guide grid, and set reminders that use Home Assistant notifications. Reminders can also read text aloud (TTS), play sound from a file or URL, call any service, set entities and change channel on your TV box. Written messages can include variables and live entity values. Built-in help, Swedish/English interface.

**SV** – Sök live-program, serier och filmer (wildcards), bläddra i en tablå och sätt påminnelser via Home Assistants notiser. Påminnelser kan också läsa upp text (TTS), spela ljud från fil eller URL, anropa valfri tjänst, sätta entiteter och byta kanal på TV-boxen. Egna texter kan innehålla variabler och värden från entiteter. Inbyggd hjälp, svenskt/engelskt gränssnitt.

Open the **EPG** panel in the sidebar after starting the add-on. Full documentation: see the *Documentation* tab and the **Help** tab inside the panel.

## Highlights
- Search with `*`, `?`, comma = OR, `-exclude`
- Program, rule (watch) and time reminders; edit with ✎
- Notification: push, simple, persistent, voice, or none
- Your own title/message with `{title}`, `{channel}`, `{state:sensor.x}` …
- Actions: read aloud, sound (file/URL), any service, set entity
- Channel change with optional "turn TV on first"
- Snooze and "change channel" buttons in mobile notifications
- Quiet hours, only-if-home, favorites
- Sensors `sensor.epg_*` and events `iptv_epg_reminder` / `iptv_epg_tune` / `iptv_epg_new_titles`
