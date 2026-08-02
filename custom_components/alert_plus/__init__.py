"""The Alert Plus integration.

A UI-configurable take on Home Assistant's frozen ``alert`` integration: every
alert gets a stable unique ID, so it can be named, given an icon and assigned to
an area from the frontend like any other entity.

Alerts can be declared either way, and the two live side by side:

- **YAML**, under an ``alert_plus:`` key using the exact schema of core
  ``alert:``. YAML stays the source of truth for those alerts; their options are
  edited in YAML, while name, icon and area remain editable from the frontend.
- **The UI**, as helpers. One config entry per alert, options editable from the
  frontend too.
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_REPEAT,
    CONF_STATE,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .alert import AlertPlusConfigEntry, AlertPlusRuntime
from .const import (
    ACKNOWLEDGE_ID_SUFFIX,
    CONF_CAN_ACKNOWLEDGE,
    CONF_DATA,
    CONF_DONE_MESSAGE,
    CONF_MESSAGE,
    CONF_NOTIFIERS,
    CONF_SKIP_FIRST,
    CONF_TITLE,
    DEFAULT_CAN_ACKNOWLEDGE,
    DEFAULT_SKIP_FIRST,
    DOMAIN,
    MIN_REPEAT_MINUTES,
    PLATFORMS,
)

# Deliberately identical to core alert's ALERT_SCHEMA, so an existing `alert:`
# block moves over by renaming its key to `alert_plus:` and nothing else.
ALERT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_STATE, default=STATE_ON): cv.string,
        vol.Required(CONF_REPEAT): vol.All(
            cv.ensure_list,
            [vol.Coerce(float)],
            [vol.Range(min=MIN_REPEAT_MINUTES)],
        ),
        vol.Optional(CONF_CAN_ACKNOWLEDGE, default=DEFAULT_CAN_ACKNOWLEDGE): cv.boolean,
        vol.Optional(CONF_SKIP_FIRST, default=DEFAULT_SKIP_FIRST): cv.boolean,
        vol.Optional(CONF_MESSAGE): cv.template,
        vol.Optional(CONF_DONE_MESSAGE): cv.template,
        vol.Optional(CONF_TITLE): cv.template,
        vol.Optional(CONF_DATA): dict,
        vol.Optional(CONF_NOTIFIERS, default=list): vol.All(
            cv.ensure_list, [cv.string]
        ),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: cv.schema_with_slug_keys(ALERT_SCHEMA)}, extra=vol.ALLOW_EXTRA
)

TEMPLATE_KEYS = (CONF_MESSAGE, CONF_DONE_MESSAGE, CONF_TITLE)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the alerts declared in YAML."""
    alerts: dict[str, Any] = config.get(DOMAIN) or {}
    runtimes: dict[str, AlertPlusRuntime] = hass.data.setdefault(DOMAIN, {})

    for object_id, alert_config in alerts.items():
        runtimes[object_id] = AlertPlusRuntime(
            hass,
            name=alert_config[CONF_NAME],
            # The YAML key is the user's own stable identifier, which is exactly
            # what a unique ID needs to be.
            unique_id=object_id,
            watched_entity_id=alert_config[CONF_ENTITY_ID],
            options=_yaml_to_options(alert_config),
            suggested_object_id=object_id,
        )

    if not runtimes:
        return True

    for platform in PLATFORMS:
        hass.async_create_task(
            async_load_platform(
                hass, platform, DOMAIN, {"object_ids": list(runtimes)}, config
            )
        )

    for runtime in runtimes.values():
        runtime.async_start()

    return True


@callback
def _yaml_to_options(alert_config: dict[str, Any]) -> dict[str, Any]:
    """Normalize a validated YAML alert into the runtime's options mapping.

    The schema validates templates into ``Template`` objects; they go back to
    their source string so YAML and config entries feed the runtime the exact
    same shape.
    """
    options = dict(alert_config)
    for key in TEMPLATE_KEYS:
        if (template := options.get(key)) is not None:
            options[key] = template.template
    return options


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

    runtime = AlertPlusRuntime(
        hass,
        name=entry.title,
        unique_id=entry.entry_id,
        watched_entity_id=watched_entity_id,
        options=entry.options,
    )
    entry.runtime_data = runtime
    entry.async_on_unload(runtime.async_shutdown)

    # Platforms first: the acknowledgement switch restores its state on add, and
    # the runtime must see that before it evaluates the watched entity.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    runtime.async_start()

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
