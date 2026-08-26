"""Constants for the Entity Override integration."""

DOMAIN = "entity_override"

STORAGE_VERSION = 1
STORAGE_KEY = "entity_override.overrides"

SERVICE_SET = "set"
SERVICE_CANCEL = "cancel"

ATTR_ENTITY_ID = "entity_id"
ATTR_STATE = "state"
ATTR_UNTIL = "until"

SIGNAL_OVERRIDES_UPDATED = f"{DOMAIN}_overrides_updated"

PENDING_SENSOR_ENTITY_ID = "sensor.entity_override_pending"

CARD_JS_FILENAME = "entity-override-card.js"
CARD_URL_PATH = "/entity_override_static/entity-override-card.js"
