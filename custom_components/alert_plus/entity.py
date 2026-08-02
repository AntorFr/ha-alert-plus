"""The alert entity.

Behaves exactly like core's ``AlertEntity`` — same domain, same ``idle`` / ``on``
/ ``off`` states, same acknowledgement semantics — with a unique ID, so it lands
in the entity registry and the frontend can configure it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, override

from homeassistant.components.notify import (
    ATTR_DATA,
    ATTR_MESSAGE,
    ATTR_TITLE,
    DOMAIN as NOTIFY_DOMAIN,
    SERVICE_SEND_MESSAGE,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ICON,
    CONF_REPEAT,
    CONF_STATE,
    EVENT_HOMEASSISTANT_STOP,
    STATE_IDLE,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HassJob,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import (
    ServiceNotFound,
    ServiceValidationError,
    TemplateError,
)
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_CAN_ACKNOWLEDGE,
    ATTR_NEXT_NOTIFICATION,
    ATTR_NOTIFICATION_COUNT,
    ATTR_WATCHED_ENTITY_ID,
    CONF_CAN_ACKNOWLEDGE,
    CONF_DATA,
    CONF_DONE_MESSAGE,
    CONF_MESSAGE,
    CONF_NOTIFIERS,
    CONF_NOTIFY_ENTITIES,
    CONF_SKIP_FIRST,
    CONF_TITLE,
    DOMAIN,
    ENTITY_ID_FORMAT,
    LOGGER,
)


class AlertPlusEntity(RestoreEntity):
    """Repeat a notification while a watched entity sits in the alerting state."""

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        name: str,
        unique_id: str,
        object_id: str,
        watched_entity_id: str,
        options: Mapping[str, Any],
    ) -> None:
        """Initialize an alert.

        Options come either from a YAML block or from a config entry, so this
        takes a plain mapping rather than either of them.
        """
        self.hass = hass
        self.entity_id = ENTITY_ID_FORMAT.format(object_id)
        self._attr_name = name
        self._attr_unique_id = unique_id
        # Only a default: an icon set from the frontend lands in the registry,
        # and the registry wins over this.
        self._attr_icon = options.get(CONF_ICON)

        self._watched_entity_id = watched_entity_id
        self._alert_state: str = options[CONF_STATE]
        self._delays = [timedelta(minutes=value) for value in options[CONF_REPEAT]]
        self._skip_first: bool = options[CONF_SKIP_FIRST]
        self._can_acknowledge: bool = options[CONF_CAN_ACKNOWLEDGE]

        self._notifiers: list[str] = options.get(CONF_NOTIFIERS, [])
        self._notify_entities: list[str] = options.get(CONF_NOTIFY_ENTITIES, [])
        self._notification_data: dict[str, Any] | None = options.get(CONF_DATA)

        self._message_template = self._build_template(options.get(CONF_MESSAGE))
        self._done_message_template = self._build_template(
            options.get(CONF_DONE_MESSAGE)
        )
        self._title_template = self._build_template(options.get(CONF_TITLE))

        self._firing = False
        self._acknowledged = False
        self._notification_count = 0
        self._next_delay_index = 0
        self._next_notification: datetime | None = None
        self._cancel_scheduled: CALLBACK_TYPE | None = None

    def _build_template(self, value: str | None) -> Template | None:
        """Compile an optional template from its source string."""
        if value is None:
            return None
        return Template(value, self.hass)

    @property
    @override
    def state(self) -> str:
        """Return the alert state, exactly as core alert reports it."""
        if self._firing:
            return STATE_OFF if self._acknowledged else STATE_ON
        return STATE_IDLE

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the details an automation or dashboard may want."""
        return {
            ATTR_WATCHED_ENTITY_ID: self._watched_entity_id,
            ATTR_CAN_ACKNOWLEDGE: self._can_acknowledge,
            ATTR_NOTIFICATION_COUNT: self._notification_count,
            ATTR_NEXT_NOTIFICATION: (
                self._next_notification.isoformat() if self._next_notification else None
            ),
        }

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the acknowledgement, then start watching."""
        await super().async_added_to_hass()

        # Core forgot the acknowledgement on every restart, so a problem you had
        # already silenced started shouting again on the way back up.
        if (last_state := await self.async_get_last_state()) is not None:
            self._acknowledged = last_state.state == STATE_OFF and self._can_acknowledge

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._watched_entity_id], self._async_watched_changed
            )
        )
        # Deferred to startup so the watched entity has settled on a real state
        # rather than being briefly unknown.
        self.async_on_remove(async_at_started(self.hass, self._async_initial_check))
        self.async_on_remove(
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_stop)
        )

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Drop the pending notification when the alert goes away."""
        self._async_cancel_scheduled()
        await super().async_will_remove_from_hass()

    @callback
    def _async_stop(self, _event: Event) -> None:
        """Disarm the repeat timer when Home Assistant stops.

        Entities are not removed on shutdown, so nothing else would cancel it.
        """
        self._async_cancel_scheduled()

    async def _async_initial_check(self, _hass: HomeAssistant) -> None:
        """Fire straight away when the condition is already met at startup.

        Core only reacted to state *changes*, so a problem present across a
        restart stayed silent. Restoring the acknowledgement is what keeps this
        from turning every restart into a notification.
        """
        state = self.hass.states.get(self._watched_entity_id)
        if state is not None and state.state == self._alert_state:
            await self._async_begin(reset_acknowledgement=False)

    async def _async_watched_changed(self, event: Event[EventStateChangedData]) -> None:
        """Start or stop the alert when the watched entity moves."""
        if (to_state := event.data["new_state"]) is None:
            return

        if to_state.state == self._alert_state:
            if not self._firing:
                await self._async_begin(reset_acknowledgement=True)
        elif self._firing:
            await self._async_end()

    async def _async_begin(self, *, reset_acknowledgement: bool) -> None:
        """Enter the firing state and open the notification cycle."""
        LOGGER.debug("Alert %s started firing", self.name)
        self._firing = True
        self._notification_count = 0
        self._next_delay_index = 0
        if reset_acknowledgement:
            self._acknowledged = False

        if not self._acknowledged:
            if self._skip_first:
                self._async_schedule_notification()
            else:
                await self._async_send_notification()

        self.async_write_ha_state()

    async def _async_end(self) -> None:
        """Leave the firing state and send the done message, if any."""
        LOGGER.debug("Alert %s stopped firing", self.name)
        self._async_cancel_scheduled()
        self._firing = False

        # Only report the recovery to people who were told about the problem.
        send_done = self._notification_count > 0

        self._acknowledged = False
        self._notification_count = 0
        self._next_delay_index = 0

        if (
            send_done
            and self._done_message_template is not None
            and (message := self._render(self._done_message_template)) is not None
        ):
            await self._async_dispatch(message)

        self.async_write_ha_state()

    @callback
    def _async_schedule_notification(self) -> None:
        """Arm the timer for the next repetition."""
        self._async_cancel_scheduled()

        delay = self._delays[self._next_delay_index]
        # Walk down the escalation list, then stay on its last value forever.
        self._next_delay_index = min(self._next_delay_index + 1, len(self._delays) - 1)

        self._next_notification = dt_util.utcnow() + delay
        self._cancel_scheduled = async_track_point_in_time(
            self.hass,
            HassJob(
                self._async_repeat,
                name=f"alert_plus repeat {self.name}",
                cancel_on_shutdown=True,
            ),
            self._next_notification,
        )

    @callback
    def _async_cancel_scheduled(self) -> None:
        """Disarm the repetition timer."""
        if self._cancel_scheduled is not None:
            self._cancel_scheduled()
            self._cancel_scheduled = None
        self._next_notification = None

    async def _async_repeat(self, _now: datetime) -> None:
        """Send the next repetition of a still-unacknowledged alert."""
        self._cancel_scheduled = None
        if not self._firing or self._acknowledged:
            return

        await self._async_send_notification()
        self.async_write_ha_state()

    async def _async_send_notification(self) -> None:
        """Send the alert message, then arm the next repetition."""
        message = self.name
        if (
            self._message_template is not None
            and (rendered := self._render(self._message_template)) is not None
        ):
            message = rendered

        await self._async_dispatch(message)
        self._notification_count += 1
        self._async_schedule_notification()

    def _render(self, template: Template) -> str | None:
        """Render a template, returning None when it fails at runtime."""
        try:
            return template.async_render(parse_result=False)
        except TemplateError as err:
            LOGGER.error(
                "Alert %s could not render one of its templates: %s", self.name, err
            )
            return None

    async def _async_dispatch(self, message: str) -> None:
        """Deliver a message to every configured notifier."""
        title: str | None = None
        if self._title_template is not None:
            title = self._render(self._title_template)

        for notifier in self._notifiers:
            payload: dict[str, Any] = {ATTR_MESSAGE: message}
            if title is not None:
                payload[ATTR_TITLE] = title
            if self._notification_data:
                payload[ATTR_DATA] = self._notification_data
            await self._async_call_notify(notifier, payload)

        if self._notify_entities:
            payload = {ATTR_ENTITY_ID: self._notify_entities, ATTR_MESSAGE: message}
            if title is not None:
                payload[ATTR_TITLE] = title
            # Notify entities take no free-form ``data`` payload, unlike the
            # legacy notify services.
            await self._async_call_notify(SERVICE_SEND_MESSAGE, payload)

    async def _async_call_notify(self, service: str, payload: dict[str, Any]) -> None:
        """Call a notify service, surviving a notifier that is not loaded."""
        try:
            await self.hass.services.async_call(
                NOTIFY_DOMAIN, service, payload, context=self._context
            )
        except ServiceNotFound:
            LOGGER.error(
                "Alert %s could not call notify.%s, retrying at the next repetition",
                self.name,
                service,
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Unacknowledge the alert, as core alert's turn_on does."""
        if not self._acknowledged:
            return

        self._acknowledged = False
        if self._firing:
            self._async_schedule_notification()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Acknowledge the alert, as core alert's turn_off does."""
        if not self._can_acknowledge:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="cannot_acknowledge",
                translation_placeholders={"name": str(self.name)},
            )
        if self._acknowledged:
            return

        self._acknowledged = True
        self._async_cancel_scheduled()
        self.async_write_ha_state()

    async def async_toggle(self, **kwargs: Any) -> None:
        """Flip the acknowledgement."""
        if self._acknowledged:
            await self.async_turn_on()
            return
        await self.async_turn_off()
