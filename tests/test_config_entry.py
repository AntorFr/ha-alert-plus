"""Tests for alerts created from the UI, and their coexistence with YAML."""

from __future__ import annotations

from typing import Any

from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ENTITY_ID,
    CONF_REPEAT,
    CONF_STATE,
    SERVICE_TURN_OFF,
    STATE_IDLE,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.alert_plus.const import (
    ALERT_DOMAIN,
    CONF_CAN_ACKNOWLEDGE,
    CONF_NOTIFIERS,
    CONF_SKIP_FIRST,
    DOMAIN,
)

UI_WATCHED = "binary_sensor.door"
UI_ENTITY = f"{ALERT_DOMAIN}.front_door"

YAML_WATCHED = "binary_sensor.smoke"
YAML_ENTITY = f"{ALERT_DOMAIN}.fire_alert"
YAML_CONFIG: dict[str, Any] = {
    DOMAIN: {
        "fire_alert": {
            "name": "Fire alert",
            "entity_id": YAML_WATCHED,
            "repeat": 30,
            "notifiers": ["notify"],
        }
    }
}


async def _add_ui_alert(hass: HomeAssistant) -> MockConfigEntry:
    """Add an alert as the UI would create it."""
    hass.states.async_set(UI_WATCHED, STATE_OFF)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Front door",
        options={
            CONF_ENTITY_ID: UI_WATCHED,
            CONF_STATE: STATE_ON,
            CONF_REPEAT: [30.0],
            CONF_SKIP_FIRST: False,
            CONF_CAN_ACKNOWLEDGE: True,
            CONF_NOTIFIERS: ["notify"],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_ui_alert_lands_in_the_alert_domain(hass: HomeAssistant) -> None:
    """An alert created from the UI is an alert entity like any other."""
    async_mock_service(hass, "notify", "notify")
    entry = await _add_ui_alert(hass)

    assert hass.states.get(UI_ENTITY).state == STATE_IDLE

    registry_entry = er.async_get(hass).async_get(UI_ENTITY)
    assert registry_entry is not None
    assert registry_entry.unique_id == entry.entry_id


async def test_ui_alert_fires_and_acknowledges(hass: HomeAssistant) -> None:
    """It runs the same state machine as a YAML one."""
    calls = async_mock_service(hass, "notify", "notify")
    await _add_ui_alert(hass)

    hass.states.async_set(UI_WATCHED, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(UI_ENTITY).state == STATE_ON
    assert [call.data["message"] for call in calls] == ["Front door"]

    await hass.services.async_call(
        ALERT_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: UI_ENTITY}, blocking=True
    )
    assert hass.states.get(UI_ENTITY).state == STATE_OFF


async def test_unloading_removes_the_alert(hass: HomeAssistant) -> None:
    """Removing the config entry takes its alert with it."""
    async_mock_service(hass, "notify", "notify")
    entry = await _add_ui_alert(hass)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # The registry keeps the entry, so it lingers as a restored placeholder.
    assert hass.states.get(UI_ENTITY).state == STATE_UNAVAILABLE


async def test_removing_the_entry_removes_the_registry_entry(
    hass: HomeAssistant,
) -> None:
    """Deleting the helper takes its registry entry with it.

    This only works because the entity is tied to its config entry, which is
    what going through the alert platform buys.
    """
    async_mock_service(hass, "notify", "notify")
    entry = await _add_ui_alert(hass)
    assert er.async_get(hass).async_get(UI_ENTITY) is not None

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert er.async_get(hass).async_get(UI_ENTITY) is None


async def test_yaml_and_ui_alerts_live_side_by_side(hass: HomeAssistant) -> None:
    """Both sources are usable at once; neither disturbs the other."""
    calls = async_mock_service(hass, "notify", "notify")
    hass.states.async_set(YAML_WATCHED, STATE_OFF)
    assert await async_setup_component(hass, DOMAIN, YAML_CONFIG)
    await hass.async_block_till_done()

    await _add_ui_alert(hass)

    assert hass.states.get(YAML_ENTITY).state == STATE_IDLE
    assert hass.states.get(UI_ENTITY).state == STATE_IDLE

    hass.states.async_set(UI_WATCHED, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(UI_ENTITY).state == STATE_ON
    assert hass.states.get(YAML_ENTITY).state == STATE_IDLE
    assert [call.data["message"] for call in calls] == ["Front door"]
