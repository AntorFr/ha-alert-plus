"""The Alert Plus integration.

An upgrade of Home Assistant's frozen ``alert`` integration, meant to replace it.
Everything core did is kept as-is — the ``alert`` domain, the ``idle`` / ``on`` /
``off`` states, the ``alert.turn_on`` / ``turn_off`` / ``toggle`` services, and
the YAML schema down to the key names — so ``alert.fire_alert`` stays
``alert.fire_alert``.

What it adds:

- **A unique ID on every alert**, so it reaches the entity registry and its name,
  icon, area and visibility become editable from the frontend. This is what core
  never had, and the reason this exists.
- **Creation from the UI**, as a helper, alongside YAML. Both at once.
- **``alert_plus.reload``**, so a YAML change no longer needs a restart.
- An acknowledgement that survives a restart, alerts that fire when the condition
  is already met at startup, and support for ``notify`` entities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_ICON,
    CONF_NAME,
    CONF_REPEAT,
    CONF_STATE,
    SERVICE_RELOAD,
    SERVICE_TOGGLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import (
    ALERT_DOMAIN,
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
    LOGGER,
    MIN_REPEAT_MINUTES,
)
from .entity import AlertPlusEntity

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
        # An addition over core alert. Only a default: an icon set from the
        # frontend is stored in the registry and wins over this one.
        vol.Optional(CONF_ICON): cv.icon,
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


@dataclass(slots=True)
class AlertPlusData:
    """What the integration keeps in ``hass.data``."""

    component: EntityComponent[AlertPlusEntity]
    # Tracked apart from the component's own entities so a YAML reload can
    # rebuild exactly what YAML created, and nothing else.
    yaml_entities: dict[str, AlertPlusEntity] = field(default_factory=dict)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the alert component, its services and the YAML alerts."""
    component = EntityComponent[AlertPlusEntity](LOGGER, ALERT_DOMAIN, hass)
    data = AlertPlusData(component=component)
    hass.data[DOMAIN] = data

    # The three services core alert exposed, on the same domain, so existing
    # automations calling alert.turn_off keep working.
    component.async_register_entity_service(SERVICE_TURN_OFF, None, "async_turn_off")
    component.async_register_entity_service(SERVICE_TURN_ON, None, "async_turn_on")
    component.async_register_entity_service(SERVICE_TOGGLE, None, "async_toggle")

    async def _async_reload(call: ServiceCall) -> None:
        """Rebuild the YAML alerts from the configuration on disk."""
        # Read and validate before removing anything, so a typo in the YAML does
        # not take the running alerts with it.
        reload_config = await async_integration_yaml_config(hass, DOMAIN)
        if reload_config is None:
            LOGGER.error(
                "Not reloading alerts: the YAML configuration failed to validate"
            )
            return

        # Only what YAML created: alerts added from the UI belong to their config
        # entry and must survive a YAML reload.
        for entity in list(data.yaml_entities.values()):
            await component.async_remove_entity(entity.entity_id)
        data.yaml_entities.clear()

        await _async_setup_yaml_alerts(hass, reload_config)

    async_register_admin_service(hass, DOMAIN, SERVICE_RELOAD, _async_reload)

    await _async_setup_yaml_alerts(hass, config)

    return True


async def _async_setup_yaml_alerts(hass: HomeAssistant, config: ConfigType) -> None:
    """Create the alerts declared in YAML."""
    alerts: dict[str, Any] = config.get(DOMAIN) or {}
    if not alerts:
        return

    data: AlertPlusData = hass.data[DOMAIN]
    entities: list[AlertPlusEntity] = []

    for object_id, alert_config in alerts.items():
        entity = AlertPlusEntity(
            hass,
            name=alert_config[CONF_NAME],
            # The YAML key was already the entity id under core alert, and it is
            # the user's own stable identifier, which is what a unique ID needs
            # to be. Using it for both keeps entity ids untouched on migration.
            unique_id=object_id,
            object_id=object_id,
            watched_entity_id=alert_config[CONF_ENTITY_ID],
            options=_yaml_to_options(alert_config),
        )
        data.yaml_entities[object_id] = entity
        entities.append(entity)

    await data.component.async_add_entities(entities)


def _yaml_to_options(alert_config: dict[str, Any]) -> dict[str, Any]:
    """Normalize a validated YAML alert into the entity's options mapping.

    The schema validates templates into ``Template`` objects; they go back to
    their source string so YAML and config entries feed the entity the exact
    same shape.
    """
    options = dict(alert_config)
    for key in TEMPLATE_KEYS:
        if (template := options.get(key)) is not None:
            options[key] = template.template
    return options


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an alert created from the UI.

    Delegated to the component so the entity goes through the ``alert`` platform
    of this integration and gets tied to its config entry in the registry.
    """
    data: AlertPlusData = hass.data[DOMAIN]
    return await data.component.async_setup_entry(entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an alert created from the UI."""
    data: AlertPlusData = hass.data[DOMAIN]
    return await data.component.async_unload_entry(entry)
