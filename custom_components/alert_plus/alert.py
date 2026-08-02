"""Alert platform, for the alerts created from the UI.

``EntityComponent.async_setup_entry`` looks for this module by name: it is the
``alert`` platform of the ``alert_plus`` integration. Going through it, rather
than adding entities to the component by hand, is what ties each entity to its
config entry in the registry, so the frontend shows it under its helper and
deleting the helper takes the entity with it.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify
import voluptuous as vol

from .const import DOMAIN
from .entity import AlertPlusEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
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

    async_add_entities(
        [
            AlertPlusEntity(
                hass,
                name=entry.title,
                unique_id=entry.entry_id,
                object_id=slugify(entry.title),
                watched_entity_id=watched_entity_id,
                options=entry.options,
            )
        ]
    )
