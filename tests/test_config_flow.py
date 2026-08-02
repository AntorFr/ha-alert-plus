"""Tests for the Alert Plus config and options flow."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_REPEAT,
    CONF_STATE,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.alert_plus.const import (
    CONF_CAN_ACKNOWLEDGE,
    CONF_MESSAGE,
    CONF_NOTIFIERS,
    CONF_SKIP_FIRST,
    DOMAIN,
)

USER_INPUT: dict[str, Any] = {
    CONF_NAME: "Front door",
    CONF_ENTITY_ID: "binary_sensor.watched",
    CONF_STATE: STATE_ON,
    CONF_REPEAT: ["30"],
    CONF_SKIP_FIRST: False,
    CONF_CAN_ACKNOWLEDGE: True,
    CONF_NOTIFIERS: ["test_notifier"],
}


async def test_user_flow_creates_an_alert(hass: HomeAssistant) -> None:
    """The user flow stores everything in options and titles the entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(USER_INPUT)
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Front door"
    assert result["data"] == {}
    # Repeat delays are normalized to numbers on the way in.
    assert result["options"][CONF_REPEAT] == [30.0]
    assert result["options"][CONF_ENTITY_ID] == "binary_sensor.watched"


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({CONF_REPEAT: ["soon"]}, "invalid_repeat"),
        ({CONF_REPEAT: ["0.001"]}, "repeat_too_short"),
        ({CONF_REPEAT: []}, "repeat_required"),
    ],
)
async def test_user_flow_rejects_bad_delays(
    hass: HomeAssistant, overrides: dict[str, Any], error: str
) -> None:
    """Bad repeat delays are caught before an entry exists."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT | overrides
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_user_flow_rejects_a_broken_template(hass: HomeAssistant) -> None:
    """The template selector refuses a template that does not compile."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT | {CONF_MESSAGE: "{{ unbalanced "}
        )


async def test_options_flow_updates_and_reloads(hass: HomeAssistant) -> None:
    """Editing an alert rewrites its options and reloads the entry."""
    hass.states.async_set("binary_sensor.watched", "off")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Front door",
        options={
            CONF_ENTITY_ID: "binary_sensor.watched",
            CONF_STATE: STATE_ON,
            CONF_REPEAT: [30.0],
            CONF_SKIP_FIRST: False,
            CONF_CAN_ACKNOWLEDGE: True,
            CONF_NOTIFIERS: [],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_ENTITY_ID: "binary_sensor.watched",
            CONF_STATE: "problem",
            CONF_REPEAT: ["5", "15"],
            CONF_SKIP_FIRST: True,
            CONF_CAN_ACKNOWLEDGE: False,
            CONF_NOTIFIERS: [],
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_REPEAT] == [5.0, 15.0]
    assert entry.options[CONF_STATE] == "problem"
    # Acknowledgement was turned off, so the reload dropped the switch.
    assert hass.states.get("switch.front_door_acknowledged") is None
