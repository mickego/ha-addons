# Changelog

## 2.1.0
- New interface languages: German, French, Norwegian (Bokmål) and Finnish (SV/EN/DE/FR/NO/FI switch). The built-in Help tab is shown in English for the new languages.
- Add-on configuration translated to German, French, Norwegian and Finnish
- Five dashboard cards for other Lovelace dashboards (`epg-cards.js`): next reminder, upcoming list, on now (favorites, with channel-change button), last activity, status
- New sensor `sensor.epg_now_on_favorites`; `sensor.epg_next_reminder` now lists the next 12 reminders; TV-box settings exposed as attributes of `sensor.epg_active_reminders`

## 2.0.0
- Swedish/English interface switch (also default texts, history and sensors)
- Built-in help tab with examples for every feature
- Reminders can be edited (✎)
- Per-reminder actions: read text aloud (TTS), play sound from file or URL, call any service, set entity
- Own title/message with variables and entity values (`{state:…}`, `{attr:…}`, `{name:…}`)
- "Turn on first" step before channel change
- Snooze / change-channel buttons in mobile push notifications
- Quiet hours and only-if-someone-is-home
- Favorite channels in search and guide
- HA sensors (`sensor.epg_*`) and events (`iptv_epg_reminder`, `iptv_epg_tune`, `iptv_epg_new_titles`)
- No personal names or example credentials anywhere in the package

## 1.x
- Initial releases: search, guide grid, reminders, time reminders, channel change
