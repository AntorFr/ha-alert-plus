# Alert Plus

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)

An upgrade of Home Assistant's `alert` integration, meant to replace it.

Everything core did is kept: the same `alert` domain, the same entity IDs, the
same `idle` / `on` / `off` states, the same `alert.turn_on` / `turn_off` /
`toggle` services, the same YAML schema down to the key names.
**`alert.fire_alert` stays `alert.fire_alert`**, and automations calling it keep
working untouched.

What it adds is what core never had.

## Why

Core's [`alert`](https://www.home-assistant.io/integrations/alert/) gives its
entities no unique ID. Without one, an entity never reaches the entity registry,
and everything the frontend offers is unavailable: you cannot rename it, give it
an icon, assign it to an area, hide it, or expose it to a voice assistant.

Development of core `alert` is
[frozen and headed for deprecation](https://github.com/home-assistant/home-assistant.io/issues/42151),
so that is not going to be fixed there.

## What it adds

- **A unique ID on every alert** → registry entry → name, icon, area and
  visibility editable from the frontend.
- **Creation from the UI**, as a helper, alongside YAML. Both at once.
- **`alert_plus.reload`**, so a YAML change no longer needs a restart.
- **Acknowledgement survives a restart**, instead of being forgotten.
- **A condition already met at startup raises the alert**, instead of staying
  silent until the next state change.
- **`notify` entities** supported alongside legacy `notify.*` services.

## Installation

### HACS

Add `https://github.com/AntorFr/ha-alert-plus` as a custom repository of type
*Integration*, download **Alert Plus**, then restart Home Assistant.

### Manual

Copy `custom_components/alert_plus` into your `custom_components` directory and
restart Home Assistant.

## Migrating from core `alert`

Rename the key: `alert:` becomes `alert_plus:`. That is the whole migration.

```diff
-alert:
+alert_plus:
   fire_alert:
     name: "Fire alert"
     entity_id: binary_sensor.smoke
     repeat: 30
     notifiers:
       - notify
```

Entity IDs, states, services and attributes are unchanged, so nothing that
referenced `alert.fire_alert` needs touching.

> ⚠️ **Do not leave an `alert:` block behind.** It would load core's integration,
> and the two would fight over the `alert` domain and its services. Rename every
> block, or none.

## Declaring alerts

Both ways work at the same time. Use YAML for what you want versioned in git,
the UI for the rest.

### YAML

```yaml
alert_plus:
  fire_alert:
    name: "Fire alert"
    message: >
      "Smoke detected in {{ area_name('binary_sensor.smoke') }}"
    done_message: >
      "All clear"
    entity_id: binary_sensor.smoke
    state: "on"            # optional, 'on' is the default
    repeat: 30
    can_acknowledge: true  # optional, default is true
    skip_first: false      # optional, default is false
    notifiers:
      - notify
```

The YAML key is both the entity ID and the unique ID, exactly as core used it.
Apply changes with the **`alert_plus.reload`** action — no restart. Reloading
only touches YAML alerts; those created from the UI keep running. If the YAML
fails to validate, the reload is refused and the alerts already running stay up.

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
| `can_acknowledge` | Whether `alert.turn_off` may silence it |
| `notifiers` | Legacy `notify.*` services, without the `notify.` prefix |
| `notify_entities` | `notify` entities to send the message to (addition; UI only) |
| `message` / `title` / `done_message` | Templates; the message defaults to the alert name |
| `data` | Extra payload for the legacy notify services (notify entities ignore it) |

## States and services

| State | Meaning |
| --- | --- |
| `idle` | The watched entity is not in the alerting state |
| `on` | Firing, not acknowledged |
| `off` | Firing, acknowledged |

`alert.turn_off` acknowledges, `alert.turn_on` unacknowledges, `alert.toggle`
flips — as in core.

Extra attributes, on top of what core reported: `watched_entity_id`,
`can_acknowledge`, `notification_count`, `next_notification`.

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

Early but tested. The long-term goal is to propose this to Home Assistant core
as the successor to `alert`, which is why it keeps core's domain and behaviour
to the letter and lints with core's ruleset.
