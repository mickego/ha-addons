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

## 5. Manuell installation av kalender och kort

Om add-onet inte når din konfigurationsmapp kopierar du själv `custom_components/reminders_pro` och `www/reminders-pro-cards.js` från add-onets nedladdningsyta, startar om Home Assistant och lägger till `/local/reminders-pro-cards.js` som *JavaScript-modul* under *Dashboards → Resurser*.

## 6. Felsökning

- Inget kommer fram: tryck **Testa** på påminnelsen och titta i **Historik**.
- Tom mottagarlista: add-onet når inte Home Assistant.
- Tider följer Home Assistants tidszon (*Inställningar → System → Allmänt*).
- Export/import under *Inställningar → Data* flyttar dina påminnelser mellan installationer.
