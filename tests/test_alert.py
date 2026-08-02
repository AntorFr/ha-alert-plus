"""Tests for the Alert Plus runtime."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ENTITY_ID,
    CONF_REPEAT,
    CONF_STATE,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.alert_plus.const import (
    ATTR_ACKNOWLEDGED,
    CONF_CAN_ACKNOWLEDGE,
    CONF_DONE_MESSAGE,
    CONF_MESSAGE,
    CONF_NOTIFIERS,
    CONF_SKIP_FIRST,
    DOMAIN,
)

WATCHED = "binary_sensor.watched"
NOTIFIER = "test_notifier"
ALERT_ENTITY = "binary_sensor.front_door"
ACK_ENTITY = "switch.front_door_acknowledged"


def _options(**overrides: Any) -> dict[str, Any]:
    """Return config entry options, overridable per test."""
    return {
        CONF_ENTITY_ID: WATCHED,
        CONF_STATE: STATE_ON,
        CONF_REPEAT: [30.0],
        CONF_SKIP_FIRST: False,
        CONF_CAN_ACKNOWLEDGE: True,
        CONF_NOTIFIERS: [NOTIFIER],
    } | overrides


async def _setup(hass: HomeAssistant, **overrides: Any) -> MockConfigEntry:
    """Set up one alert entry, watching an entity that starts idle."""
    hass.states.async_set(WATCHED, STATE_OFF)
    entry = MockConfigEntry(
        domain=DOMAIN, title="Front door", options=_options(**overrides)
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _fire(hass: HomeAssistant, minutes: float) -> None:
    """Jump forward in time and let scheduled work run."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=minutes))
    await hass.async_block_till_done()


async def _set_watched(hass: HomeAssistant, state: str) -> None:
    """Move the watched entity and let the alert react."""
    hass.states.async_set(WATCHED, state)
    await hass.async_block_till_done()


async def test_notifies_on_trigger_and_repeats(hass: HomeAssistant) -> None:
    """An alert notifies immediately, then again after the repeat delay."""
    calls = async_mock_service(hass, "notify", NOTIFIER)
    await _setup(hass)

    await _set_watched(hass, STATE_ON)
    assert hass.states.get(ALERT_ENTITY).state == STATE_ON
    assert len(calls) == 1
    assert calls[0].data["message"] == "Front door"

    await _fire(hass, 31)
    assert len(calls) == 2

    await _set_watched(hass, STATE_OFF)
    assert hass.states.get(ALERT_ENTITY).state == STATE_OFF

    await _fire(hass, 31)
    assert len(calls) == 2


async def test_message_template_is_rendered(hass: HomeAssistant) -> None:
    """The message template wins over the alert name."""
    calls = async_mock_service(hass, "notify", NOTIFIER)
    await _setup(
        hass, **{CONF_MESSAGE: "Door is {{ states('binary_sensor.watched') }}"}
    )

    await _set_watched(hass, STATE_ON)
    assert calls[0].data["message"] == "Door is on"


async def test_skip_first_waits_for_the_delay(hass: HomeAssistant) -> None:
    """With skip_first the alert stays silent until the first repeat."""
    calls = async_mock_service(hass, "notify", NOTIFIER)
    await _setup(hass, **{CONF_SKIP_FIRST: True})

    await _set_watched(hass, STATE_ON)
    assert hass.states.get(ALERT_ENTITY).state == STATE_ON
    assert len(calls) == 0

    await _fire(hass, 31)
    assert len(calls) == 1


async def test_done_message_only_after_a_notification(hass: HomeAssistant) -> None:
    """The done message is sent on recovery, but only if anyone was told."""
    calls = async_mock_service(hass, "notify", NOTIFIER)
    await _setup(hass, **{CONF_DONE_MESSAGE: "All good"})

    await _set_watched(hass, STATE_ON)
    await _set_watched(hass, STATE_OFF)
    assert [call.data["message"] for call in calls] == ["Front door", "All good"]


