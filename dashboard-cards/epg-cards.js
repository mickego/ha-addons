/*  IPTV EPG Reminders – dashboard cards for Home Assistant (Lovelace)
 *  Cards: epg-next-card, epg-upcoming-card, epg-now-card, epg-activity-card, epg-status-card
 *  Data comes from the add-on's sensors – works remotely (Nabu Casa) too.
 *  Install: copy to /config/www/epg-cards.js, then Settings → Dashboards → ⋮ → Resources →
 *  add /local/epg-cards.js as "JavaScript module".  Add cards in the card picker (search "EPG").
 */
const T = {
  sv: { play: "▶ Spela", played: "✓", next: "Nästa påminnelse", none: "Inga kommande påminnelser", upcoming: "Kommande påminnelser", now: "Just nu", next_l: "Sen",
        last: "Senast utlöst", lastch: "Senaste kanalbyte", active: "Aktiva påminnelser", sched: "Schemalagda (7 d)", on: "Nu", ch: "kanal",
        tune: "Byt kanal", nofav: "Inga favoriter/kanalnummer sparade i add-onen", min: "min", soon: "nu", never: "Inget ännu", tv: "TV-box saknas i add-onens inställningar", sent: "Kanalbyte skickat" },
  en: { play: "▶ Play", played: "✓", next: "Next reminder", none: "No upcoming reminders", upcoming: "Upcoming reminders", now: "On now", next_l: "Next",
        last: "Last triggered", lastch: "Last channel change", active: "Active reminders", sched: "Scheduled (7 d)", on: "Now", ch: "channel",
        tune: "Change channel", nofav: "No favorites/channel numbers saved in the add-on", min: "min", soon: "now", never: "Nothing yet", tv: "No TV box set in the add-on settings", sent: "Channel change sent" },
  de: { play: "▶ Abspielen", played: "✓", next: "Nächste Erinnerung", none: "Keine anstehenden Erinnerungen", upcoming: "Anstehende Erinnerungen", now: "Läuft jetzt", next_l: "Danach",
        last: "Zuletzt ausgelöst", lastch: "Letzter Senderwechsel", active: "Aktive Erinnerungen", sched: "Geplant (7 T)", on: "Jetzt", ch: "Sender",
        tune: "Sender wechseln", nofav: "Keine Favoriten/Sendernummern im Add-on gespeichert", min: "Min", soon: "jetzt", never: "Noch nichts", tv: "Keine TV-Box in den Add-on-Einstellungen", sent: "Senderwechsel gesendet" },
  fr: { play: "▶ Lire", played: "✓", next: "Prochain rappel", none: "Aucun rappel à venir", upcoming: "Rappels à venir", now: "En cours", next_l: "Ensuite",
        last: "Dernier déclenché", lastch: "Dernier changement de chaîne", active: "Rappels actifs", sched: "Planifiés (7 j)", on: "Maintenant", ch: "chaîne",
        tune: "Changer de chaîne", nofav: "Aucun favori/numéro de chaîne enregistré dans l'add-on", min: "min", soon: "maintenant", never: "Rien pour l'instant", tv: "Aucune box TV dans les paramètres de l'add-on", sent: "Changement de chaîne envoyé" },
  nb: { play: "▶ Spill av", played: "✓", next: "Neste påminnelse", none: "Ingen kommende påminnelser", upcoming: "Kommende påminnelser", now: "På nå", next_l: "Deretter",
        last: "Sist utløst", lastch: "Siste kanalbytte", active: "Aktive påminnelser", sched: "Planlagt (7 d)", on: "Nå", ch: "kanal",
        tune: "Bytt kanal", nofav: "Ingen favoritter/kanalnumre lagret i tillegget", min: "min", soon: "nå", never: "Ingenting ennå", tv: "Ingen TV-boks i tilleggets innstillinger", sent: "Kanalbytte sendt" },
  fi: { play: "▶ Toista", played: "✓", next: "Seuraava muistutus", none: "Ei tulevia muistutuksia", upcoming: "Tulevat muistutukset", now: "Menossa nyt", next_l: "Sen jälkeen",
        last: "Viimeksi laukaistu", lastch: "Viimeisin kanavanvaihto", active: "Aktiiviset muistutukset", sched: "Ajastetut (7 pv)", on: "Nyt", ch: "kanava",
        tune: "Vaihda kanava", nofav: "Lisäosaan ei ole tallennettu suosikkeja/kanavanumeroita", min: "min", soon: "nyt", never: "Ei vielä mitään", tv: "Lisäosan asetuksissa ei ole TV-boksia", sent: "Kanavanvaihto lähetetty" },
};
const CSS = `
:host{display:block}
ha-card{padding:14px 16px}
.h{display:flex;align-items:center;gap:8px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--secondary-text-color);margin-bottom:8px}
.h ha-icon{--mdc-icon-size:18px;color:var(--primary-color)}
.big{font-size:20px;font-weight:600;line-height:1.25;color:var(--primary-text-color)}
.sub{color:var(--secondary-text-color);font-size:13px;margin-top:2px}
.pill{display:inline-block;background:var(--secondary-background-color);border-radius:999px;padding:2px 9px;font-size:12px;margin:6px 6px 0 0;color:var(--primary-text-color)}
.pill.acc{background:var(--primary-color);color:var(--text-primary-color,#fff)}
.row{display:flex;align-items:center;gap:10px;padding:8px 0;border-top:1px solid var(--divider-color)}
.row:first-of-type{border-top:0}
.row .t{font-weight:600;color:var(--primary-text-color)}
.row .s{font-size:12.5px;color:var(--secondary-text-color)}
.row .tm{min-width:48px;font-weight:600;color:var(--primary-color);font-variant-numeric:tabular-nums}
.row .grow{flex:1;min-width:0}
.row .grow div{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.btn{border:0;border-radius:8px;padding:6px 10px;cursor:pointer;background:var(--primary-color);color:var(--text-primary-color,#fff);font:inherit;font-size:12.5px}
.btn[disabled]{opacity:.5;cursor:default}
.bar{height:4px;background:var(--divider-color);border-radius:2px;margin-top:4px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--primary-color)}
.empty{color:var(--secondary-text-color);padding:6px 0}
.kv{display:grid;grid-template-columns:1fr auto;gap:6px 12px;font-size:14px}
.kv b{font-weight:600}
.toast{margin-top:8px;font-size:12px;color:var(--secondary-text-color)}
`;

