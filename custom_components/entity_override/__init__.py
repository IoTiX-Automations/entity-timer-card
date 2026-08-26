"""The Entity Override integration.

Turns any entity on or off immediately and schedules reverting it at a
chosen date & time. Pending overrides are persisted to storage and
rescheduled on restart, so a reboot mid-countdown does not lose the
revert. Ships a companion Lovelace card (auto-registered as a frontend
resource) that provides the "turn on/off until" popup UI.
"""

from __future__ import annotations

import logging
import pathlib
from datetime import datetime
from typing import Any

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ENTITY_ID,
    ATTR_STATE,
    ATTR_UNTIL,
    CARD_JS_FILENAME,
    CARD_URL_PATH,
    DOMAIN,
    SERVICE_CANCEL,
    SERVICE_SET,
    SIGNAL_OVERRIDES_UPDATED,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

SET_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_STATE): vol.In(["on", "off"]),
        vol.Required(ATTR_UNTIL): cv.datetime,
    }
)

CANCEL_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_id})


class OverrideManager:
    """Owns the pending-overrides store and their scheduled reverts."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._overrides: dict[str, dict[str, str]] = {}
        self._unsub_timers: dict[str, Any] = {}

    @property
    def overrides(self) -> dict[str, dict[str, str]]:
        return self._overrides

    async def async_load(self) -> None:
        self._overrides = await self._store.async_load() or {}

    async def _async_save(self) -> None:
        await self._store.async_save(self._overrides)
        async_dispatcher_send(self.hass, SIGNAL_OVERRIDES_UPDATED)

    async def _async_call_state(self, entity_id: str, state: str) -> None:
        service = "turn_on" if state == "on" else "turn_off"
        await self.hass.services.async_call(
            "homeassistant", service, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )

    def _cancel_timer(self, entity_id: str) -> None:
        unsub = self._unsub_timers.pop(entity_id, None)
        if unsub is not None:
            unsub()

    def _schedule_revert(self, entity_id: str, until: datetime, revert_state: str) -> None:
        async def _revert(_now: datetime) -> None:
            self._unsub_timers.pop(entity_id, None)
            await self._async_call_state(entity_id, revert_state)
            self._overrides.pop(entity_id, None)
            await self._async_save()

        self._unsub_timers[entity_id] = async_track_point_in_time(self.hass, _revert, until)

    async def async_set(self, entity_id: str, state: str, until: datetime) -> None:
        """Apply the requested state now and schedule reverting it at `until`."""
        await self._async_call_state(entity_id, state)

        self._cancel_timer(entity_id)
        revert_state = "off" if state == "on" else "on"
        self._overrides[entity_id] = {
            "revert_state": revert_state,
            "until": dt_util.as_utc(until).isoformat(),
        }
        await self._async_save()
        self._schedule_revert(entity_id, dt_util.as_utc(until), revert_state)

    async def async_cancel(self, entity_id: str) -> None:
        """Cancel a pending override without changing the entity's current state."""
        self._cancel_timer(entity_id)
        if self._overrides.pop(entity_id, None) is not None:
            await self._async_save()

    async def async_reschedule_all(self) -> None:
        """Called on startup: reschedule pending overrides, revert any already due."""
        now = dt_util.utcnow()
        changed = False
        for entity_id, info in list(self._overrides.items()):
            until = dt_util.parse_datetime(info["until"])
            if until is None:
                self._overrides.pop(entity_id, None)
                changed = True
                continue
            if until <= now:
                await self._async_call_state(entity_id, info["revert_state"])
                self._overrides.pop(entity_id, None)
                changed = True
            else:
                self._schedule_revert(entity_id, until, info["revert_state"])
        if changed:
            await self._async_save()

    def async_shutdown(self) -> None:
        for unsub in list(self._unsub_timers.values()):
            unsub()
        self._unsub_timers.clear()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = OverrideManager(hass)
    await manager.async_load()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager

    await manager.async_reschedule_all()

    async def _handle_set(call: ServiceCall) -> None:
        await manager.async_set(call.data[ATTR_ENTITY_ID], call.data[ATTR_STATE], call.data[ATTR_UNTIL])

    async def _handle_cancel(call: ServiceCall) -> None:
        await manager.async_cancel(call.data[ATTR_ENTITY_ID])

    hass.services.async_register(DOMAIN, SERVICE_SET, _handle_set, schema=SET_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CANCEL, _handle_cancel, schema=CANCEL_SCHEMA)

    # Serve the companion card and auto-register it as a frontend resource,
    # so installers never have to add a dashboard resource by hand.
    www_dir = pathlib.Path(__file__).parent / "www"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL_PATH, str(www_dir / CARD_JS_FILENAME), cache_headers=False)]
    )
    add_extra_js_url(hass, CARD_URL_PATH)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        manager: OverrideManager = hass.data[DOMAIN].pop(entry.entry_id)
        manager.async_shutdown()
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SET)
            hass.services.async_remove(DOMAIN, SERVICE_CANCEL)
    return unload_ok
