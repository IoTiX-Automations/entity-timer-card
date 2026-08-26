# Entity Override

A Home Assistant integration + companion Lovelace card that turns any
entity on or off **until** a chosen date & time, then automatically
reverts it.

Tap the card → a dialog opens with two options, **"Turn ON until"** and
**"Turn OFF until"**, each with a date/time picker. Confirming flips the
entity immediately and schedules reverting it back at the chosen moment.
The card shows a live countdown to the scheduled flip.

Pending overrides are persisted to storage and rescheduled on startup, so
a Home Assistant restart mid-countdown does not lose the revert.

## Installation

### HACS (recommended)

1. HACS → Integrations → ⋮ → Custom repositories → add this repository
   URL with category **Integration** (once accepted into the default
   HACS store, this step won't be necessary — just search "Entity
   Override").
2. Install **Entity Override**, then restart Home Assistant.
3. Settings → Devices & Services → Add Integration → **Entity Override**
   (no configuration fields — just confirm). This also auto-registers
   the companion card as a frontend resource.

### Manual

Copy `custom_components/entity_override` into your Home Assistant
`config/custom_components/` directory, restart, then add the integration
as above.

## Using the card

```yaml
type: custom:entity-override-card
entity: switch.some_entity
name: Optional display name
icon: mdi:optional-icon
```

## Services

The integration also exposes two services directly, usable from
automations/scripts without the card:

- `entity_override.set` — fields `entity_id`, `state` (`on`/`off`),
  `until` (datetime). Applies the state now and schedules the revert.
- `entity_override.cancel` — field `entity_id`. Cancels a pending
  override without changing the entity's current state.

## How it works

- A single config entry manages all overrides; no per-entity setup.
- Pending overrides live in `sensor.entity_override_pending` as an
  attribute dict (`overrides: { entity_id: { revert_state, until } }`),
  which the card reads reactively — no polling.
- Reverts are scheduled with Home Assistant's point-in-time event
  tracking and re-armed on startup from persisted storage, so timing is
  exact and restart-safe.

## License

MIT — see [LICENSE](LICENSE).
