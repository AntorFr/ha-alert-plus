# Alert Plus

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)

A take on Home Assistant's `alert` integration whose entities are real registry
entities — configurable in YAML, in the UI, or both at once.

Watch an entity, and repeat a notification for as long as it stays in the state
you consider a problem.

## Why

Core's [`alert`](https://www.home-assistant.io/integrations/alert/) integration
gives its entities no unique ID. Without one, an entity never reaches the entity
registry, and everything the frontend offers is unavailable: you cannot rename
it, give it an icon, assign it to an area, hide it, or expose it to a voice
assistant.

Development of core `alert` is
[frozen and headed for deprecation](https://github.com/home-assistant/home-assistant.io/issues/42151),
so that is not going to be fixed there.

Alert Plus fixes it without taking YAML away.

## Installation

### HACS

Add `https://github.com/AntorFr/ha-alert-plus` as a custom repository of type
*Integration*, download **Alert Plus**, then restart Home Assistant.

### Manual

Copy `custom_components/alert_plus` into your `custom_components` directory and
restart Home Assistant.

## Two ways to declare an alert

Both work at the same time, and neither is a migration path for the other. Use
YAML for what you want versioned in git, the UI for the rest.

### YAML

Under an `alert_plus:` key, using the **exact schema of core `alert:`**:

```yaml
alert_plus:
  ico_disconnected_alert:
    name: "Alerte Ico déconnecté"
    message: >
      "Ico déconnecté depuis {{ relative_time(states.sensor.plouf_oxydo_reduction_potential.last_changed) }}"
    done_message: >
      "Ico de nouveau connecté"
    entity_id: binary_sensor.ico_data_freshness
    state: "on"            # optional, 'on' is the default
    repeat: 180
    can_acknowledge: true  # optional, default is true
    skip_first: true       # optional, default is false
    notifiers:
      - notify
```

YAML stays the source of truth for these alerts: their options are edited in
YAML, and changes need a Home Assistant restart. Their **name, icon, area and
visibility remain editable from the frontend** — that is the point of the unique
ID.

The YAML key is the unique ID *and* the entity object ID, so the alert above
becomes `binary_sensor.ico_disconnected_alert`. Renaming the key creates a new
entity and orphans the old one.

### UI

**Settings → Devices & services → Helpers → Create helper → Alert Plus.** One
config entry per alert, everything editable from the frontend, no restart.

## Options

| Option | Meaning |
| --- | --- |
| `entity_id` | The alert fires while this entity sits in the alerting state |
| `state` | State that makes the alert fire (`on` by default) |
| `repeat` | Minutes between notifications; several values escalate, and the last one repeats forever |
| `skip_first` | Wait for the first delay instead of notifying immediately |
| `can_acknowledge` | Adds a switch that mutes notifications until the alert clears |
| `notifiers` | Legacy `notify.*` services, without the `notify.` prefix |
| `notify_entities` | `notify` entities to send the message to (UI only) |
| `message` / `title` / `done_message` | Templates; the message defaults to the alert name |
| `data` | Extra payload for the legacy notify services (notify entities ignore it) |

## Entities

Each alert creates:

- `binary_sensor.<name>` — device class `problem`, `on` while the alert fires.
  Attributes: `acknowledged`, `can_acknowledge`, `notification_count`,
  `next_notification`, `watched_entity_id`.
- `switch.<name>_acknowledged` — only when acknowledgement is allowed. Turning
  it on mutes the repeats; it clears by itself once the alert ends.

Both are in the entity registry whichever way the alert was declared.

## Differences from core `alert`

| Core `alert` | Alert Plus |
| --- | --- |
| YAML only | YAML **and/or** the UI, side by side |
| No unique ID, no registry entry | Registry-backed, configurable from the frontend |
| One entity with `idle` / `on` / `off` | A `problem` binary sensor plus a separate acknowledgement switch |
| Acknowledgement lost on restart | Acknowledgement restored across restarts |
| A problem present at startup stays silent until the next state change | Evaluated at startup |
| Legacy `notify.*` services only | Legacy services **and** `notify` entities |

### Coming from core `alert`

Rename the key: `alert:` becomes `alert_plus:`. Nothing else in the block
changes — the schema is identical.

Entity IDs change domain but keep their object ID, so
`alert.ico_disconnected_alert` becomes `binary_sensor.ico_disconnected_alert`,
plus a `switch.ico_disconnected_alert_acknowledged`. Automations referring to
your alerts need updating.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

To run hassfest locally, hand it a clean tree. Pointed at the working copy it
walks into `.venv` and validates every Home Assistant core integration it finds
in `site-packages`, drowning the report in thousands of irrelevant errors:

```bash
tree=$(mktemp -d) && git archive HEAD | tar -x -C "$tree"
docker run --rm -v "$tree://github/workspace" ghcr.io/home-assistant/hassfest
```

CI runs hassfest, HACS validation, ruff and the test suite.

## Status

Early but tested. The long-term goal is to propose this to Home Assistant core,
which is why the code sticks to core conventions and lints with core's ruleset.
