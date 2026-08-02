"""Config and options flow for the Alert Plus integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, override

from homeassistant.components.notify import (
    DOMAIN as NOTIFY_DOMAIN,
    SERVICE_SEND_MESSAGE,
)
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_REPEAT,
    CONF_STATE,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
    SchemaConfigFlowHandler,
    SchemaFlowError,
    SchemaFlowFormStep,
)
import voluptuous as vol

from .const import (
    CONF_CAN_ACKNOWLEDGE,
    CONF_DATA,
    CONF_DONE_MESSAGE,
    CONF_MESSAGE,
    CONF_NOTIFIERS,
    CONF_NOTIFY_ENTITIES,
    CONF_SKIP_FIRST,
    CONF_TITLE,
    DEFAULT_CAN_ACKNOWLEDGE,
    DEFAULT_REPEAT,
    DEFAULT_SKIP_FIRST,
    DOMAIN,
    MIN_REPEAT_MINUTES,
)


def _build_schema(hass: HomeAssistant, *, include_name: bool) -> vol.Schema:
    """Build the flow schema.

    Legacy notify services are offered as a dropdown built from what is loaded
    right now, while still accepting a typed-in name so an alert can target a
    notifier that is not set up yet.
    """
    notify_services = sorted(
        service
        for service in hass.services.async_services_for_domain(NOTIFY_DOMAIN)
        # ``send_message`` is the notify *entity* service; it is driven by the
        # separate entity picker below, not by a service name.
        if service != SERVICE_SEND_MESSAGE
    )

    schema: dict[Any, Any] = {}
    if include_name:
        schema[vol.Required(CONF_NAME)] = selector.TextSelector()

    schema.update(
        {
            vol.Required(CONF_ENTITY_ID): selector.EntitySelector(),
            vol.Required(CONF_STATE, default=STATE_ON): selector.TextSelector(),
            vol.Required(
                CONF_REPEAT, default=[str(delay) for delay in DEFAULT_REPEAT]
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.NUMBER, multiple=True
                )
            ),
            vol.Required(
                CONF_SKIP_FIRST, default=DEFAULT_SKIP_FIRST
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_CAN_ACKNOWLEDGE, default=DEFAULT_CAN_ACKNOWLEDGE
            ): selector.BooleanSelector(),
            vol.Optional(CONF_NOTIFIERS, default=list): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_services,
                    multiple=True,
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_NOTIFY_ENTITIES, default=list): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=NOTIFY_DOMAIN, multiple=True)
            ),
            vol.Optional(CONF_MESSAGE): selector.TemplateSelector(),
            vol.Optional(CONF_TITLE): selector.TemplateSelector(),
            vol.Optional(CONF_DONE_MESSAGE): selector.TemplateSelector(),
            vol.Optional(CONF_DATA): selector.ObjectSelector(),
        }
    )

    return vol.Schema(schema)


async def _async_config_schema(handler: SchemaCommonFlowHandler) -> vol.Schema:
    """Return the schema used when creating an alert."""
    return _build_schema(handler.parent_handler.hass, include_name=True)


async def _async_options_schema(handler: SchemaCommonFlowHandler) -> vol.Schema:
    """Return the schema used when editing an alert.

    The name is left out on purpose: helpers are renamed through the standard
    rename action, which retitles the config entry.
    """
    return _build_schema(handler.parent_handler.hass, include_name=False)


async def _async_suggested_values(
    handler: SchemaCommonFlowHandler,
) -> dict[str, Any]:
    """Pre-fill the form from stored options.

    Repeat delays are stored as numbers but rendered by a text selector, so they
    are handed back as strings.
    """
    suggested = dict(handler.options)
    if (repeat := suggested.get(CONF_REPEAT)) is not None:
        suggested[CONF_REPEAT] = [str(delay) for delay in repeat]
    return suggested


async def _async_validate(
    _handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
) -> dict[str, Any]:
    """Normalize the repeat delays typed into the text selector.

    Templates need no check here: ``TemplateSelector`` compiles them as part of
    schema validation and rejects the broken ones on the offending field.
    """
    repeat: list[float] = []
    for raw_delay in user_input[CONF_REPEAT]:
        try:
            delay = float(raw_delay)
        except (TypeError, ValueError) as err:
            raise SchemaFlowError("invalid_repeat") from err
        if delay < MIN_REPEAT_MINUTES:
            raise SchemaFlowError("repeat_too_short")
        repeat.append(delay)

    if not repeat:
        raise SchemaFlowError("repeat_required")

    return {**user_input, CONF_REPEAT: repeat}


CONFIG_FLOW = {
    "user": SchemaFlowFormStep(
        _async_config_schema, validate_user_input=_async_validate
    )
}

OPTIONS_FLOW = {
    "init": SchemaFlowFormStep(
        _async_options_schema,
        suggested_values=_async_suggested_values,
        validate_user_input=_async_validate,
    )
}


class AlertPlusConfigFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):
    """Handle a config or options flow for Alert Plus."""

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW
    options_flow_reloads = True

    @override
    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return config entry title."""
        name: str = options[CONF_NAME]
        return name
