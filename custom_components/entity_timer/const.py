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
