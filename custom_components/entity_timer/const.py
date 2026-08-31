"""Constants for the Entity Timer integration."""

DOMAIN = "entity_timer"

STORAGE_VERSION = 1
STORAGE_KEY = "entity_timer.timers"

SERVICE_SET = "set"
SERVICE_CANCEL = "cancel"

ATTR_ENTITY_ID = "entity_id"
ATTR_STATE = "state"
ATTR_UNTIL = "until"

SIGNAL_TIMERS_UPDATED = f"{DOMAIN}_timers_updated"

PENDING_SENSOR_ENTITY_ID = "sensor.entity_timer_pending"

CARD_JS_FILENAME = "entity-timer-card.js"
CARD_URL_PATH = "/entity_timer_static/entity-timer-card.js"

# hass.data flag: the static route can only be registered once per running
# process (aiohttp rejects a second add_route for the same path), but
# async_setup_entry runs again on every integration reload. This is process-
# lifetime state, not per-config-entry state, so it lives under its own key
# rather than inside hass.data[DOMAIN][entry.entry_id].
DATA_STATIC_PATH_REGISTERED = f"{DOMAIN}_static_path_registered"
