"""Tests for the alert_plus.reload service."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from homeassistant import config as hass_config
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_REPEAT,
    CONF_STATE,
    SERVICE_RELOAD,
    STATE_IDLE,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
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

WATCHED = "binary_sensor.smoke"
YAML_ENTITY = f"{ALERT_DOMAIN}.fire_alert"
RELOADED_ENTITY = f"{ALERT_DOMAIN}.reloaded_alert"
UI_ENTITY = f"{ALERT_DOMAIN}.front_door"

INITIAL_YAML: dict[str, Any] = {
    DOMAIN: {
        "fire_alert": {
            "name": "Fire alert",
            "entity_id": WATCHED,
            "repeat": 30,
            "notifiers": ["notify"],
        }
    }
}


async def _reload(hass: HomeAssistant, fixture: str) -> None:
    """Call the reload service against a given configuration.yaml."""
    path = str(Path(__file__).parent / "fixtures" / fixture)
    with patch.object(hass_config, "YAML_CONFIG_FILE", path):
        await hass.services.async_call(DOMAIN, SERVICE_RELOAD, blocking=True)
        await hass.async_block_till_done()


async def _setup_yaml(hass: HomeAssistant) -> None:
    """Set up one YAML alert, watching an entity that starts idle."""
    hass.states.async_set(WATCHED, STATE_OFF)
    assert await async_setup_component(hass, DOMAIN, INITIAL_YAML)
    await hass.async_block_till_done()


async def _add_ui_alert(hass: HomeAssistant) -> MockConfigEntry:
    """Add an alert created from the UI, watching its own entity."""
    hass.states.async_set("binary_sensor.door", STATE_OFF)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Front door",
        options={
            CONF_ENTITY_ID: "binary_sensor.door",
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


async def test_reload_service_is_registered(hass: HomeAssistant) -> None:
    """The service exists as soon as the integration is set up."""
    await _setup_yaml(hass)
    assert hass.services.has_service(DOMAIN, SERVICE_RELOAD)


async def test_reload_swaps_the_yaml_alerts(hass: HomeAssistant) -> None:
    """Reloading drops the old YAML alerts and builds the new ones."""
    async_mock_service(hass, "notify", "notify")
    await _setup_yaml(hass)
    assert hass.states.get(YAML_ENTITY).state == STATE_IDLE

    await _reload(hass, "reload_configuration.yaml")

    assert hass.states.get(RELOADED_ENTITY).state == STATE_IDLE
    removed = hass.states.get(YAML_ENTITY)
    assert removed is None or removed.state == STATE_UNAVAILABLE


async def test_reloaded_alert_actually_fires(hass: HomeAssistant) -> None:
    """The rebuilt alert is live, not just a state in the machine."""
    calls = async_mock_service(hass, "notify", "notify")
    await _setup_yaml(hass)
    await _reload(hass, "reload_configuration.yaml")

    hass.states.async_set(WATCHED, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(RELOADED_ENTITY).state == STATE_ON
    assert [call.data["message"] for call in calls] == ["Reloaded alert"]


async def test_reload_leaves_config_entry_alerts_alone(hass: HomeAssistant) -> None:
    """Reloading YAML must not disturb the alerts created from the UI."""
    calls = async_mock_service(hass, "notify", "notify")
    await _setup_yaml(hass)
    await _add_ui_alert(hass)
    assert hass.states.get(UI_ENTITY).state == STATE_IDLE

    await _reload(hass, "reload_configuration.yaml")

    # Still there, and still watching: removing the wrong entities would have
    # taken it out silently.
    assert hass.states.get(UI_ENTITY).state == STATE_IDLE

    hass.states.async_set("binary_sensor.door", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(UI_ENTITY).state == STATE_ON
    assert [call.data["message"] for call in calls] == ["Front door"]


async def test_reload_with_invalid_yaml_keeps_the_running_alerts(
    hass: HomeAssistant,
) -> None:
    """A typo in the YAML must not take the live alerts down."""
    calls = async_mock_service(hass, "notify", "notify")
    await _setup_yaml(hass)

    await _reload(hass, "invalid_configuration.yaml")

    assert hass.states.get(YAML_ENTITY).state == STATE_IDLE

    hass.states.async_set(WATCHED, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(YAML_ENTITY).state == STATE_ON
    assert len(calls) == 1
