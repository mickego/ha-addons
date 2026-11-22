/*  Reminders Pro – dashboard cards for Home Assistant (Lovelace)
 *  Cards: reminders-pro-next-card, reminders-pro-today-card, reminders-pro-upcoming-card,
 *         reminders-pro-pending-card (Done / Snooze / Skip), reminders-pro-quick-card
 *  Data comes from the add-on's sensors, so it works remotely (Nabu Casa) too.
 *  Install: the add-on copies this file to /config/www/reminders-pro-cards.js and registers the resource
 *  (or add /local/reminders-pro-cards.js as a "JavaScript module" under Dashboards → Resources).
 *  The buttons send the event reminders_pro_command (needs an administrator user).
 */
const T = {
  sv: {next: "Nästa påminnelse", none: "Inga kommande påminnelser", today: "Idag", nothing_today: "Inget idag", upcoming: "Kommande", pending: "Väntar på kvittens", nopending: "Allt kvitterat ✓", done: "Klart", snooze: "Snooze", skip: "Hoppa över", quick: "Snabbpåminnelse", ph: "Vad ska jag påminna om?", add: "Lägg till", min: "min", in: "om", sent: "skickad", err: "Kunde inte skicka (kräver administratör)", ok: "Skickat", missing: "Hittar inte sensorn", fired: "utlöst", missed: "missad", skipped: "överhoppad"},
  en: {next: "Next reminder", none: "No upcoming reminders", today: "Today", nothing_today: "Nothing today", upcoming: "Upcoming", pending: "Waiting for acknowledgement", nopending: "All acknowledged ✓", done: "Done", snooze: "Snooze", skip: "Skip", quick: "Quick reminder", ph: "What should I remind you about?", add: "Add", min: "min", in: "in", sent: "sent", err: "Could not send (administrator required)", ok: "Sent", missing: "Sensor not found", fired: "fired", missed: "missed", skipped: "skipped"},
  de: {next: "Nächste Erinnerung", none: "Keine anstehenden Erinnerungen", today: "Heute", nothing_today: "Heute nichts", upcoming: "Anstehend", pending: "Wartet auf Bestätigung", nopending: "Alles bestätigt ✓", done: "Erledigt", snooze: "Schlummern", skip: "Überspringen", quick: "Schnellerinnerung", ph: "Woran soll ich erinnern?", add: "Hinzufügen", min: "Min", in: "in", sent: "gesendet", err: "Senden fehlgeschlagen (Administrator nötig)", ok: "Gesendet", missing: "Sensor nicht gefunden", fired: "ausgelöst", missed: "verpasst", skipped: "übersprungen"},
  fr: {next: "Prochain rappel", none: "Aucun rappel à venir", today: "Aujourd'hui", nothing_today: "Rien aujourd'hui", upcoming: "À venir", pending: "En attente d'acquittement", nopending: "Tout est acquitté ✓", done: "Fait", snooze: "Reporter", skip: "Ignorer", quick: "Rappel rapide", ph: "De quoi dois-je vous rappeler ?", add: "Ajouter", min: "min", in: "dans", sent: "envoyé", err: "Échec de l'envoi (administrateur requis)", ok: "Envoyé", missing: "Capteur introuvable", fired: "déclenché", missed: "manqué", skipped: "ignoré"},
  nb: {next: "Neste påminnelse", none: "Ingen kommende påminnelser", today: "I dag", nothing_today: "Ingenting i dag", upcoming: "Kommende", pending: "Venter på kvittering", nopending: "Alt kvittert ✓", done: "Ferdig", snooze: "Utsett", skip: "Hopp over", quick: "Hurtigpåminnelse", ph: "Hva skal jeg minne deg på?", add: "Legg til", min: "min", in: "om", sent: "sendt", err: "Kunne ikke sende (krever administrator)", ok: "Sendt", missing: "Fant ikke sensoren", fired: "utløst", missed: "glemt", skipped: "hoppet over"},
  fi: {next: "Seuraava muistutus", none: "Ei tulevia muistutuksia", today: "Tänään", nothing_today: "Ei mitään tänään", upcoming: "Tulevat", pending: "Odottaa kuittausta", nopending: "Kaikki kuitattu ✓", done: "Valmis", snooze: "Torkuta", skip: "Ohita", quick: "Pikamuistutus", ph: "Mistä muistutan?", add: "Lisää", min: "min", in: "", sent: "lähetetty", err: "Lähetys epäonnistui (vaatii ylläpitäjän)", ok: "Lähetetty", missing: "Sensoria ei löydy", fired: "laukaistu", missed: "ohi", skipped: "ohitettu"},
};
const CSS = `
:host{display:block}
ha-card{padding:14px 16px;display:block}
.h{display:flex;align-items:center;gap:8px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--secondary-text-color);margin-bottom:8px}
.h .ic{color:var(--primary-color)}
.big{font-size:20px;font-weight:600;line-height:1.25;color:var(--primary-text-color)}
.sub{color:var(--secondary-text-color);font-size:13px;margin-top:2px}
.row{display:flex;align-items:center;gap:10px;padding:7px 0;border-top:1px solid var(--divider-color)}
.row:first-of-type{border-top:0}
.dot{width:10px;height:10px;border-radius:50%;flex:none;background:var(--primary-color)}
.tm{min-width:48px;font-weight:600;color:var(--primary-color);font-variant-numeric:tabular-nums}
.grow{flex:1;min-width:0}.t{font-weight:600;color:var(--primary-text-color);overflow:hidden;text-overflow:ellipsis}
.s{font-size:12.5px;color:var(--secondary-text-color)}
.past{opacity:.55}.past .t{text-decoration:line-through}
button{font:inherit;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);border-radius:10px;padding:6px 12px;cursor:pointer}
button.p{background:var(--primary-color);color:var(--text-primary-color,#fff);border-color:var(--primary-color)}
select,input{font:inherit;border:1px solid var(--divider-color);border-radius:10px;padding:6px 8px;background:var(--card-background-color);color:var(--primary-text-color);min-width:0}
.acts{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.empty{color:var(--secondary-text-color);padding:6px 0}
.msg{font-size:12px;color:var(--secondary-text-color);margin-top:6px}
`;
const lang = h => { const l = ((h && (h.language || (h.locale && h.locale.language))) || "en").slice(0, 2).toLowerCase(); return l === "no" ? "nb" : (T[l] ? l : "en"); };
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

