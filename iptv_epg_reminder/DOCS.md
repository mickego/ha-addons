# IPTV EPG Reminders · IPTV EPG Påminnelser

🇬🇧 [English](#english) · 🇸🇪 [Svenska](#svenska)

---

<a id="english"></a>
# English

## 1. Install and configure

1. Copy the `iptv_epg_reminder` folder to the `/addons` share of Home Assistant (Samba or SSH).
2. *Settings → Add-ons → Add-on store → ⋮ → Check for updates*, open **IPTV EPG Påminnelser** under *Local add-ons* and press **Install**.
3. Open the **Configuration** tab and fill in your source (see below). Start the add-on and enable *Show in sidebar*.

| Option | Meaning |
|---|---|
| `epg_url` | Your XMLTV/EPG address. Stored only here, never shown in the dashboard (only the host name is). |
| `xtream_url` | Optional Xtream Codes address for live/series/movies catalog. If empty it is derived from `epg_url` when that is an Xtream `xmltv.php` link. |
| `playlist_url` | Optional M3U fallback for the channel list. |
| `refresh_hours` | How often EPG and catalog are fetched. |
| `epg_days` | Days ahead to store. |
| `default_lead_minutes` | Initial "minutes before start" for new reminders. |
| `tts_entity` | Default TTS engine, e.g. `tts.home_assistant_cloud`. |
| `language` | Initial interface language: `sv` or `en`. Switch any time with the **SV / EN** buttons. |
| `tts_language` | Language code for spoken text. Empty = same as the interface. |

> Passwords are masked in logs and error messages. If you copy a masked URL (`••••`) the fetch fails – enter the real password.

## 2. Search

Separate keywords with commas (OR). Exclude with `-word`. `*` = any text, `?` = one character. With a wildcard the whole title must match.

| Query | Finds |
|---|---|
| `football` | titles containing football |
| `football, tennis` | football or tennis |
| `football, -women` | football, not if "women" occurs (title, channel name or category) |
| `News*` | starts with News |
| `*final*` | contains final |

Tabs: **Live › Programs**, **Live › Channels**, **Series**, **Movies**. Save a search with **＋ Save search**; filter by ⭐ favorites.

## 3. Reminders

| Type | How to create | What it does |
|---|---|---|
| Program | **🔔 Remind** on a result or in the guide | One program on one channel |
| Rule (watch) | **Watch this search / title / channel** | Every matching program; for series/movies, every *new* matching title |
| Time | **＋ Time reminder** | At a time: once, daily, Mon–Fri or chosen weekdays – independent of the EPG |

Edit with **✎**, delete with **✕**, switch rules on/off with the toggle.

### Notification
Types: **push** (mobile app), **simple** (other notify services), **persistent** (HA bell), **voice (TTS)**, **none** (only channel change/actions).

With **Buttons in the mobile notification** the push gets **Snooze N min** and **Change to channel N**. Snoozed reminders appear as 💤 in *Scheduled*.

### Your own text and variables
Write the **Title** and **Message** yourself (empty = default). Use the **Insert** bar under each field.

| Variable | Meaning |
|---|---|
| `{title}` | Program title |
| `{channel}` | Channel name |
| `{number}` | Channel number |
| `{start}` / `{end}` | Start / end time |
| `{date}` | Date (YYYY-MM-DD) |
| `{time}` | Time when sent |
| `{minutes}` | Minutes until start |
| `{status}` | Ready-made text, e.g. "Starts in 10 min on BBC1 (20:00)" |
| `{label}` | Your name for the reminder |
| `{lead}` | Minutes-before setting |
| `{description}` | Description (first 200 characters) |
| `{category}` | Category |
| `{reminder_id}` | Reminder id |

Values from Home Assistant:

| Syntax | Result |
|---|---|
| `{state:sensor.outdoor_temp}` | entity state |
| `{attr:sensor.outdoor_temp:unit_of_measurement}` | an attribute |
| `{name:person.anna}` | friendly name |

Example: `{title} starts in {minutes} min on {channel}. It is {state:sensor.outdoor_temp} degrees outside.`
Unknown variables are left as they are.

### Actions
Add any number under **Actions**. Each runs **at the notice** or **at program start** (time reminders: at the set time). **▶ Test** runs it immediately.

- **🗣️ Read text aloud** – text with variables, media player(s), optional volume, TTS engine and language.
- **🔔 Play sound** – *File*: put it in HA's media folder and type the file name (`ding.mp3`, `sounds/ding.mp3`). *URL*: any reachable audio address.
- **🛠️ Call service** – `domain.service` plus JSON data; variables work in text values.
  ```json
  light.turn_on
  {"entity_id": "light.living_room", "brightness_pct": 80}
  ```
- **🎚️ Set entity** – `on`/`off` for switch, input_boolean, light …; text for input_text; number for input_number; option for input_select; other entities get a virtual state.

### Channel change
Enable **Switch the TV box automatically**, enter channel number and the TV box (`remote.` entity). Digits are sent with `remote.send_command`. Options: at program start or together with the notice; **turn on first** (entity + wait seconds); **remember the channel number** per channel. Defaults (box, delay between digits, extra command like `OK`, turn-on entity) are in *Settings → TV box*.

### Conditions
- **Quiet hours** (Settings): voice and sound are skipped inside the window. Override per reminder with *Ignore quiet hours*.
- **Only if someone is home**: skips voice, sound and channel change unless one of the chosen `person.` entities is `home`.

## 4. Guide (grid)
Channels vertically, time horizontally. ⭐ marks favorites (sorted first, filterable). Click a program for reminder/channel change, a channel for quick channel change or timed switching. Red line = now, 🔔 = reminder exists.

## 5. Home Assistant entities and events
Sensors (virtual, refreshed every minute, recreated after HA restarts):

| Entity | State |
|---|---|
| `sensor.epg_next_reminder` | time of next reminder; attributes `title, channel, start, minutes_until, channel_number, reminder_id, upcoming` |
| `sensor.epg_last_triggered` | time of last trigger; attributes `title, message, channel, number, label` |
| `sensor.epg_active_reminders` | number of active reminders |
| `sensor.epg_last_channel_change` | last channel number; attributes `channel, entity_id, program, changed_at` |

Events:

| Event | Fields |
|---|---|
| `iptv_epg_reminder` | `title, channel, number, start, end, date, time, minutes, label, lead, description, category, reminder_id, message, notification_title` |
| `iptv_epg_tune` | `entity_id, channel_number, channel, program, reminder_id` |
| `iptv_epg_new_titles` | `kind, titles, reminder_id` |

```yaml
trigger:
  - platform: event
    event_type: iptv_epg_reminder
action:
  - service: notify.notify
    data:
      message: "{{ trigger.event.data.title }} on {{ trigger.event.data.channel }}"
```

Tip: exclude the EPG-related entities from the recorder if you do not want their history.

## 5b. Dashboard cards / Languages

**Languages:** the panel can be switched between Swedish, English, German, French, Norwegian and Finnish (buttons at the top right). The Help tab is available in Swedish and English; the other languages show it in English.

**Cards for other dashboards:** `epg-cards.js` contains five cards that read the add-on's sensors (so they also work through Nabu Casa):
`custom:epg-next-card`, `custom:epg-upcoming-card` (`count: 5`), `custom:epg-now-card` (`max: 6`, `tune: true`, optional `entity: remote.tv_box`), `custom:epg-activity-card`, `custom:epg-status-card`. All accept `language: sv|en|de|fr|nb|fi` (default: your Home Assistant language).

1. Download the file from the Settings tab in the add-on (or from `dashboard-cards/epg-cards.js` on GitHub) and copy it to `/config/www/epg-cards.js`.
2. Settings → Dashboards → ⋮ → Resources → add `/local/epg-cards.js` as *JavaScript module* (Advanced mode must be on). Reload the page.
3. Edit a dashboard → Add card → search for **EPG**.

## 5c. Playing TV (media players and in the panel)

Needs an Xtream account (`epg_url`/`xtream_url`) or an M3U playlist (`playlist_url`) – channels from a pure XMLTV source have no stream and show no ▶ button.

- **▶ Play** in search results, channel lists and the guide: choose media player(s) and format and press *Play on device*, or *Watch here* to open the in-panel player.
- **Action "Play channel"** in a reminder: plays the program's channel on the chosen player(s) at the notice or at program start. For time reminders the channel number under *Channel change* decides the channel. It counts as sound (quiet hours and "only if someone is home" apply).
- **Settings → Playback**: default players (also used by the ▶ button in push notifications and by the dashboard card), format and content type. *HLS (.m3u8)* is recommended for Chromecast/Google TV and VLC; *auto* sends `music` to VLC (its integration only accepts that) and the right MIME type to others.
- **Dashboard card**: `epg-now-card` accepts `play: true` (+ optional `play_entity`, `play_format`) and shows a ▶ button per channel. It fires the event `iptv_epg_play` (`channel_id` or `number`, `entity_id`, `fmt`) which you can also fire from your own automations.
- The stream address contains your login. It is sent to the media player but never stored in reminders, history, events or sensors. Many providers allow only one or a few simultaneous streams per account.
- The in-panel player needs an HLS stream (`.m3u8`); plain `.ts` cannot be played by browsers.

## 6. Privacy
- The EPG/IPTV address and credentials exist only in the add-on configuration; the dashboard shows only the host name.
- Credentials are masked in logs and errors.
- All data is stored locally in the add-on's own database.
- The add-on only contacts your EPG/IPTV source and Home Assistant.

## 7. Troubleshooting
| Problem | Try |
|---|---|
| "Error fetching EPG" | Check the address; make sure the password is not masked. |
| No devices to choose | Install/sign in the mobile app; reload the page. |
| No voice/sound | **▶ Test**; check player, TTS engine, volume, quiet hours; URL must be reachable by the player. |
| Channel change fails | Test under *Settings → TV box*; try a longer delay or an extra command (e.g. `OK`). |
| Buttons do nothing | Needs the Companion app; the add-on needs HA API access (default). |
| Sensors missing after restart | They are recreated within a minute. |

---

<a id="svenska"></a>
# Svenska

## 1. Installera och konfigurera

1. Kopiera mappen `iptv_epg_reminder` till `/addons` på Home Assistant (Samba eller SSH).
2. *Inställningar → Tillägg → Tilläggsbutik → ⋮ → Sök efter uppdateringar*, öppna **IPTV EPG Påminnelser** under *Lokala tillägg* och tryck **Installera**.
3. Öppna fliken **Konfiguration** och fyll i din källa (se nedan). Starta tillägget och slå på *Visa i sidofältet*.

| Alternativ | Betydelse |
|---|---|
| `epg_url` | Din XMLTV-/EPG-adress. Sparas bara här och visas aldrig i dashboarden (bara värdnamnet). |
| `xtream_url` | Valfri Xtream Codes-adress för live-/serie-/filmkatalog. Tom = härleds från `epg_url` om den är en Xtream-länk (`xmltv.php`). |
| `playlist_url` | Valfri M3U-reserv för kanallistan. |
| `refresh_hours` | Hur ofta EPG och katalog hämtas. |
| `epg_days` | Antal dagar framåt som sparas. |
| `default_lead_minutes` | Startvärde för ”minuter före start”. |
| `tts_entity` | Standard TTS-motor, t.ex. `tts.home_assistant_cloud`. |
| `language` | Språk vid första start: `sv` eller `en`. Växla när som helst med **SV / EN**. |
| `tts_language` | Språkkod för uppläst text. Tomt = samma som gränssnittet. |

> Lösenord maskas i loggar och felmeddelanden. Kopierar du en maskerad adress (`••••`) misslyckas hämtningen – skriv in det riktiga lösenordet.

## 2. Sök

Separera sökord med komma (ELLER). Uteslut med `-ord`. `*` = valfri text, `?` = ett tecken. Med wildcard måste hela titeln matcha.

| Sökning | Hittar |
|---|---|
| `fotboll` | titlar som innehåller fotboll |
| `fotboll, tennis` | fotboll eller tennis |
| `fotboll, -damer` | fotboll, inte om ”damer” förekommer (titel, kanalnamn eller kategori) |
| `Rapport*` | börjar med Rapport |
| `*final*` | innehåller final |

Flikar: **Live › Program**, **Live › Kanaler**, **Serier**, **Filmer**. Spara en sökning med **＋ Spara sökning**; filtrera på ⭐ favoriter.

## 3. Påminnelser

| Typ | Skapa | Gör |
|---|---|---|
| Program | **🔔 Påminn** på ett resultat eller i tablån | Ett program på en kanal |
| Regel (bevaka) | **Bevaka sökningen / titel / kanal** | Varje matchande program; för serier/filmer varje *ny* matchande titel |
| Tid | **＋ Tidspåminnelse** | Vid ett klockslag: engång, varje dag, mån–fre eller valda dagar – oberoende av EPG |

Ändra med **✎**, ta bort med **✕**, slå av/på regler med reglaget.

### Notis
Typer: **push** (mobilapp), **enkel** (andra notify-tjänster), **persistent** (HA-klockan), **röst (TTS)**, **ingen** (bara kanalbyte/åtgärder).

Med **Knappar i mobilnotisen** får push-notisen **Påminn om N min** och **Byt till kanal N**. Snoozade påminnelser visas som 💤 under *Schemalagt*.

### Egen text och variabler
Skriv **Rubrik** och **Meddelande** själv (tomt = standard). Använd **Infoga**-raden under varje fält.

| Variabel | Svenskt alias | Betydelse |
|---|---|---|
| `{title}` | `{titel}`, `{program}` | Programtitel |
| `{channel}` | `{kanal}` | Kanalnamn |
| `{number}` | `{kanalnummer}` | Kanalnummer |
| `{start}` / `{end}` | `{starttid}` / `{slut}` | Start-/sluttid |
| `{date}` | `{datum}` | Datum (ÅÅÅÅ-MM-DD) |
| `{time}` | `{tid}` | Klockan när den skickas |
| `{minutes}` | `{minuter}` | Minuter till start |
| `{status}` | | Färdig text, t.ex. ”Börjar om 10 min på SVT1 (20:00)” |
| `{label}` | `{etikett}` | Ditt namn på påminnelsen |
| `{lead}` | | Minuter före start som valts |
| `{description}` | `{beskrivning}` | Beskrivning (första 200 tecken) |
| `{category}` | `{kategori}` | Kategori |
| `{reminder_id}` | | Påminnelsens id |

Värden från Home Assistant:

| Syntax | Resultat |
|---|---|
| `{state:sensor.temp_ute}` (alias `{värde:…}`) | entitetens tillstånd |
| `{attr:sensor.temp_ute:unit_of_measurement}` (alias `{attribut:…}`) | ett attribut |
| `{name:person.anna}` (alias `{namn:…}`) | visningsnamn |

Exempel: `{title} börjar om {minutes} min på {channel}. Det är {state:sensor.temp_ute} grader ute.`
Okända variabler lämnas orörda.

### Åtgärder
Lägg till valfritt antal under **Åtgärder**. Varje åtgärd körs **vid notisen** eller **vid programstart** (tidspåminnelser: vid klockslaget). **▶ Testa** kör den direkt.

- **🗣️ Läs upp text** – text med variabler, mediaspelare, valfri volym, TTS-motor och språk.
- **🔔 Spela ljud** – *Fil*: lägg den i HA:s media-mapp och skriv filnamnet (`ding.mp3`, `ljud/ding.mp3`). *URL*: valfri nåbar ljudadress.
- **🛠️ Anropa tjänst** – `domän.tjänst` plus JSON-data; variabler fungerar i textvärden.
  ```json
  light.turn_on
  {"entity_id": "light.living_room", "brightness_pct": 80}
  ```
- **🎚️ Sätt entitet** – `on`/`off` för switch, input_boolean, light …; text för input_text; tal för input_number; alternativ för input_select; andra entiteter får ett virtuellt tillstånd.

### Kanalbyte
Slå på **Växla TV-boxen automatiskt**, ange kanalnummer och TV-box (`remote.`-entitet). Siffrorna skickas med `remote.send_command`. Val: vid programstart eller samtidigt med notisen; **slå på först** (entitet + väntetid i sekunder); **kom ihåg kanalnumret** per kanal. Standardvärden (box, fördröjning mellan siffror, extra kommando som `OK`, entitet att slå på) finns under *Inställningar → TV-box*.

### Villkor
- **Tysta timmar** (Inställningar): röst och ljud hoppas över i tidsfönstret. Överstyr per påminnelse med *Ignorera tysta timmar*.
- **Bara om någon är hemma**: hoppar över röst, ljud och kanalbyte om ingen av de valda `person.`-entiteterna är `home`.

## 4. Tablå (grid)
Kanaler vertikalt, tid horisontellt. ⭐ markerar favoriter (sorteras först, kan filtreras). Klicka på ett program för påminnelse/kanalbyte, på en kanal för snabbt kanalbyte eller tidsstyrning. Rött streck = nu, 🔔 = påminnelse finns.

## 5. Entiteter och events i Home Assistant
Sensorer (virtuella, uppdateras varje minut, skapas om efter HA-omstart):

| Entitet | Tillstånd |
|---|---|
| `sensor.epg_next_reminder` | tid för nästa påminnelse; attribut `title, channel, start, minutes_until, channel_number, reminder_id, upcoming` |
| `sensor.epg_last_triggered` | tid för senaste utlösning; attribut `title, message, channel, number, label` |
| `sensor.epg_active_reminders` | antal aktiva påminnelser |
| `sensor.epg_last_channel_change` | senaste kanalnummer; attribut `channel, entity_id, program, changed_at` |

Events:

| Event | Fält |
|---|---|
| `iptv_epg_reminder` | `title, channel, number, start, end, date, time, minutes, label, lead, description, category, reminder_id, message, notification_title` |
| `iptv_epg_tune` | `entity_id, channel_number, channel, program, reminder_id` |
| `iptv_epg_new_titles` | `kind, titles, reminder_id` |

```yaml
trigger:
  - platform: event
    event_type: iptv_epg_reminder
action:
  - service: notify.notify
    data:
      message: "{{ trigger.event.data.title }} på {{ trigger.event.data.channel }}"
```

Tips: undanta EPG-relaterade entiteter i recorder om du inte vill spara deras historik.

## 5b. Dashboardkort / Språk

**Språk:** panelen kan växlas mellan svenska, engelska, tyska, franska, norska och finska (knapparna uppe till höger). Hjälpfliken finns på svenska och engelska, övriga språk visar den på engelska.

**Kort för andra dashboards:** `epg-cards.js` innehåller fem kort som läser add-onens sensorer (fungerar därför även via Nabu Casa):
`custom:epg-next-card`, `custom:epg-upcoming-card` (`count: 5`), `custom:epg-now-card` (`max: 6`, `tune: true`, valfritt `entity: remote.tv_box`), `custom:epg-activity-card`, `custom:epg-status-card`. Alla tar `language: sv|en|de|fr|nb|fi` (standard: Home Assistants språk).

1. Ladda ner filen under Inställningar i add-onen (eller `dashboard-cards/epg-cards.js` på GitHub) och kopiera den till `/config/www/epg-cards.js`.
2. Inställningar → Dashboards → ⋮ → Resurser → lägg till `/local/epg-cards.js` som *JavaScript-modul* (Avancerat läge måste vara på). Ladda om sidan.
3. Redigera en dashboard → Lägg till kort → sök efter **EPG**.

## 5c. Spela TV (mediaspelare och i panelen)

Kräver ett Xtream-konto (`epg_url`/`xtream_url`) eller en M3U-spellista (`playlist_url`) – kanaler från en ren XMLTV-källa saknar ström och får ingen ▶-knapp.

- **▶ Spela** i sökresultat, kanallistor och tablån: välj mediaspelare och format och tryck *Spela på enhet*, eller *Titta här* för spelaren i panelen.
- **Åtgärden "Spela kanal"** i en påminnelse: spelar programmets kanal på vald(a) mediaspelare vid notisen eller vid programstart. För tidspåminnelser avgör kanalnumret under *Kanalbyte* kanalen. Räknas som ljud (tysta timmar och "bara om någon är hemma" gäller).
- **Inställningar → Uppspelning**: standardspelare (används även av ▶-knappen i push-notiser och av dashboardkortet), format och innehållstyp. *HLS (.m3u8)* rekommenderas för Chromecast/Google TV och VLC; *auto* skickar `music` till VLC (dess integration accepterar bara det) och rätt MIME-typ till övriga.
- **Dashboardkort:** `epg-now-card` tar `play: true` (+ valfritt `play_entity`, `play_format`) och visar en ▶-knapp per kanal. Den skickar eventet `iptv_epg_play` (`channel_id` eller `number`, `entity_id`, `fmt`) som du också kan skicka från egna automationer.
- Strömadressen innehåller din inloggning. Den skickas till mediaspelaren men sparas aldrig i påminnelser, historik, events eller sensorer. Många leverantörer tillåter bara en eller ett par samtidiga strömmar per konto.
- Spelaren i panelen kräver HLS (`.m3u8`); rena `.ts`-strömmar kan inte spelas i webbläsare.

## 6. Integritet
- EPG-/IPTV-adressen och inloggningen finns bara i tilläggets konfiguration; dashboarden visar bara värdnamnet.
- Inloggningsuppgifter maskas i loggar och fel.
- All data lagras lokalt i tilläggets egen databas.
- Tillägget kontaktar bara din EPG-/IPTV-källa och Home Assistant.

## 7. Felsökning
| Problem | Prova |
|---|---|
| ”Fel vid hämtning av EPG” | Kontrollera adressen; se till att lösenordet inte är maskerat. |
| Inga enheter att välja | Installera/logga in mobilappen; ladda om sidan. |
| Ingen röst/ljud | **▶ Testa**; kontrollera spelare, TTS-motor, volym, tysta timmar; URL måste nås av spelaren. |
| Kanalbyte fungerar inte | Testa under *Inställningar → TV-box*; prova längre fördröjning eller extra kommando (t.ex. `OK`). |
| Knapparna gör inget | Kräver Companion-appen; tillägget behöver HA API-åtkomst (standard). |
| Sensorer saknas efter omstart | De skapas om inom en minut. |
