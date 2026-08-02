"""Constants for the Alert Plus integration."""

from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "alert_plus"

# Entities are created in core's `alert` domain, not in a domain of this
# integration's own. Alert Plus is meant to become that integration, so
# `alert.fire_alert` has to keep being `alert.fire_alert`.
ALERT_DOMAIN: Final = "alert"
ENTITY_ID_FORMAT: Final = ALERT_DOMAIN + ".{}"

LOGGER: Final = logging.getLogger(__package__)

# Configuration keys, matching core alert's YAML keys one for one.
CONF_CAN_ACKNOWLEDGE: Final = "can_acknowledge"
CONF_DATA: Final = "data"
CONF_DONE_MESSAGE: Final = "done_message"
CONF_MESSAGE: Final = "message"
CONF_NOTIFIERS: Final = "notifiers"
CONF_SKIP_FIRST: Final = "skip_first"
CONF_TITLE: Final = "title"

# Additions of this integration, with no equivalent in core alert.
CONF_NOTIFY_ENTITIES: Final = "notify_entities"

DEFAULT_CAN_ACKNOWLEDGE: Final = True
DEFAULT_REPEAT: Final[list[float]] = [30.0]
DEFAULT_SKIP_FIRST: Final = False

# One second, expressed in minutes. Anything shorter turns a repeating alert
# into a notification storm, so the flow refuses it.
MIN_REPEAT_MINUTES: Final = 1 / 60

# State attributes, on top of the state core alert already reported.
ATTR_CAN_ACKNOWLEDGE: Final = "can_acknowledge"
ATTR_NEXT_NOTIFICATION: Final = "next_notification"
ATTR_NOTIFICATION_COUNT: Final = "notification_count"
ATTR_WATCHED_ENTITY_ID: Final = "watched_entity_id"