class RPBase extends HTMLElement {
  setConfig(c) { this._c = Object.assign({}, this.constructor.defaults || {}, c || {}); if (!this.shadowRoot) this.attachShadow({mode: "open"}); this._built = false; this._render(); }
  set hass(h) { this._h = h; this._render(); }
  getCardSize() { return 3; }
  get tr() { return T[lang(this._h)]; }
  fmt(iso, o) {
    try { return new Intl.DateTimeFormat((this._h && this._h.language) || undefined, Object.assign({timeZone: this._h && this._h.config && this._h.config.time_zone}, o || {weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"})).format(new Date(iso)); } catch (e) { return iso; }
  }
  rel(iso) {
    const d = (new Date(iso) - Date.now()) / 1000, rf = new Intl.RelativeTimeFormat((this._h && this._h.language) || undefined, {numeric: "auto"}), a = Math.abs(d);
    return a < 3600 ? rf.format(Math.round(d / 60), "minute") : a < 172800 ? rf.format(Math.round(d / 3600), "hour") : rf.format(Math.round(d / 86400), "day");
  }
  st(id) { return this._h && this._h.states[id]; }
  async cmd(data) {
    try { await this._h.connection.sendMessagePromise({type: "fire_event", event_type: "reminders_pro_command", event_data: data}); this.flash(this.tr.ok); return true; }
    catch (e) { this.flash(this.tr.err); return false; }
  }
  flash(m) { const e = this.shadowRoot.querySelector(".msg"); if (e) { e.textContent = m; setTimeout(() => { if (e.textContent === m) e.textContent = ""; }, 3000); } }
  frame(icon, title, body) { return `<style>${CSS}</style><ha-card><div class="h"><span class="ic">${icon}</span>${esc(title)}</div>${body}<div class="msg"></div></ha-card>`; }
  _render() { if (!this._h || !this._c || !this.shadowRoot) return; const html = this.html(); if (html !== this._last) { this._last = html; this.shadowRoot.innerHTML = html; this.bind && this.bind(); } }
}

class RPNext extends RPBase {
  static get defaults() { return {entity: "sensor.reminders_pro_next"}; }
  html() {
    const s = this.st(this._c.entity), tr = this.tr;
    if (!s) return this.frame("🔔", this._c.title || tr.next, `<div class="empty">${tr.missing}: ${esc(this._c.entity)}</div>`);
    const a = s.attributes || {};
    if (s.state === "unknown" || s.state === "unavailable" || !a.title) return this.frame("🔔", this._c.title || tr.next, `<div class="empty">${tr.none}</div>`);
    return this.frame("🔔", this._c.title || tr.next, `<div class="row" style="border:0"><span class="dot" style="background:${esc(a.color || "var(--primary-color)")}"></span><div class="grow"><div class="big">${esc(a.title)}</div><div class="sub">${esc(this.fmt(s.state))} · ${esc(this.rel(s.state))}${a.category ? " · " + esc(a.category) : ""}</div>${a.message ? `<div class="sub">${esc(a.message)}</div>` : ""}</div></div>`);
  }
  static getStubConfig() { return {}; }
}
class RPUpcoming extends RPBase {
  static get defaults() { return {entity: "sensor.reminders_pro_next", count: 6}; }
  html() {
    const s = this.st(this._c.entity), tr = this.tr;
    const list = ((s && s.attributes && s.attributes.upcoming) || []).slice(0, this._c.count);
    return this.frame("📅", this._c.title || tr.upcoming, list.length ? list.map(u => `<div class="row"><span class="dot" style="background:${esc(u.color || "var(--primary-color)")}"></span><div class="grow"><div class="t">${esc(u.title)}</div><div class="s">${esc(this.fmt(u.at))} · ${esc(this.rel(u.at))}</div></div></div>`).join("") : `<div class="empty">${tr.none}</div>`);
  }
  getCardSize() { return 1 + Math.min(this._c.count, 6); }
}
class RPToday extends RPBase {
  static get defaults() { return {entity: "sensor.reminders_pro_today", hide_done: false}; }
  html() {
    const s = this.st(this._c.entity), tr = this.tr;
    let items = ((s && s.attributes && s.attributes.items) || []);
    if (this._c.hide_done) items = items.filter(i => i.status === "upcoming");
    const ic = {upcoming: "⏳", fired: "🔔", done: "✓", skipped: "⤼", missed: "⚠️", quiet_skip: "🔕", home_skip: "🏠", cond_skip: "🚫", error: "⚠️"};
    return this.frame("🗓️", this._c.title || tr.today, items.length ? items.map(i => `<div class="row ${i.status === "upcoming" ? "" : "past"}"><span class="tm">${esc(i.time)}</span><span class="dot" style="background:${esc(i.color || "var(--primary-color)")}"></span><div class="grow"><div class="t">${esc(i.title)}</div></div><span title="${esc(tr[i.status] || "")}">${ic[i.status] || ""}</span></div>`).join("") : `<div class="empty">${tr.nothing_today}</div>`);
  }
  getCardSize() { return 3; }
}
class RPPending extends RPBase {
  static get defaults() { return {entity: "sensor.reminders_pro_unacknowledged", snooze: [5, 10, 30, 60]}; }
  html() {
    const s = this.st(this._c.entity), tr = this.tr;
    const items = ((s && s.attributes && s.attributes.items) || []);
    return this.frame("🔔", this._c.title || tr.pending, items.length ? items.map(i => `<div class="row" style="align-items:flex-start"><span class="dot" style="margin-top:6px;background:${esc(i.color || "var(--primary-color)")}"></span><div class="grow"><div class="t">${esc(i.title)}</div><div class="s">${esc(this.fmt(i.since))}${i.sent ? " · " + tr.sent + " " + i.sent + "×" : ""}</div>
      <div class="acts"><button class="p" data-a="done" data-t="${esc(i.token)}">✓ ${tr.done}</button><select data-a="snooze" data-t="${esc(i.token)}"><option value="">💤 ${tr.snooze}</option>${this._c.snooze.map(m => `<option value="${m}">${m} ${tr.min}</option>`).join("")}</select><button data-a="skip" data-t="${esc(i.token)}">${tr.skip}</button></div></div></div>`).join("") : `<div class="empty">${tr.nopending}</div>`);
  }
  bind() {
    this.shadowRoot.querySelectorAll("button[data-a]").forEach(b => b.addEventListener("click", () => this.cmd({cmd: b.dataset.a, token: b.dataset.t})));
    this.shadowRoot.querySelectorAll("select[data-a]").forEach(x => x.addEventListener("change", () => { if (x.value) this.cmd({cmd: "snooze", token: x.dataset.t, minutes: +x.value}); }));
  }
  getCardSize() { return 3; }
}
class RPQuick extends RPBase {
  static get defaults() { return {minutes: [5, 10, 30, 60], targets: []}; }
  html() {
    const tr = this.tr;
    return this.frame("⚡", this._c.title || tr.quick, `<div style="display:flex;gap:6px;flex-wrap:wrap"><input class="q" type="text" placeholder="${esc(tr.ph)}" style="flex:1;min-width:150px"><select class="m">${this._c.minutes.map(m => `<option value="${m}"${m === 10 ? " selected" : ""}>${tr.in} ${m} ${tr.min}</option>`).join("")}</select><button class="p">${tr.add}</button></div>`);
  }
  bind() {
    const q = this.shadowRoot.querySelector(".q"), m = this.shadowRoot.querySelector(".m");
    const go = async () => { const title = q.value.trim(); if (!title) return; const d = {cmd: "quick", title, minutes: +m.value}; if (this._c.targets && this._c.targets.length) d.targets = this._c.targets; if (await this.cmd(d)) q.value = ""; };
    this.shadowRoot.querySelector("button").addEventListener("click", go);
    q.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  }
  _render() { if (!this._h || !this._c || !this.shadowRoot) return; if (!this._built) { this._built = true; this.shadowRoot.innerHTML = this.html(); this.bind(); } }
}
const CARDS = [["reminders-pro-next-card", RPNext, "Reminders Pro – next", "The next reminder"], ["reminders-pro-upcoming-card", RPUpcoming, "Reminders Pro – upcoming", "List of upcoming reminders"],
  ["reminders-pro-today-card", RPToday, "Reminders Pro – today", "Today's reminders with status"], ["reminders-pro-pending-card", RPPending, "Reminders Pro – acknowledge", "Done / Snooze / Skip for waiting reminders"],
  ["reminders-pro-quick-card", RPQuick, "Reminders Pro – quick", "Create a quick reminder"]];
window.customCards = window.customCards || [];
for (const [tag, cls, name, desc] of CARDS) { if (!customElements.get(tag)) customElements.define(tag, cls); window.customCards.push({type: tag, name, description: desc, preview: false}); }
console.info("%c REMINDERS-PRO-CARDS %c loaded", "background:#3b6ef5;color:#fff;padding:2px 6px;border-radius:4px 0 0 4px", "background:#222;color:#fff;padding:2px 6px;border-radius:0 4px 4px 0");
