# Reminders Pro · Påminnelser Pro

🇬🇧 [English](#english) · 🇸🇪 [Svenska](#svenska)

---

<a id="english"></a>
# English

## 1. Install

1. Add the repository in Home Assistant: *Settings → Add-ons → Add-on store → ⋮ → Repositories*.
2. Open **Påminnelser Pro**, press **Install**, then **Start** and enable *Show in sidebar*.
3. Open the **Påminnelser** panel. Pick your language top right.

| Option | Meaning |
|---|---|
| `language` | Interface language at first start (`sv`, `en`, `de`, `fr`, `nb`, `fi`). Switch any time in the panel. |
| `tts_entity` | Default TTS engine, e.g. `tts.home_assistant_cloud`. |
| `tts_language` | Language code for spoken text. Empty = same as the interface. |
| `default_snooze_min` | Initial value for the Snooze button. |
| `install_integration` | Copy the calendar integration to your configuration folder (needs one HA restart). |
| `install_card` | Copy the dashboard cards to `/config/www` and register them. |

## 2. Create a reminder

Press **+ New reminder**, then fill in three parts:

1. **What** – title, optional text and category.
2. **When** – *Once* or *Repeating*. A live preview shows the next 10 occurrences.
3. **How should I notify you?** – add one or more ways; all run when the reminder fires.

| You want | Setting |
|---|---|
| Every 3rd day at 08:00, 12:00, 18:00 | Every 3 days · three times |
| Every other week on Monday and Thursday | Every 2 weeks · Mon, Thu |
| Every other month on the 15th | Every 2 months · Specific dates · 15 |
| Last Friday of the month | Every 1 month · Weekday · last · Friday |
| First Monday of the month | Weekday · first · Monday |
| Every year on 3 March | Every 1 year · Months: March · date 3 |
| Every 20 minutes between 08 and 17 | Every 20 minutes · Only between 08:00 and 17:00 |
| Weekdays only | Every 1 day · Only these days: Mon–Fri |

Start, end, "after N times", exception dates and pause are under *When*. Exception and skipped dates do not count towards "after N times". Times of day follow the wall clock through daylight-saving changes (a time that does not exist fires an hour later; a time that occurs twice fires once); "every N minutes/hours" counts real elapsed time.

## 3. Ways to be notified

- **Mobile push** (Companion app) with **Done · Snooze · Skip** buttons
- **Any notify service** – Telegram, e-mail, Signal … (extra data as JSON)
- **Persistent notification**, **voice** (TTS on a media player), **sound** (file in `/media` or URL)
- **Call a service**, **set an entity**, **fire an event**
- Own text: `{title}` `{message}` `{date}` `{time}` `{weekday}` `{n}` `{remaining}` `{next}` `{category}` `{attempt}` and Home Assistant values `{state:sensor.x}`, `{attr:sensor.x:attribute}`, `{name:sensor.x}`

**Repeat until acknowledged:** under *Options*. The notification repeats every N minutes (at most M times) until you press Done, Snooze or Skip – on the phone, in the panel or on a dashboard card.

**Quiet hours / home:** under *Settings*. Postpone until the quiet hours end or skip. "Only if someone is home" uses the people you pick.

## 4. Calendar, sensors and cards

- **Calendar:** with `install_integration` on, restart Home Assistant once, then *Settings → Devices & services → Add integration → Reminders Pro*. You get `calendar.reminders_pro`.
- **Dashboard cards:** `reminders-pro-next-card`, `reminders-pro-today-card`, `reminders-pro-upcoming-card`, `reminders-pro-pending-card`, `reminders-pro-quick-card` – add them from the card picker (search "Reminders Pro"). They read the sensors, so they work through Nabu Casa. The buttons need an administrator user.
- **Own sensor per reminder:** tick *Create its own sensor in HA* under *Options*. You get `sensor.reminders_pro_<name>` (e.g. `sensor.reminders_pro_soptunnan`) whose state is the next occurrence – shown as "in 5 days" in the Companion app and on dashboards. Attributes: `local`, `local_date`, `local_time`, `days_left`, `hours_until`, `upcoming` (next 5), `last_fired`, `paused_until`. Use it in a text with `{state:sensor.reminders_pro_soptunnan}` or in an entities card.
- **Sensors:** `sensor.reminders_pro_next`, `_today`, `_active`, `_unacknowledged`, `_last`, `binary_sensor.reminders_pro_attention`.
- **Events:** `reminders_pro_fired`, `reminders_pro_done`, `reminders_pro_snoozed`, `reminders_pro_skipped`, `reminders_pro_unacknowledged`.
- **Commands** (event `reminders_pro_command`): `{"cmd":"quick","title":"Pasta ready","minutes":10}`, `{"cmd":"done","token":"…"}`, `{"cmd":"trigger","id":3}`, `{"cmd":"pause","id":3,"days":2}`, `{"cmd":"resume","id":3}`.

Automation example:

```yaml
- alias: Reminder on the TV
  trigger:
    - platform: event
      event_type: reminders_pro_fired
  action:
    - service: notify.living_room_tv
      data:
        message: "{{ trigger.event.data.title }} – {{ trigger.event.data.message }}"
```

## 4b. Own buttons, Android TV and conditions

**Own buttons (mobile push).** Under *Options → Buttons in the mobile notification* press **+ Own button** and choose what should happen: toggle / turn on / turn off an entity, start an automation, run a script, activate a scene, press a button entity, call a service (with JSON data), set an entity to a value, or fire an event. "After the press" decides whether the reminder is also marked as done. Your buttons are shown first, then Done / Snooze / Skip (untick the ones you do not want). The Android app shows at most 3 buttons in total.

**Android TV / Fire TV.** Add the way *Android TV / Fire TV notification* and pick the notify service from the *Notifications for Android TV* integration (`nfandroidtv`). Optional: duration, position, text size, transparency, colour, icon and image URL. Extra JSON is merged into `data`.

**Conditions (exceptions on entity state).** Under *Options → Conditions* choose **Only send if …** or **Skip if …**, whether *all* or *any* of the conditions must match, and add rows: entity, optional attribute, comparison (equals, is not, greater than, at least, less than, at most, contains, is one of) and value. Examples: `sensor.outdoor_temp` less than `5`; `person.anna` equals `home`; `sensor.x` is one of `on, open`. The value may use variables, e.g. `{state:input_number.limit}`. A skipped reminder appears in History as *Condition not met*. Test runs ignore conditions.

Pressing a custom button fires the event `reminders_pro_button` (`label`, `index`, `token`, `title`). You can also press a button from an automation: event `reminders_pro_command` with `{"cmd":"button","token":"…","index":0}`.

## 4c. Advance notice, after-last-done, entity triggers and category sensors

- **Advance notice:** Options → Advance notice. Add one or more "N minutes/hours/days/weeks before". Works for every reminder. Use `{age}` with a birth year, e.g. "{title} turns {age}".
- **After last done:** under *When* choose *After last done*. The next occurrence is counted from the day you press Done (or *Done now*).
- **From an entity:** under *When* choose *From an entity*. Fires when the conditions are met (optionally for at least N minutes); fires again only after they were unmet in between, with an optional cooldown.
- **Category sensor:** Settings → tick 📅 on a category. `sensor.reminders_pro_<category>` shows the next reminder with title, days left and date.

## 5. Manual installation of calendar and cards

If the add-on cannot reach your configuration folder, copy `custom_components/reminders_pro` and `www/reminders-pro-cards.js` from the add-on's download area yourself, restart Home Assistant and add `/local/reminders-pro-cards.js` as a *JavaScript module* under *Dashboards → Resources*.

## 6. Troubleshooting

- Nothing arrives: press **Test** on the reminder and check **History**.
- Empty recipient list: the add-on cannot reach Home Assistant.
- Times follow Home Assistant's time zone (*Settings → System → General*).
- Export/import under *Settings → Data* moves your reminders between installations.

---

<a id="svenska"></a>
# Svenska

## 1. Installera

1. Lägg till förrådet i Home Assistant: *Inställningar → Add-ons → Add-on store → ⋮ → Förråd*.
2. Öppna **Påminnelser Pro**, tryck **Installera**, sedan **Starta** och slå på *Visa i sidofältet*.
3. Öppna panelen **Påminnelser**. Välj språk uppe till höger.

| Alternativ | Betydelse |
|---|---|
| `language` | Språk vid första start (`sv`, `en`, `de`, `fr`, `nb`, `fi`). Kan växlas i panelen. |
| `tts_entity` | Standard TTS-motor, t.ex. `tts.home_assistant_cloud`. |
| `tts_language` | Språkkod för uppläst text. Tomt = samma som gränssnittet. |
| `default_snooze_min` | Startvärde för Snooze-knappen. |
| `install_integration` | Kopiera kalenderintegrationen till din konfigurationsmapp (kräver en omstart av HA). |
| `install_card` | Kopiera dashboardkorten till `/config/www` och registrera dem. |

## 2. Skapa en påminnelse

Tryck **+ Ny påminnelse** och fyll i tre delar:

1. **Vad** – rubrik, valfri text och kategori.
2. **När** – *En gång* eller *Återkommande*. En live-förhandsvisning visar de nästa 10 tillfällena.
3. **Hur ska jag meddelas?** – lägg till ett eller flera sätt; alla körs när påminnelsen utlöses.

| Önskemål | Inställning |
|---|---|
| Var 3:e dag 08:00, 12:00, 18:00 | Var 3 dagar · tre klockslag |
| Varannan vecka måndag och torsdag | Var 2 veckor · mån, tors |
| Varannan månad den 15:e | Var 2 månader · Bestämda datum · 15 |
| Sista fredagen i månaden | Var 1 månad · Veckodag · sista · fredag |
| Första måndagen i månaden | Veckodag · första · måndag |
| Varje år 3 mars | Var 1 år · Månader: mars · dag 3 |
| Var 20:e minut mellan 08 och 17 | Var 20 minuter · Bara mellan 08:00 och 17:00 |
| Bara vardagar | Var 1 dag · Bara dessa dagar: mån–fre |

Start, slut, ”efter N gånger”, undantagsdatum och paus finns under *När*. Undantagna och överhoppade datum räknas inte mot ”efter N gånger”. Klockslag följer väggklockan genom sommar-/vintertid (ett klockslag som saknas skickas en timme senare; ett som finns två gånger skickas en gång); ”var N:e minut/timme” räknar verklig förfluten tid.

## 3. Sätt att meddelas

- **Mobilpush** (Companion-appen) med knapparna **Klart · Snooze · Hoppa över**
- **Valfri notify-tjänst** – Telegram, e-post, Signal … (extra data som JSON)
- **Persistent notis**, **röst** (TTS på en mediaspelare), **ljud** (fil i `/media` eller webbadress)
- **Anropa tjänst**, **sätt entitet**, **skicka event**
- Egen text: `{title}` `{message}` `{date}` `{time}` `{weekday}` `{n}` `{remaining}` `{next}` `{category}` `{attempt}` samt värden från Home Assistant `{state:sensor.x}`, `{attr:sensor.x:attribut}`, `{name:sensor.x}` (svenska alias som `{titel}`, `{datum}`, `{tid}` fungerar också)

**Upprepa tills kvitterat:** under *Alternativ*. Notisen upprepas var N:e minut (högst M gånger) tills du trycker Klart, Snooze eller Hoppa över – i mobilen, i panelen eller på ett dashboardkort.

**Tysta timmar / hemma:** under *Inställningar*. Skjut upp tills de tysta timmarna är slut eller hoppa över. ”Bara om någon är hemma” använder de personer du väljer.

## 4. Kalender, sensorer och kort

- **Kalender:** med `install_integration` på startar du om Home Assistant en gång, sedan *Inställningar → Enheter och tjänster → Lägg till integration → Reminders Pro*. Du får `calendar.reminders_pro`.
- **Dashboardkort:** `reminders-pro-next-card`, `reminders-pro-today-card`, `reminders-pro-upcoming-card`, `reminders-pro-pending-card`, `reminders-pro-quick-card` – lägg till från kortväljaren (sök ”Reminders Pro”). De läser sensorerna och fungerar därför via Nabu Casa. Knapparna kräver en administratörsanvändare.
- **Egen sensor per påminnelse:** bocka i *Skapa en egen sensor i HA* under *Alternativ*. Du får `sensor.reminders_pro_<namn>` (t.ex. `sensor.reminders_pro_soptunnan`) vars värde är nästa tillfälle – visas som "om 5 dagar" i Companion-appen och på dashboards. Attribut: `local`, `local_date`, `local_time`, `days_left`, `hours_until`, `upcoming` (nästa 5), `last_fired`, `paused_until`. Använd den i en text med `{state:sensor.reminders_pro_soptunnan}` eller i ett entitetskort.
- **Sensorer:** `sensor.reminders_pro_next`, `_today`, `_active`, `_unacknowledged`, `_last`, `binary_sensor.reminders_pro_attention`.
- **Events:** `reminders_pro_fired`, `reminders_pro_done`, `reminders_pro_snoozed`, `reminders_pro_skipped`, `reminders_pro_unacknowledged`.
- **Kommandon** (event `reminders_pro_command`): `{"cmd":"quick","title":"Pasta klar","minutes":10}`, `{"cmd":"done","token":"…"}`, `{"cmd":"trigger","id":3}`, `{"cmd":"pause","id":3,"days":2}`, `{"cmd":"resume","id":3}`.

Automationsexempel:

```yaml
- alias: Påminnelse på TV:n
  trigger:
    - platform: event
      event_type: reminders_pro_fired
  action:
    - service: notify.vardagsrum_tv
      data:
        message: "{{ trigger.event.data.title }} – {{ trigger.event.data.message }}"
```

## 4b. Egna knappar, Android TV och villkor

**Egna knappar (mobilpush).** Under *Alternativ → Knappar i mobilnotisen* trycker du **+ Egen knapp** och väljer vad som ska hända: växla / slå på / slå av en entitet, starta en automation, köra ett skript, aktivera en scen, trycka på en knapp-entitet, anropa en tjänst (med JSON-data), sätta en entitet till ett värde eller skicka ett event. ”Efter tryck” avgör om påminnelsen också markeras som klar. Dina knappar visas först, sedan Klart / Snooze / Hoppa över (bocka ur de du inte vill ha). Androidappen visar högst 3 knappar totalt.

**Android TV / Fire TV.** Lägg till sättet *Android TV / Fire TV-notis* och välj notify-tjänsten från integrationen *Notifications for Android TV* (`nfandroidtv`). Valfritt: visningstid, position, textstorlek, genomskinlighet, färg samt ikon och bild (webbadress). Extra JSON slås ihop med `data`.

**Villkor (undantag på entitetsstatus).** Under *Alternativ → Villkor* väljer du **Skicka bara om …** eller **Hoppa över om …**, om *alla* eller *något* villkor ska stämma, och lägger till rader: entitet, valfritt attribut, jämförelse (är lika med, är inte, större än, minst, mindre än, högst, innehåller, är någon av) och värde. Exempel: `sensor.utetemp` mindre än `5`; `person.anna` är lika med `home`; `sensor.x` är någon av `on, open`. Värdet får innehålla variabler, t.ex. `{state:input_number.gräns}`. En överhoppad påminnelse syns i Historik som *Villkor ej uppfyllt*. Testkörning ignorerar villkor.

När en egen knapp trycks skickas eventet `reminders_pro_button` (`label`, `index`, `token`, `title`). Du kan också trycka en knapp från en automation: event `reminders_pro_command` med `{"cmd":"button","token":"…","index":0}`.

## 4c. Förvarning, efter senast utfört, entitetsutlösare och kategorisensorer

- **Förvarning:** Alternativ → Förvarning. Lägg till en eller flera ”N minuter/timmar/dagar/veckor före”. Gäller alla påminnelser. Använd `{age}` med födelseår, t.ex. ”{title} fyller {age} år”.
- **Efter senast utfört:** välj *Efter senast utfört* under *När*. Nästa tillfälle räknas från den dag du trycker Klart (eller *Utfört nu*).
- **Från en entitet:** välj *Från en entitet* under *När*. Utlöses när villkoren uppfylls (valfritt i minst N minuter) och igen först när de varit ouppfyllda emellan, med valfri spärrtid.
- **Kategorisensor:** Inställningar → bocka 📅 vid en kategori. `sensor.reminders_pro_<kategori>` visar nästa påminnelse med titel, dagar kvar och datum.

## 5. Manuell installation av kalender och kort

Om add-onet inte når din konfigurationsmapp kopierar du själv `custom_components/reminders_pro` och `www/reminders-pro-cards.js` från add-onets nedladdningsyta, startar om Home Assistant och lägger till `/local/reminders-pro-cards.js` som *JavaScript-modul* under *Dashboards → Resurser*.

## 6. Felsökning

- Inget kommer fram: tryck **Testa** på påminnelsen och titta i **Historik**.
- Tom mottagarlista: add-onet når inte Home Assistant.
- Tider följer Home Assistants tidszon (*Inställningar → System → Allmänt*).
- Export/import under *Inställningar → Data* flyttar dina påminnelser mellan installationer.
