"""The Entity Timer integration.

Turns any entity on or off immediately and schedules reverting it at a
chosen date & time. Pending timers are persisted to storage and
rescheduled on restart, so a reboot mid-countdown does not lose the
revert. Ships a companion Lovelace card that provides the "turn on/off
until" popup UI; this component serves the card's script but does not
auto-register it as a dashboard resource — Lovelace's scoped
custom-element-registry only recognizes cards added as an actual
dashboard resource (Settings > Dashboards > Resources), not scripts
injected via frontend.add_extra_js_url (that API works for panels, not
Lovelace card elements). See the README for the one-time setup step.
"""

from __future__ import annotations

import logging
import pathlib
from datetime import datetime
from typing import Any

import voluptuous as vol

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
    DATA_STATIC_PATH_REGISTERED,
    DOMAIN,
    SERVICE_CANCEL,
    SERVICE_SET,
    SIGNAL_TIMERS_UPDATED,
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


class EntityTimerManager:
    """Owns the pending-timers store and their scheduled reverts."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._timers: dict[str, dict[str, str]] = {}
        self._unsub_timers: dict[str, Any] = {}

    @property
    def timers(self) -> dict[str, dict[str, str]]:
        return self._timers

    async def async_load(self) -> None:
        self._timers = await self._store.async_load() or {}

    async def _async_save(self) -> None:
        await self._store.async_save(self._timers)
        async_dispatcher_send(self.hass, SIGNAL_TIMERS_UPDATED)

    async def _async_call_state(self, entity_id: str, state: str) -> None:
        service = "turn_on" if state == "on" else "turn_off"
        await self.hass.services.async_call(
            "homeassistant", service, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )

    def _cancel_timer_callback(self, entity_id: str) -> None:
        unsub = self._unsub_timers.pop(entity_id, None)
        if unsub is not None:
            unsub()

    def _schedule_revert(self, entity_id: str, until: datetime, revert_state: str) -> None:
        async def _revert(_now: datetime) -> None:
            self._unsub_timers.pop(entity_id, None)
            self._timers.pop(entity_id, None)
            # Sensor commits before the entity's own state changes (see
            # async_set for why) so any card watching this entity already
            # sees "no pending timer" by the time it observes the revert.
            await self._async_save()
            await self._async_call_state(entity_id, revert_state)

        self._unsub_timers[entity_id] = async_track_point_in_time(self.hass, _revert, until)

    async def async_set(self, entity_id: str, state: str, until: datetime) -> None:
        """Schedule reverting entity_id at `until`, then apply the requested state now."""
        self._cancel_timer_callback(entity_id)
        revert_state = "off" if state == "on" else "on"
        self._timers[entity_id] = {
            "revert_state": revert_state,
            "until": dt_util.as_utc(until).isoformat(),
        }
        # Sensor commits before the entity's own state changes. Any card
        # watching this entity_id (there can be any number, in any number
        # of places) gets a state_changed event for the sensor before one
        # for the entity, so by the time it reacts to the entity's own
        # change, the pending-timer data it would look up is already
        # correct — no card-local bookkeeping needed to avoid a race.
        await self._async_save()
        self._schedule_revert(entity_id, dt_util.as_utc(until), revert_state)
        await self._async_call_state(entity_id, state)

    async def async_cancel(self, entity_id: str) -> None:
        """Cancel a pending timer, immediately reverting the entity to its normal state.

        Cancelling ends the override — it does not just forget about it and
        leave the entity stuck in the overridden state until someone
        remembers to flip it back by hand.
        """
        self._cancel_timer_callback(entity_id)
        info = self._timers.pop(entity_id, None)
        if info is None:
            return
        await self._async_save()
        await self._async_call_state(entity_id, info["revert_state"])

    async def async_reschedule_all(self) -> None:
        """Called on startup: reschedule pending timers, revert any already due."""
        now = dt_util.utcnow()
        due: list[tuple[str, str]] = []
        changed = False
        for entity_id, info in list(self._timers.items()):
            until = dt_util.parse_datetime(info["until"])
            if until is None:
                self._timers.pop(entity_id, None)
                changed = True
            elif until <= now:
                self._timers.pop(entity_id, None)
                due.append((entity_id, info["revert_state"]))
                changed = True
            else:
                self._schedule_revert(entity_id, until, info["revert_state"])
        if changed:
            await self._async_save()
        for entity_id, revert_state in due:
            await self._async_call_state(entity_id, revert_state)

    def async_shutdown(self) -> None:
        for unsub in list(self._unsub_timers.values()):
            unsub()
        self._unsub_timers.clear()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = EntityTimerManager(hass)
    await manager.async_load()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager

    await manager.async_reschedule_all()

    async def _handle_set(call: ServiceCall) -> None:
        await manager.async_set(call.data[ATTR_ENTITY_ID], call.data[ATTR_STATE], call.data[ATTR_UNTIL])

    async def _handle_cancel(call: ServiceCall) -> None:
        await manager.async_cancel(call.data[ATTR_ENTITY_ID])

    hass.services.async_register(DOMAIN, SERVICE_SET, _handle_set, schema=SET_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CANCEL, _handle_cancel, schema=CANCEL_SCHEMA)

    # Serve the companion card's script. It still needs to be added as a
    # dashboard resource once (Settings > Dashboards > Resources) — see
    # the README; Lovelace does not pick up card elements from
    # frontend.add_extra_js_url.
    #
    # Only register once per process: aiohttp raises if the same path is
    # registered twice, and async_setup_entry runs again on every reload
    # of the integration (not just on a full HA restart, which is the only
    # thing that actually resets the underlying route table).
    if not hass.data.get(DATA_STATIC_PATH_REGISTERED):
        www_dir = pathlib.Path(__file__).parent / "www"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_PATH, str(www_dir / CARD_JS_FILENAME), cache_headers=False)]
        )
        hass.data[DATA_STATIC_PATH_REGISTERED] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        manager: EntityTimerManager = hass.data[DOMAIN].pop(entry.entry_id)
        manager.async_shutdown()
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SET)
            hass.services.async_remove(DOMAIN, SERVICE_CANCEL)
    return unload_ok
