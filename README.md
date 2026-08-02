# Alert Plus

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)

A UI-configurable take on Home Assistant's `alert` integration.

Watch an entity, and repeat a notification for as long as it stays in the state
you consider a problem — the behaviour of core `alert`, but as a **helper**.

## Why

Core's [`alert`](https://www.home-assistant.io/integrations/alert/) integration
is YAML-only and gives its entities no unique ID. Without a unique ID an entity
is never added to the entity registry, and everything the frontend offers is
therefore unavailable: you cannot rename it, give it an icon, assign it to an
area, hide it, or expose it to a voice assistant.

Development of core `alert` is
[frozen and headed for deprecation](https://github.com/home-assistant/home-assistant.io/issues/42151),
so that is not going to be fixed there.

Alert Plus follows the pattern Home Assistant uses for its own helpers
(`threshold`, `min_max`, `derivative`): **one config entry per alert**. Each
alert is created from the UI, gets a stable unique ID, and its entities behave
like any other registry-backed entity.

## Installation

### HACS

Add `https://github.com/AntorFr/ha-alert-plus` as a custom repository of type
*Integration*, download **Alert Plus**, then restart Home Assistant.

### Manual

Copy `custom_components/alert_plus` into your `custom_components` directory and
restart Home Assistant.

## Usage

**Settings → Devices & services → Helpers → Create helper → Alert Plus.**

| Option | Meaning |
| --- | --- |
| Watched entity | The alert fires while this entity sits in the alerting state |
| Alerting state | State that makes the alert fire (`on` by default) |
| Repeat delays | Minutes between notifications; several values escalate, and the last one repeats forever |
| Skip the first notification | Wait for the first delay instead of notifying immediately |
| Can be acknowledged | Adds a switch that mutes notifications until the alert clears |
| Notify services | Legacy `notify.*` services, without the `notify.` prefix |
| Notify entities | `notify` entities to send the message to |
| Message / Notification title / Done message | Templates; the message defaults to the alert name |
| Notification data | Extra payload for the legacy notify services (notify entities ignore it) |

### Entities

Each alert creates:

- `binary_sensor.<name>` — device class `problem`, `on` while the alert fires.
  Attributes: `acknowledged`, `can_acknowledge`, `notification_count`,
  `next_notification`, `watched_entity_id`.
- `switch.<name>_acknowledged` — only when acknowledgement is allowed. Turning
  it on mutes the repeats; it clears by itself once the alert ends.

Both are in the entity registry, so name, icon, area and visibility are yours to
set from the UI.

## Differences from core `alert`

| Core `alert` | Alert Plus |
| --- | --- |
| YAML only | Created and edited from the UI |
| No unique ID, no registry entry | Registry-backed, fully configurable from the frontend |
| One entity with `idle` / `on` / `off` | A `problem` binary sensor plus a separate acknowledgement switch |
| Acknowledgement lost on restart | Acknowledgement restored across restarts |
| A problem present at startup stays silent until the next state change | Evaluated at startup |
| Legacy `notify.*` services only | Legacy services **and** `notify` entities |

### Migrating from core `alert`

Options map one-to-one onto the YAML keys: `entity_id`, `state`, `repeat`,
`skip_first`, `can_acknowledge`, `message`, `done_message`, `title`, `data` and
`notifiers`. Recreate each alert as a helper, then delete the `alert:` block.

Entity IDs change (`alert.foo` becomes `binary_sensor.foo`), so automations
referring to your alerts need updating.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

CI runs hassfest, HACS validation, ruff and the test suite.

## Status

Early but tested. The long-term goal is to propose this to Home Assistant core
as a helper integration, which is why the code sticks to core conventions and
lints with core's ruleset.