async def test_done_message_skipped_when_acknowledged_early(
    hass: HomeAssistant,
) -> None:
    """An alert that never notified does not announce its recovery."""
    calls = async_mock_service(hass, "notify", NOTIFIER)
    await _setup(hass, **{CONF_SKIP_FIRST: True, CONF_DONE_MESSAGE: "All good"})

    await _set_watched(hass, STATE_ON)
    await _set_watched(hass, STATE_OFF)
    assert calls == []


async def test_repeat_delays_escalate(hass: HomeAssistant) -> None:
    """Several delays are walked through, then the last one repeats forever."""
    calls = async_mock_service(hass, "notify", NOTIFIER)
    await _setup(hass, **{CONF_REPEAT: [1.0, 5.0]})

    await _set_watched(hass, STATE_ON)
    assert len(calls) == 1

    await _fire(hass, 1.5)
    assert len(calls) == 2

    # The second delay is five minutes, so 1.5 more is not enough.
    await _fire(hass, 3)
    assert len(calls) == 2

    await _fire(hass, 7)
    assert len(calls) == 3


async def test_acknowledging_mutes_then_resumes(hass: HomeAssistant) -> None:
    """The acknowledgement switch mutes repeats and unmuting brings them back."""
    calls = async_mock_service(hass, "notify", NOTIFIER)
    await _setup(hass)

    await _set_watched(hass, STATE_ON)
    assert len(calls) == 1

    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: ACK_ENTITY}, blocking=True
    )
    assert hass.states.get(ACK_ENTITY).state == STATE_ON
    assert hass.states.get(ALERT_ENTITY).attributes[ATTR_ACKNOWLEDGED] is True

    await _fire(hass, 31)
    assert len(calls) == 1

    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: ACK_ENTITY}, blocking=True
    )
    await _fire(hass, 31)
    assert len(calls) == 2


async def test_acknowledgement_clears_when_the_alert_ends(
    hass: HomeAssistant,
) -> None:
    """A new occurrence starts unacknowledged."""
    async_mock_service(hass, "notify", NOTIFIER)
    await _setup(hass)

    await _set_watched(hass, STATE_ON)
    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: ACK_ENTITY}, blocking=True
    )
    await _set_watched(hass, STATE_OFF)

    assert hass.states.get(ACK_ENTITY).state == STATE_OFF


async def test_no_switch_when_acknowledgement_is_disabled(
    hass: HomeAssistant,
) -> None:
    """Alerts that cannot be acknowledged do not expose a switch."""
    await _setup(hass, **{CONF_CAN_ACKNOWLEDGE: False})

    assert hass.states.get(ALERT_ENTITY) is not None
    assert hass.states.get(ACK_ENTITY) is None


async def test_already_firing_at_startup(hass: HomeAssistant) -> None:
    """A condition already met when the entry loads raises the alert."""
    calls = async_mock_service(hass, "notify", NOTIFIER)
    hass.states.async_set(WATCHED, STATE_ON)

    entry = MockConfigEntry(domain=DOMAIN, title="Front door", options=_options())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(ALERT_ENTITY).state == STATE_ON
    assert len(calls) == 1


async def test_entities_are_registered_with_stable_unique_ids(
    hass: HomeAssistant,
) -> None:
    """The whole point: registry entries, so the frontend can configure them."""
    entry = await _setup(hass)
    registry = er.async_get(hass)

    alert = registry.async_get(ALERT_ENTITY)
    assert alert is not None
    assert alert.unique_id == entry.entry_id
    assert alert.config_entry_id == entry.entry_id

    ack = registry.async_get(ACK_ENTITY)
    assert ack is not None
    assert ack.unique_id == f"{entry.entry_id}-acknowledged"


async def test_unload_stops_the_alert(hass: HomeAssistant) -> None:
    """Unloading removes the entities and cancels pending notifications."""
    calls: list[ServiceCall] = async_mock_service(hass, "notify", NOTIFIER)
    entry = await _setup(hass)

    await _set_watched(hass, STATE_ON)
    assert len(calls) == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # The registry keeps the entity, so it lingers as a restored placeholder.
    assert hass.states.get(ALERT_ENTITY).state == STATE_UNAVAILABLE

    await _fire(hass, 31)
    assert len(calls) == 1
