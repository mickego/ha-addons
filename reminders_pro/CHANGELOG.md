# Changelog

## 1.4.0
- **Calendar view** in the app: new Calendar tab with month and week view, coloured by category. Click a day to see, edit or add reminders. Categories hidden from "All" are excluded

## 1.3.2
- **Hide a category from "All":** tick 🙈 on a category in Settings (e.g. a "Templates" category). Help describes how to use a category as templates

## 1.3.1
- Help extended: variables, `{state:…}`, `{attr:…:…}`, `{name:…}` with examples

## 1.3.0
- **Advance notice for any reminder:** add e.g. "7 days before" and "1 day before" under Options. An extra notification (without buttons) is sent before each occurrence. New variable `{age}` with an optional birth/start year ("{title} turns {age}")
- **After last done:** new mode where the next occurrence is counted from the day you press Done (or "Done now" on the card) – for filter changes and similar. New command `{"cmd":"done_now","id":…}`
- **From an entity:** the reminder fires when entity conditions are met (optionally held for N minutes, with cooldown) and again only after the conditions were unmet in between
- **Category sensor:** tick 📅 on a category in Settings to get `sensor.reminders_pro_<category>` with the next reminder's title, days left and date
- New history entry *Advance notice sent*

## 1.2.0
- **Own sensor per reminder:** tick "Create its own sensor in HA" under Options. You get `sensor.reminders_pro_<name>` whose state is the next occurrence (timestamp – shows e.g. "in 5 days" in the app and dashboards) with attributes `local`, `local_date`, `local_time`, `days_left`, `hours_until`, `upcoming` (next 5), `last_fired`, `paused_until` and more. Respects pause, skip-next and exceptions

## 1.1.0
- **Own buttons in the mobile notification:** toggle / turn on / turn off an entity, start an automation, run a script, activate a scene, press a button entity, call any service, set an entity or fire an event. Optionally acknowledge the reminder on press. Choose which of Done · Snooze · Skip to keep (Android shows 3 buttons in total)
- **Android TV / Fire TV notification** (Notifications for Android TV): duration, position, text size, transparency, colour, icon and image
- **Conditions on entity state:** only send if / skip if, all or any of several conditions (equals, is not, greater/less than, contains, is one of), on state or attribute, values may use variables
- New history entries *Button pressed* and *Condition not met*, new event `reminders_pro_button` and command `{"cmd":"button","token":"…","index":0}

## 1.0.0
First release of **Reminders Pro · Påminnelser Pro** – a pure reminder add-on (nothing to do with EPG).
- Fully dynamic repeats: every N minutes / hours / days / weeks / months / years; several times per day, repeated times (every 20 min between 08 and 17), weekdays, specific month days, "last Friday", "first Monday", yearly dates
- Start, end, "after N times", exception dates, pause; correct daylight-saving handling
- No-code form with a live preview of the next 10 occurrences
- Notifications: mobile push with **Done · Snooze · Skip** buttons, repeat until acknowledged, persistent notification, voice (TTS), sound, any `notify` service (Telegram, e-mail …), call a service, set an entity, fire an event, own text with variables and entity values
- Quiet hours (postpone or skip) and "only if someone is home"
- Calendar entity `calendar.reminders_pro`, sensors, events, command event `reminders_pro_command`
- Dashboard cards (next, today, upcoming, acknowledge, quick) that also work through Nabu Casa
- Categories with colours, export / import
- Interface languages: Swedish, English, German, French, Norwegian, Finnish
