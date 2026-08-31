# Entity Timer

A Home Assistant integration + companion Lovelace card that turns any
entity on or off **until** a chosen date & time, then automatically
reverts it.

Tap the card → a dialog opens with two options, **"Turn ON until"** and
**"Turn OFF until"**, each with a date/time picker. Confirming flips the
entity immediately and schedules reverting it back at the chosen moment.
The card shows a live countdown to the scheduled flip. If a timer is
already pending, the dialog also shows a **Cancel** option to stop it
early without changing the entity's current state.

Pending timers are persisted to storage and rescheduled on startup, so
a Home Assistant restart mid-countdown does not lose the revert.

## Installation

### HACS (recommended)

1. HACS → Integrations → ⋮ → Custom repositories → add this repository
   URL with category **Integration** (once accepted into the default
   HACS store, this step won't be necessary — just search "Entity
   Timer").
2. Install **Entity Timer**, then restart Home Assistant.
3. Settings → Devices & Services → Add Integration → **Entity Timer**
   (no configuration fields — just confirm).
4. Add the card's script as a dashboard resource: Settings → Dashboards
   → ⋮ (top right) → Resources → Add Resource →
   URL: `/entity_timer_static/entity-timer-card.js`, Resource type:
   **JavaScript Module**. (Home Assistant's Lovelace only recognizes
   custom card elements registered this way — its newer scoped
   custom-element-registry system does not pick up cards injected via
   the generic `frontend.add_extra_js_url` API, even though that API
   successfully serves and executes the script.)

### Manual

Copy `custom_components/entity_timer` into your Home Assistant
`config/custom_components/` directory, restart, add the integration,
then add the dashboard resource — all as above.

## Using the card

Add it through the dashboard UI (Add Card → search "Entity Timer Card") to
get a visual editor — entity picker, name, icon, and a "Minimized" toggle —
instead of writing YAML by hand. Or write it directly:

```yaml
type: custom:entity-timer-card
entity: switch.some_entity
name: Optional display name
icon: mdi:optional-icon
```

### As a Picture Elements icon

Set `icon_only: true` to render a bare, colored icon (no card box) instead
of the full row — for use as an element inside a `picture-elements` card.
Tap still opens the same popup.

```yaml
type: picture-elements
image: /local/floorplan.png
elements:
  - type: custom:entity-timer-card
    entity: switch.some_entity
    icon_only: true
    style:
      top: 40%
      left: 60%
      "--entity-timer-icon-size": "32px"
```

The icon is colored via `--entity-timer-icon-color-off` /
`--entity-timer-icon-color-on` (falling back to the usual HA icon-color
variables), sized via `--entity-timer-icon-size` (default `24px`), and
shows a small dot while a timer is pending — all settable per-element
through the `style:` block above.

## Services

The integration also exposes two services directly, usable from
automations/scripts without the card:

- `entity_timer.set` — fields `entity_id`, `state` (`on`/`off`),
  `until` (datetime). Applies the state now and schedules the revert.
- `entity_timer.cancel` — field `entity_id`. Cancels a pending
  timer without changing the entity's current state.

## How it works

- A single config entry manages all timers; no per-entity setup.
- Pending timers live in `sensor.entity_timer_pending` as an
  attribute dict (`timers: { entity_id: { revert_state, until } }`),
  which the card reads reactively — no polling.
- Reverts are scheduled with Home Assistant's point-in-time event
  tracking and re-armed on startup from persisted storage, so timing is
  exact and restart-safe.

## License

MIT — see [LICENSE](LICENSE).
