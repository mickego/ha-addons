# Changelog

## 2.3.1
- Playback: a failing media player no longer stops the others; players that only show dashboards (Pixel Tablet, Nest Hub …) now give a clear message

## 2.3.0
- Movies and series can now be played too: ▶ Play on a media player or watch in the panel (series: pick season and episode)
- Movie/episode proxy with seek support for the in-panel player (browsers cannot play .mkv – use a media player for those)
- Content type is chosen from the file extension (mp4, mkv, avi …); VLC still gets `music`

## 2.2.0
- Play TV: new reminder action **Play channel** sends the live stream to any media player (Chromecast / Google TV, VLC, Kodi …) via `media_player.play_media`
- ▶ Play buttons in search results, channel lists and the guide: play on a device or **watch in the panel** (HLS player with built-in stream proxy – your login never reaches the browser)
- Playback defaults under Settings (default players, HLS/TS, content type); VLC is detected automatically
- Optional ▶ Play button in the push notification and in the `epg-now-card` dashboard card (event `iptv_epg_play`)
- The stream address is built on demand from your Xtream/M3U source and is never stored in reminders, history, events or sensors
- Bundles hls.js (Apache-2.0) for the in-panel player

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
