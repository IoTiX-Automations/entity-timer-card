"""Diagnostic sensor exposing all pending overrides for the companion card."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OverrideManager
from .const import DOMAIN, PENDING_SENSOR_ENTITY_ID, SIGNAL_OVERRIDES_UPDATED


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager: OverrideManager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EntityOverridePendingSensor(manager, entry.entry_id)])


class EntityOverridePendingSensor(SensorEntity):
    """Reports the count and detail of currently pending overrides.

    Uses a fixed, predictable entity_id (rather than name-derived slugging)
    because the companion card reads this entity directly by id.
    """

    _attr_icon = "mdi:clock-alert-outline"
    _attr_should_poll = False
    _attr_name = "Entity Override Pending"

    def __init__(self, manager: OverrideManager, entry_id: str) -> None:
        self._manager = manager
        self._attr_unique_id = f"{entry_id}_pending"
        self.entity_id = PENDING_SENSOR_ENTITY_ID

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_OVERRIDES_UPDATED, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        return len(self._manager.overrides)

    @property
    def extra_state_attributes(self) -> dict:
        return {"overrides": self._manager.overrides}
