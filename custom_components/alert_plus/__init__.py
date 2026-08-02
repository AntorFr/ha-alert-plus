"""The Alert Plus integration.

A UI-configurable take on Home Assistant's frozen ``alert`` integration: one
config entry per alert, so every alert gets a stable unique ID and can be named,
given an icon and assigned to an area from the frontend like any other entity.
"""

from __future__ import annotations

from homeassistant.const import CONF_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er
import voluptuous as vol

from .alert import AlertPlusConfigEntry, AlertPlusRuntime
from .const import ACKNOWLEDGE_ID_SUFFIX, CONF_CAN_ACKNOWLEDGE, DOMAIN, PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: AlertPlusConfigEntry) -> bool:
    """Set up an alert from a config entry."""
    registry = er.async_get(hass)
    try:
        watched_entity_id = er.async_validate_entity_id(
            registry, entry.options[CONF_ENTITY_ID]
        )
    except vol.Invalid as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="watched_entity_missing",
            translation_placeholders={"entity_id": entry.options[CONF_ENTITY_ID]},
        ) from err

    _async_cleanup_acknowledge_switch(registry, entry)

    entry.runtime_data = AlertPlusRuntime(hass, entry, watched_entity_id)

    # Platforms first: the acknowledgement switch restores its state on add, and
    # the runtime must see that before it evaluates the watched entity.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.runtime_data.async_start()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: AlertPlusConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


@callback
def _async_cleanup_acknowledge_switch(
    registry: er.EntityRegistry, entry: AlertPlusConfigEntry
) -> None:
    """Remove the acknowledgement switch once the option is turned off.

    The switch platform simply stops creating the entity, which on its own would
    leave a permanently unavailable leftover in the registry.
    """
    if entry.options[CONF_CAN_ACKNOWLEDGE]:
        return

    entity_id = registry.async_get_entity_id(
        Platform.SWITCH, DOMAIN, f"{entry.entry_id}{ACKNOWLEDGE_ID_SUFFIX}"
    )
    if entity_id is not None:
        registry.async_remove(entity_id)
