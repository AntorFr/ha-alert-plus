"""Switch used to acknowledge an alert."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .alert import AlertPlusConfigEntry, AlertPlusRuntime
from .const import ACKNOWLEDGE_ID_SUFFIX


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AlertPlusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the acknowledgement switch, when the alert allows one."""
    runtime = entry.runtime_data
    if not runtime.can_acknowledge:
        return

    async_add_entities([AlertPlusAcknowledgeSwitch(runtime)])


class AlertPlusAcknowledgeSwitch(SwitchEntity, RestoreEntity):
    """Mute an alert's notifications until the watched condition clears."""

    _attr_should_poll = False
    _attr_icon = "mdi:bell-check-outline"

    def __init__(self, runtime: AlertPlusRuntime) -> None:
        """Initialize the acknowledgement switch."""
        self._runtime = runtime
        self._attr_name = f"{runtime.name} acknowledged"
        self._attr_unique_id = f"{runtime.entry.entry_id}{ACKNOWLEDGE_ID_SUFFIX}"

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the acknowledgement and follow the alert state machine."""
        await super().async_added_to_hass()

        # Runs before the runtime is started, so an alert acknowledged before a
        # restart stays quiet instead of notifying again on the way back up.
        if (last_state := await self.async_get_last_state()) is not None:
            self._runtime.async_restore_acknowledged(last_state.state == STATE_ON)

        self.async_on_remove(
            self._runtime.async_add_listener(self.async_write_ha_state)
        )

    @property
    @override
    def is_on(self) -> bool:
        """Return True while the alert is acknowledged."""
        return self._runtime.acknowledged

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Acknowledge the alert."""
        await self._runtime.async_acknowledge()

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Resume notifications for the alert."""
        await self._runtime.async_unacknowledge()
