"""Tests for alerts declared in YAML."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.const import CONF_ENTITY_ID, CONF_STATE, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.alert_plus.const import (
    CONF_CAN_ACKNOWLEDGE,
    CONF_NOTIFIERS,
    CONF_SKIP_FIRST,
    DOMAIN,
)

WATCHED = "binary_sensor.ico_data_freshness"
OBJECT_ID = "ico_disconnected_alert"
ALERT_ENTITY = f"binary_sensor.{OBJECT_ID}"
ACK_ENTITY = f"switch.{OBJECT_ID}_acknowledged"


def _yaml(**overrides: Any) -> dict[str, Any]:
    """Return an `alert_plus:` block, in core `alert:` syntax."""
    alert = {
        "name": "Alerte Ico deconnecte",
        "message": "Ico deconnecte depuis {{ states('sensor.plouf') }}",
        "done_message": "Ico de nouveau connecte",
        "entity_id": WATCHED,
        "state": "on",
        "repeat": 180,
        "can_acknowledge": True,
        "skip_first": False,
        "notifiers": ["notify"],
    } | overrides
    return {DOMAIN: {OBJECT_ID: alert}}


async def _setup_yaml(hass: HomeAssistant, **overrides: Any) -> None:
    """Set up the integration from a YAML block, watching an idle entity."""
    hass.states.async_set(WATCHED, STATE_OFF)
    hass.states.async_set("sensor.plouf", "12h")
    assert await async_setup_component(hass, DOMAIN, _yaml(**overrides))
    await hass.async_block_till_done()


async def test_yaml_alert_is_registry_backed(hass: HomeAssistant) -> None:
    """The whole point: a YAML alert still gets a unique ID and a registry entry.

    That is what makes its icon, area and name editable from the frontend,
    which core `alert:` never allowed.
    """
    await _setup_yaml(hass)
    registry = er.async_get(hass)

    alert = registry.async_get(ALERT_ENTITY)
    assert alert is not None
    # The YAML key is the unique ID, so it survives renames of the display name.
    assert alert.unique_id == OBJECT_ID

    ack = registry.async_get(ACK_ENTITY)
    assert ack is not None
    assert ack.unique_id == f"{OBJECT_ID}-acknowledged"


async def test_yaml_alert_notifies_and_repeats(hass: HomeAssistant) -> None:
    """A YAML alert behaves exactly like a UI one."""
    calls = async_mock_service(hass, "notify", "notify")
    await _setup_yaml(hass)

    hass.states.async_set(WATCHED, STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get(ALERT_ENTITY).state == STATE_ON
    assert len(calls) == 1
    assert calls[0].data["message"] == "Ico deconnecte depuis 12h"

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=181))
    await hass.async_block_till_done()
    assert len(calls) == 2

    hass.states.async_set(WATCHED, STATE_OFF)
    await hass.async_block_till_done()
    assert calls[-1].data["message"] == "Ico de nouveau connecte"


async def test_yaml_alert_skip_first_and_acknowledge(hass: HomeAssistant) -> None:
    """skip_first and the acknowledgement switch work on the YAML path too."""
    calls = async_mock_service(hass, "notify", "notify")
    await _setup_yaml(hass, **{CONF_SKIP_FIRST: True})

    hass.states.async_set(WATCHED, STATE_ON)
    await hass.async_block_till_done()
    assert len(calls) == 0

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": ACK_ENTITY}, blocking=True
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=181))
    await hass.async_block_till_done()
    assert len(calls) == 0


async def test_yaml_alert_without_acknowledgement_has_no_switch(
    hass: HomeAssistant,
) -> None:
    """can_acknowledge: false drops the switch, as in core alert."""
    await _setup_yaml(hass, **{CONF_CAN_ACKNOWLEDGE: False})

    assert hass.states.get(ALERT_ENTITY) is not None
    assert hass.states.get(ACK_ENTITY) is None


async def test_yaml_and_ui_alerts_live_side_by_side(hass: HomeAssistant) -> None:
    """Both sources are usable at once; neither disturbs the other."""
    calls = async_mock_service(hass, "notify", "notify")
    await _setup_yaml(hass)

    hass.states.async_set("binary_sensor.other", STATE_OFF)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Alerte UI",
        options={
            CONF_ENTITY_ID: "binary_sensor.other",
            CONF_STATE: STATE_ON,
            "repeat": [30.0],
            CONF_SKIP_FIRST: False,
            CONF_CAN_ACKNOWLEDGE: True,
            CONF_NOTIFIERS: ["notify"],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(ALERT_ENTITY) is not None
    assert hass.states.get("binary_sensor.alerte_ui") is not None

    # Firing the UI alert leaves the YAML one alone.
    hass.states.async_set("binary_sensor.other", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.alerte_ui").state == STATE_ON
    assert hass.states.get(ALERT_ENTITY).state == STATE_OFF
    assert [call.data["message"] for call in calls] == ["Alerte UI"]
