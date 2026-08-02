"""Tests for alerts declared in YAML, checked against core alert's behaviour."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_ICON,
    SERVICE_TOGGLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_IDLE,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.alert_plus.const import (
    ALERT_DOMAIN,
    ATTR_NOTIFICATION_COUNT,
    CONF_CAN_ACKNOWLEDGE,
    CONF_DONE_MESSAGE,
    CONF_MESSAGE,
    CONF_SKIP_FIRST,
    DOMAIN,
)

WATCHED = "binary_sensor.smoke"
OBJECT_ID = "fire_alert"
# The whole point: the entity id core alert produced, unchanged.
ALERT_ENTITY = f"{ALERT_DOMAIN}.{OBJECT_ID}"


def _config(**overrides: Any) -> dict[str, Any]:
    """Return an `alert_plus:` block, in core `alert:` syntax."""
    alert = {
        "name": "Fire alert",
        "entity_id": WATCHED,
        "state": "on",
        "repeat": 30,
        "notifiers": ["notify"],
    } | overrides
    return {DOMAIN: {OBJECT_ID: alert}}


async def _setup(hass: HomeAssistant, **overrides: Any) -> None:
    """Set up one YAML alert, watching an entity that starts idle."""
    hass.states.async_set(WATCHED, STATE_OFF)
    assert await async_setup_component(hass, DOMAIN, _config(**overrides))
    await hass.async_block_till_done()


async def _set_watched(hass: HomeAssistant, state: str) -> None:
    """Move the watched entity and let the alert react."""
    hass.states.async_set(WATCHED, state)
    await hass.async_block_till_done()


async def _fire(hass: HomeAssistant, minutes: float) -> None:
    """Jump forward in time and let scheduled work run."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=minutes))
    await hass.async_block_till_done()


async def _call(hass: HomeAssistant, service: str) -> None:
    """Call one of the alert domain services on our alert."""
    await hass.services.async_call(
        ALERT_DOMAIN, service, {ATTR_ENTITY_ID: ALERT_ENTITY}, blocking=True
    )


async def test_entity_id_and_states_match_core_alert(hass: HomeAssistant) -> None:
    """The alert keeps core's entity id and its idle/on/off state machine."""
    async_mock_service(hass, "notify", "notify")
    await _setup(hass)

    assert hass.states.get(ALERT_ENTITY).state == STATE_IDLE

    await _set_watched(hass, STATE_ON)
    assert hass.states.get(ALERT_ENTITY).state == STATE_ON

    await _call(hass, SERVICE_TURN_OFF)
    # Acknowledged while still firing: core reported that as 'off'.
    assert hass.states.get(ALERT_ENTITY).state == STATE_OFF

    await _set_watched(hass, STATE_OFF)
    assert hass.states.get(ALERT_ENTITY).state == STATE_IDLE


async def test_alert_is_registry_backed(hass: HomeAssistant) -> None:
    """What core never had: a unique ID, so the frontend can configure it."""
    await _setup(hass)
    entry = er.async_get(hass).async_get(ALERT_ENTITY)

    assert entry is not None
    assert entry.unique_id == OBJECT_ID


async def test_icon_is_set_from_yaml(hass: HomeAssistant) -> None:
    """The icon option shows up on the entity."""
    await _setup(hass, icon="mdi:fire")
    assert hass.states.get(ALERT_ENTITY).attributes[ATTR_ICON] == "mdi:fire"


async def test_icon_from_the_frontend_wins_over_yaml(hass: HomeAssistant) -> None:
    """The YAML icon is only a default; the registry overrides it.

    That layering is the reason the icon option can exist at all: without a
    unique ID there would be no registry entry to override it from.
    """
    await _setup(hass, icon="mdi:fire")

    er.async_get(hass).async_update_entity(ALERT_ENTITY, icon="mdi:water")
    await hass.async_block_till_done()

    assert hass.states.get(ALERT_ENTITY).attributes[ATTR_ICON] == "mdi:water"


async def test_no_icon_by_default(hass: HomeAssistant) -> None:
    """Leaving the option out leaves the entity iconless, as core was."""
    await _setup(hass)
    assert ATTR_ICON not in hass.states.get(ALERT_ENTITY).attributes


