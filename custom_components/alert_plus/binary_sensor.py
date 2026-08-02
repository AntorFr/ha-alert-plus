"""Binary sensor exposing the state of an alert."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .alert import AlertPlusConfigEntry, AlertPlusRuntime
from .const import (
    ATTR_ACKNOWLEDGED,
    ATTR_CAN_ACKNOWLEDGE,
    ATTR_NEXT_NOTIFICATION,
    ATTR_NOTIFICATION_COUNT,
    ATTR_WATCHED_ENTITY_ID,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AlertPlusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the alert binary sensor from a config entry."""
    async_add_entities([AlertPlusBinarySensor(entry.runtime_data)])


class AlertPlusBinarySensor(BinarySensorEntity):
    """Report whether the watched condition is currently met."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_should_poll = False

    def __init__(self, runtime: AlertPlusRuntime) -> None:
        """Initialize the alert binary sensor."""
        self._runtime = runtime
        self._attr_name = runtime.name
        self._attr_unique_id = runtime.entry.entry_id

    @override
    async def async_added_to_hass(self) -> None:
        """Follow the alert state machine."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._runtime.async_add_listener(self.async_write_ha_state)
        )

    @property
    @override
    def is_on(self) -> bool:
        """Return True while the alert is firing."""
        return self._runtime.is_firing

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the details an automation or dashboard may want."""
        next_notification = self._runtime.next_notification
        return {
            ATTR_WATCHED_ENTITY_ID: self._runtime.watched_entity_id,
            ATTR_ACKNOWLEDGED: self._runtime.acknowledged,
            ATTR_CAN_ACKNOWLEDGE: self._runtime.can_acknowledge,
            ATTR_NOTIFICATION_COUNT: self._runtime.notification_count,
            ATTR_NEXT_NOTIFICATION: (
                next_notification.isoformat() if next_notification else None
            ),
        }
