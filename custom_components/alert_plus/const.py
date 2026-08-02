"""Constants for the Alert Plus integration."""

from __future__ import annotations

import logging
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "alert_plus"

LOGGER: Final = logging.getLogger(__package__)

PLATFORMS: Final[list[Platform]] = [Platform.BINARY_SENSOR, Platform.SWITCH]

# Configuration keys. Everything a helper collects is stored in the config entry
# options, never in its data, so these are all option keys.
CONF_CAN_ACKNOWLEDGE: Final = "can_acknowledge"
CONF_DATA: Final = "data"
CONF_DONE_MESSAGE: Final = "done_message"
CONF_MESSAGE: Final = "message"
CONF_NOTIFIERS: Final = "notifiers"
CONF_NOTIFY_ENTITIES: Final = "notify_entities"
CONF_SKIP_FIRST: Final = "skip_first"
CONF_TITLE: Final = "title"

# Suffix of the acknowledgement switch unique ID, shared by the switch platform
# and the cleanup that removes it when acknowledgement gets turned off.
ACKNOWLEDGE_ID_SUFFIX: Final = "-acknowledged"

DEFAULT_CAN_ACKNOWLEDGE: Final = True
DEFAULT_REPEAT: Final[list[float]] = [30.0]
DEFAULT_SKIP_FIRST: Final = False

# One second, expressed in minutes. Anything shorter turns a repeating alert into
# a notification storm, so the flow refuses it.
MIN_REPEAT_MINUTES: Final = 1 / 60

# State attributes exposed on the alert binary sensor.
ATTR_ACKNOWLEDGED: Final = "acknowledged"
ATTR_CAN_ACKNOWLEDGE: Final = "can_acknowledge"
ATTR_NEXT_NOTIFICATION: Final = "next_notification"
ATTR_NOTIFICATION_COUNT: Final = "notification_count"
ATTR_WATCHED_ENTITY_ID: Final = "watched_entity_id"