async def test_notifies_and_repeats(hass: HomeAssistant) -> None:
    """An alert notifies immediately, then again after the repeat delay."""
    calls = async_mock_service(hass, "notify", "notify")
    await _setup(hass)

    await _set_watched(hass, STATE_ON)
    assert [call.data["message"] for call in calls] == ["Fire alert"]

    await _fire(hass, 31)
    assert len(calls) == 2
    assert hass.states.get(ALERT_ENTITY).attributes[ATTR_NOTIFICATION_COUNT] == 2

    await _set_watched(hass, STATE_OFF)
    await _fire(hass, 31)
    assert len(calls) == 2


async def test_message_template_is_rendered(hass: HomeAssistant) -> None:
    """The message template wins over the alert name."""
    calls = async_mock_service(hass, "notify", "notify")
    await _setup(hass, **{CONF_MESSAGE: "Smoke is {{ states('binary_sensor.smoke') }}"})

    await _set_watched(hass, STATE_ON)
    assert calls[0].data["message"] == "Smoke is on"


async def test_skip_first_waits_for_the_delay(hass: HomeAssistant) -> None:
    """With skip_first the alert stays silent until the first repeat."""
    calls = async_mock_service(hass, "notify", "notify")
    await _setup(hass, **{CONF_SKIP_FIRST: True})

    await _set_watched(hass, STATE_ON)
    assert hass.states.get(ALERT_ENTITY).state == STATE_ON
    assert len(calls) == 0

    await _fire(hass, 31)
    assert len(calls) == 1


async def test_done_message_only_after_a_notification(hass: HomeAssistant) -> None:
    """The done message is sent on recovery, but only if anyone was told."""
    calls = async_mock_service(hass, "notify", "notify")
    await _setup(hass, **{CONF_DONE_MESSAGE: "All clear"})

    await _set_watched(hass, STATE_ON)
    await _set_watched(hass, STATE_OFF)
    assert [call.data["message"] for call in calls] == ["Fire alert", "All clear"]


async def test_acknowledging_mutes_then_resumes(hass: HomeAssistant) -> None:
    """turn_off acknowledges, turn_on brings the repeats back."""
    calls = async_mock_service(hass, "notify", "notify")
    await _setup(hass)

    await _set_watched(hass, STATE_ON)
    assert len(calls) == 1

    await _call(hass, SERVICE_TURN_OFF)
    await _fire(hass, 31)
    assert len(calls) == 1

    await _call(hass, SERVICE_TURN_ON)
    await _fire(hass, 31)
    assert len(calls) == 2


async def test_toggle_flips_the_acknowledgement(hass: HomeAssistant) -> None:
    """Toggle behaves as core's did."""
    async_mock_service(hass, "notify", "notify")
    await _setup(hass)

    await _set_watched(hass, STATE_ON)
    await _call(hass, SERVICE_TOGGLE)
    assert hass.states.get(ALERT_ENTITY).state == STATE_OFF

    await _call(hass, SERVICE_TOGGLE)
    assert hass.states.get(ALERT_ENTITY).state == STATE_ON


async def test_acknowledging_a_locked_alert_is_refused(hass: HomeAssistant) -> None:
    """can_acknowledge: false rejects turn_off, as core did."""
    async_mock_service(hass, "notify", "notify")
    await _setup(hass, **{CONF_CAN_ACKNOWLEDGE: False})

    await _set_watched(hass, STATE_ON)

    with pytest.raises(ServiceValidationError):
        await _call(hass, SERVICE_TURN_OFF)

    assert hass.states.get(ALERT_ENTITY).state == STATE_ON


async def test_repeat_delays_escalate(hass: HomeAssistant) -> None:
    """Several delays are walked through, then the last one repeats forever."""
    calls = async_mock_service(hass, "notify", "notify")
    await _setup(hass, repeat=[1, 5])

    await _set_watched(hass, STATE_ON)
    assert len(calls) == 1

    await _fire(hass, 1.5)
    assert len(calls) == 2

    # The second delay is five minutes, so 1.5 more is not enough.
    await _fire(hass, 3)
    assert len(calls) == 2

    await _fire(hass, 7)
    assert len(calls) == 3


async def test_already_firing_at_startup(hass: HomeAssistant) -> None:
    """A condition already met when the alert loads raises it.

    Core only reacted to state changes, so this stayed silent.
    """
    calls = async_mock_service(hass, "notify", "notify")
    hass.states.async_set(WATCHED, STATE_ON)

    assert await async_setup_component(hass, DOMAIN, _config())
    await hass.async_block_till_done()

    assert hass.states.get(ALERT_ENTITY).state == STATE_ON
    assert len(calls) == 1
