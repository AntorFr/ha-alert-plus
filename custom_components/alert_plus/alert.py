"""State machine of a single alert.

One config entry holds exactly one alert, so a single :class:`AlertPlusRuntime` is
built per entry, stored in ``entry.runtime_data`` and shared by every platform of
that entry. Keeping the logic here rather than on an entity means the alert keeps
firing and notifying regardless of which entities the user chose to expose.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.notify import (
    ATTR_DATA,
    ATTR_MESSAGE,
    ATTR_TITLE,
    DOMAIN as NOTIFY_DOMAIN,
    SERVICE_SEND_MESSAGE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, CONF_REPEAT, CONF_STATE
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
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CAN_ACKNOWLEDGE,
    CONF_DATA,
    CONF_DONE_MESSAGE,
    CONF_MESSAGE,
    CONF_NOTIFIERS,
    CONF_NOTIFY_ENTITIES,
    CONF_SKIP_FIRST,
    CONF_TITLE,
    DOMAIN,
    LOGGER,
)

type AlertPlusConfigEntry = ConfigEntry[AlertPlusRuntime]


class AlertPlusRuntime:
    """Track a watched entity and repeat notifications while it misbehaves."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: AlertPlusConfigEntry,
        watched_entity_id: str,
    ) -> None:
        """Initialize the alert from its config entry options."""
        self.hass = hass
        self.entry = entry
        self.watched_entity_id = watched_entity_id

        options = entry.options
        self._alert_state: str = options[CONF_STATE]
        self._delays = [timedelta(minutes=value) for value in options[CONF_REPEAT]]
        self._skip_first: bool = options[CONF_SKIP_FIRST]
        self.can_acknowledge: bool = options[CONF_CAN_ACKNOWLEDGE]

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
        self._listeners: list[CALLBACK_TYPE] = []

    def _build_template(self, value: str | None) -> Template | None:
        """Compile an optional template from the stored option string."""
        if value is None:
            return None
        return Template(value, self.hass)

    @property
    def name(self) -> str:
        """Return the alert name, which is the config entry title."""
        return self.entry.title

    @property
    def is_firing(self) -> bool:
        """Return whether the watched condition is currently met."""
        return self._firing

    @property
    def acknowledged(self) -> bool:
        """Return whether notifications are muted for the current occurrence."""
        return self._acknowledged

    @property
    def notification_count(self) -> int:
        """Return how many notifications the current occurrence has sent."""
        return self._notification_count

    @property
    def next_notification(self) -> datetime | None:
        """Return when the next notification is due, if one is scheduled."""
        return self._next_notification

    @callback
    def async_add_listener(self, update_callback: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Register a callback fired whenever the alert changes state."""
        self._listeners.append(update_callback)

        @callback
        def remove_listener() -> None:
            """Stop notifying this listener."""
            self._listeners.remove(update_callback)

        return remove_listener

    @callback
    def _async_update_listeners(self) -> None:
        """Let every entity of the entry write its new state."""
        for update_callback in list(self._listeners):
            update_callback()

    @callback
    def async_restore_acknowledged(self, acknowledged: bool) -> None:
        """Seed the acknowledgement restored by the switch entity.

        Platforms are set up before :meth:`async_start`, so nothing is in flight
        yet and this cannot race with a scheduled notification.
        """
        self._acknowledged = acknowledged and self.can_acknowledge

    @callback
    def async_start(self) -> None:
        """Start watching the source entity.

        The first evaluation is deferred to Home Assistant start so the watched
        entity has settled on a real state instead of being briefly unknown, and
        so entities of this entry have restored their acknowledgement first.
        """
        self.entry.async_on_unload(
            async_track_state_change_event(
                self.hass, [self.watched_entity_id], self._async_watched_changed
            )
        )
        self.entry.async_on_unload(
            async_at_started(self.hass, self._async_initial_check)
        )
        self.entry.async_on_unload(self._async_cancel_scheduled)

    async def _async_initial_check(self, _hass: HomeAssistant) -> None:
        """Fire straight away when the condition is already met at startup.

        Core's alert integration only reacts to state *changes*, so a problem
        present across a restart stayed silent. Restoring the acknowledgement is
        what keeps this from turning every restart into a notification.
        """
        state = self.hass.states.get(self.watched_entity_id)
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

        self._async_update_listeners()

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

        self._async_update_listeners()

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
        self._async_update_listeners()

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
            await self.hass.services.async_call(NOTIFY_DOMAIN, service, payload)
        except ServiceNotFound:
            LOGGER.error(
                "Alert %s could not call notify.%s, retrying at the next repetition",
                self.name,
                service,
            )

    async def async_acknowledge(self) -> None:
        """Mute notifications until the alert clears."""
        if not self.can_acknowledge:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="cannot_acknowledge",
                translation_placeholders={"name": self.name},
            )
        if self._acknowledged:
            return

        self._acknowledged = True
        self._async_cancel_scheduled()
        self._async_update_listeners()

    async def async_unacknowledge(self) -> None:
        """Resume notifications for an alert that is still firing."""
        if not self._acknowledged:
            return

        self._acknowledged = False
        if self._firing:
            self._async_schedule_notification()
        self._async_update_listeners()
