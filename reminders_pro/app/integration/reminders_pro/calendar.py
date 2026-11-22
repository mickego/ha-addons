"""calendar.reminders_pro – visar alla kommande påminnelser som kalenderhändelser."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiohttp
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .config_flow import CONF_URL

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=1)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([RemindersCalendar(hass, entry)], True)


class RemindersCalendar(CalendarEntity):
    _attr_name = "Reminders Pro"
    _attr_icon = "mdi:bell-ring"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._base = entry.data[CONF_URL].rstrip("/")
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._event: CalendarEvent | None = None
        self._hass = hass

    @property
    def event(self) -> CalendarEvent | None:
        return self._event

    async def _fetch(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        session = async_get_clientsession(self._hass)
        params = {"start": str(int(start.timestamp())), "end": str(int(end.timestamp()))}
        async with session.get(f"{self._base}/api/calendar", params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            resp.raise_for_status()
            rows = await resp.json()
        out = []
        for r in rows:
            desc = r.get("description") or ""
            if r.get("category"):
                desc = (desc + "\n" if desc else "") + f"[{r['category']}]"
            out.append(CalendarEvent(
                start=datetime.fromtimestamp(r["start"], timezone.utc),
                end=datetime.fromtimestamp(r["end"], timezone.utc),
                summary=r["title"], description=desc or None, uid=r["uid"]))
        return out

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        try:
            return await self._fetch(start_date, end_date)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Kunde inte hämta påminnelser: %s", err)
            return []

    async def async_update(self) -> None:
        now = datetime.now(timezone.utc)
        try:
            events = await self._fetch(now - timedelta(minutes=1), now + timedelta(days=30))
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Uppdatering misslyckades: %s", err)
            self._attr_available = False
            return
        self._attr_available = True
        upcoming = [e for e in events if e.end > now]
        self._event = upcoming[0] if upcoming else None