class EpgBase extends HTMLElement {
  setConfig(c) { this._cfg = { language: "", ...c }; this._built = false; }
  set hass(h) { this._hass = h; this._render(); }
  getCardSize() { return 3; }
  _tx() {
    const l = this._cfg.language || (this._hass && (this._hass.language || "en").slice(0, 2)) || "en";
    return T[l === "no" ? "nb" : l] || T.en;
  }
  _locale() { return (this._hass && this._hass.language) || undefined; }
  _st(id) { return this._hass && this._hass.states[id]; }
  _time(ts) { return new Date(typeof ts === "number" ? ts * 1000 : ts).toLocaleTimeString(this._locale(), { hour: "2-digit", minute: "2-digit" }); }
  _day(ts) {
    const d = new Date(ts), n = new Date();
    if (d.toDateString() === n.toDateString()) return "";
    return d.toLocaleDateString(this._locale(), { weekday: "short", day: "numeric", month: "short" }) + " ";
  }
  _esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
  _mount(html) {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${CSS}</style><ha-card>${html}</ha-card>`;
  }
  _head(icon, text) { return `<div class="h"><ha-icon icon="${icon}"></ha-icon>${this._esc(text)}</div>`; }
  _more(ent) { // open more-info on tap
    this.shadowRoot.querySelectorAll("[data-more]").forEach((e) => (e.onclick = () =>
      this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId: e.dataset.more } }))));
  }
}

/* ---- Next reminder ---- */
class EpgNextCard extends EpgBase {
  static getStubConfig() { return {}; }
  _render() {
    const t = this._tx(), s = this._st("sensor.epg_next_reminder");
    if (!s || s.state === "unknown" || s.state === "unavailable") {
      this._mount(this._head("mdi:bell-ring", t.next) + `<div class="empty">${t.none}</div>`); return;
    }
    const a = s.attributes, mins = a.minutes_until;
    const when = mins != null && mins <= 1 ? t.soon : (mins != null && mins < 120 ? `${mins} ${t.min}` : this._day(s.state) + this._time(s.state));
    this._mount(this._head("mdi:bell-ring", t.next) +
      `<div data-more="${s.entity_id}" style="cursor:pointer"><div class="big">${this._esc(a.title || "")}</div>
       <div class="sub">${this._esc(a.channel || "")}${a.start ? " · " + this._time(a.start) : ""}</div>
       <span class="pill acc">🔔 ${this._esc(when)}</span>${a.channel_number ? `<span class="pill">📺 ${t.ch} ${this._esc(a.channel_number)}</span>` : ""}</div>`);
    this._more();
  }
}

/* ---- Upcoming list ---- */
class EpgUpcomingCard extends EpgBase {
  static getStubConfig() { return { count: 5 }; }
  getCardSize() { return 1 + (this._cfg.count || 5); }
  _render() {
    const t = this._tx(), s = this._st("sensor.epg_next_reminder");
    const list = ((s && s.attributes.upcoming) || []).slice(0, this._cfg.count || 5);
    const title = this._cfg.title || t.upcoming;
    if (!list.length) { this._mount(this._head("mdi:format-list-bulleted", title) + `<div class="empty">${t.none}</div>`); return; }
    this._mount(this._head("mdi:format-list-bulleted", title) + list.map((u) =>
      `<div class="row"><div class="tm">${this._time(u.fire_at)}</div>
       <div class="grow"><div class="t">${this._esc(u.title)}</div><div class="s">${this._day(u.fire_at)}${this._esc(u.channel || "")}${u.start ? " · " + this._time(u.start) : ""}${u.channel_number ? " · 📺 " + this._esc(u.channel_number) : ""}</div></div></div>`).join(""));
  }
}

/* ---- On now (mini guide + remote) ---- */
class EpgNowCard extends EpgBase {
  static getStubConfig() { return { tune: true, play: false, show_next: true }; }
  getCardSize() { return 2 + ((this._cfg.max || 6)); }
  _render() {
    if (this._busy) return;
    const t = this._tx(), s = this._st("sensor.epg_now_on_favorites"), cfg = this._st("sensor.epg_active_reminders");
    const title = this._cfg.title || t.now;
    const now = Date.now() / 1000;
    const ch = ((s && s.attributes.channels) || []).slice(0, this._cfg.max || 6);
    if (!ch.length) { this._mount(this._head("mdi:television-guide", title) + `<div class="empty">${t.nofav}</div>`); return; }
    const canTune = this._cfg.tune !== false;
    this._mount(this._head("mdi:television-guide", title) + ch.map((c, i) => {
      const pct = c.start && c.stop ? Math.max(0, Math.min(100, ((now - c.start) / (c.stop - c.start)) * 100)) : 0;
      return `<div class="row"><div class="tm">${c.number ? this._esc(c.number) : "–"}</div>
        <div class="grow"><div class="t">${this._esc(c.title || "—")}</div>
        <div class="s">${this._esc(c.channel)}${c.stop ? " · " + this._time(c.start) + "–" + this._time(c.stop) : ""}${this._cfg.show_next !== false && c.next_title ? ` · ${t.next_l}: ${this._esc(c.next_title)} ${this._time(c.next_start)}` : ""}</div>
        <div class="bar"><i style="width:${pct}%"></i></div></div>
        ${canTune && c.number ? `<button class="btn" data-i="${i}">${t.tune}</button>` : ""}
        ${this._cfg.play && c.id ? `<button class="btn" data-p="${i}">${t.play}</button>` : ""}</div>`;
    }).join("") + `<div class="toast" id="msg"></div>`);
    this.shadowRoot.querySelectorAll("button[data-i]").forEach((b) => (b.onclick = () => this._tune(ch[+b.dataset.i], cfg)));
    this.shadowRoot.querySelectorAll("button[data-p]").forEach((b) => (b.onclick = () => this._play(ch[+b.dataset.p])));
  }
  async _play(c) {
    const t = this._tx(), msg = this.shadowRoot.getElementById("msg");
    const data = { channel_id: c.id };
    if (this._cfg.play_entity) data.entity_id = this._cfg.play_entity;   // otherwise: the add-on's default players
    if (this._cfg.play_format) data.fmt = this._cfg.play_format;
    try { await this._hass.callApi("POST", "events/iptv_epg_play", data); msg.textContent = `${t.played} ${t.play}: ${c.channel}`; }
    catch (e) { msg.textContent = String((e && e.message) || e); }
  }
  async _tune(c, cfg) {
    const t = this._tx(), a = (cfg && cfg.attributes) || {};
    const entity = this._cfg.entity || a.tune_entity;
    const msg = this.shadowRoot.getElementById("msg");
    if (!entity) { msg.textContent = t.tv; return; }
    const cmds = String(c.number).split("");
    if (a.tune_suffix) cmds.push(a.tune_suffix);
    try {
      await this._hass.callService("remote", "send_command", { entity_id: entity, command: cmds, delay_secs: a.tune_delay || 0.4 });
      msg.textContent = `✓ ${t.sent}: ${c.number} (${c.channel})`;
    } catch (e) { msg.textContent = String(e && e.message || e); }
  }
}

/* ---- Activity: last triggered + last channel change ---- */
class EpgActivityCard extends EpgBase {
  static getStubConfig() { return {}; }
  _render() {
    const t = this._tx(), l = this._st("sensor.epg_last_triggered"), c = this._st("sensor.epg_last_channel_change");
    const has = (s) => s && s.state !== "unknown" && s.state !== "unavailable";
    let h = this._head("mdi:history", this._cfg.title || t.last);
    h += has(l) ? `<div data-more="${l.entity_id}" style="cursor:pointer"><div class="big">${this._esc(l.attributes.title || l.attributes.label || "")}</div>
      <div class="sub">${this._day(l.state)}${this._time(l.state)}${l.attributes.channel ? " · " + this._esc(l.attributes.channel) : ""}</div></div>` : `<div class="empty">${t.never}</div>`;
    h += `<div style="height:10px"></div>` + this._head("mdi:television-classic", t.lastch);
    h += has(c) ? `<div data-more="${c.entity_id}" style="cursor:pointer"><div class="big">${t.ch} ${this._esc(c.state)}</div>
      <div class="sub">${this._esc(c.attributes.channel || c.attributes.program || "")}${c.attributes.changed_at ? " · " + this._day(c.attributes.changed_at) + this._time(c.attributes.changed_at) : ""}</div></div>` : `<div class="empty">${t.never}</div>`;
    this._mount(h); this._more();
  }
  getCardSize() { return 4; }
}

/* ---- Status ---- */
class EpgStatusCard extends EpgBase {
  static getStubConfig() { return {}; }
  _render() {
    const t = this._tx(), a = this._st("sensor.epg_active_reminders");
    const n = this._st("sensor.epg_next_reminder");
    this._mount(this._head("mdi:bell-cog", this._cfg.title || "EPG") +
      `<div class="kv"><span>${t.active}</span><b>${a ? this._esc(a.state) : "–"}</b>
       <span>${t.sched}</span><b>${a ? this._esc(a.attributes.scheduled_next_7_days) : "–"}</b>
       <span>${t.next}</span><b>${n && n.state !== "unknown" ? this._day(n.state) + this._time(n.state) : "–"}</b></div>`);
  }
  getCardSize() { return 2; }
}

const CARDS = [
  ["epg-next-card", EpgNextCard, "EPG – Next reminder", "The next reminder with channel and time."],
  ["epg-upcoming-card", EpgUpcomingCard, "EPG – Upcoming reminders", "List of upcoming reminders (option: count)."],
  ["epg-now-card", EpgNowCard, "EPG – On now (favorites)", "What is on now on your favorite channels, with a channel-change button."],
  ["epg-activity-card", EpgActivityCard, "EPG – Last activity", "Last triggered reminder and last channel change."],
  ["epg-status-card", EpgStatusCard, "EPG – Status", "Active and scheduled reminders at a glance."],
];
window.customCards = window.customCards || [];
for (const [tag, cls, name, description] of CARDS) {
  if (!customElements.get(tag)) customElements.define(tag, cls);
  window.customCards.push({ type: tag, name, description, preview: false });
}
console.info("%c IPTV EPG cards %c loaded", "background:#2563eb;color:#fff;border-radius:3px 0 0 3px;padding:1px 4px", "padding:1px 4px");
