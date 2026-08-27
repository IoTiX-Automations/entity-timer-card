/**
 * entity-timer-card
 *
 * Part of the "Entity Timer" Home Assistant integration.
 *
 * Displays one entity. Tapping it opens a dialog with two options —
 * "Turn ON until" and "Turn OFF until" — each with a date/time picker.
 * Confirming calls entity_timer.set, which flips the entity now and
 * schedules reverting it at the chosen date/time. The integration persists
 * pending timers and reschedules them on restart, so a reboot mid-
 * countdown does not lose the revert.
 *
 * While a timer is pending, the card shows a live countdown to the
 * scheduled flip, read reactively from sensor.entity_timer_pending
 * (no polling — it just watches hass state like any other card).
 *
 * Config:
 *   type: custom:entity-timer-card
 *   entity: switch.something   (required)
 *   name: Friendly name        (optional, defaults to entity's name)
 *   icon: mdi:something        (optional, defaults to entity's icon)
 */

const PENDING_SENSOR_ENTITY_ID = "sensor.entity_timer_pending";
const OPTIMISTIC_GRACE_MS = 8000;

// Module-level (not per-instance) so a just-set optimistic value survives
// Lovelace recreating the card element — which happens on things like a
// websocket reconnect (common over remote/cloud access) — since the ES
// module itself stays loaded and isn't re-evaluated when that happens.
// Keyed by entity_id: { timer: {due, description} | null, setAt: number }
const optimisticByEntity = new Map();

class EntityTimerCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) {
      throw new Error("Please define an entity");
    }
    this._config = config;
    this._timer = null; // { due: ISOstring, description: 'on'|'off' }
    this._buildCard();
  }

  set hass(hass) {
    this._hass = hass;
    this._updateCard();
    this._updateTimerFromHass();
  }

  connectedCallback() {
    if (this._tickTimer) return;
    this._tickTimer = setInterval(() => this._tick(), 1000);
  }

  disconnectedCallback() {
    clearInterval(this._tickTimer);
    this._tickTimer = null;
  }

  getCardSize() {
    return 1;
  }

  static getStubConfig() {
    return { entity: "" };
  }

  _buildCard() {
    if (this._built) return;
    this._built = true;

    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        ha-card {
          display: flex;
          align-items: center;
          padding: 12px 16px;
          cursor: pointer;
          -webkit-tap-highlight-color: transparent;
        }
        ha-card:focus-visible {
          outline: 2px solid var(--primary-color);
          outline-offset: -2px;
        }
        ha-icon {
          color: var(--state-icon-color, var(--paper-item-icon-color, #44739e));
          margin-right: 16px;
          flex-shrink: 0;
        }
        .info {
          min-width: 0;
        }
        .name {
          font-weight: 500;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .state {
          font-size: 0.85em;
          color: var(--secondary-text-color);
        }
        .timer {
          font-size: 0.85em;
          color: var(--primary-color);
          display: none;
        }
        .timer.visible {
          display: block;
        }
        .timer-btn {
          border: none;
          border-radius: 8px;
          padding: 10px 16px;
          font-size: 0.95em;
          font-weight: 500;
          font-family: inherit;
          cursor: pointer;
          color: #fff;
          white-space: nowrap;
          transition: filter 0.15s ease, box-shadow 0.15s ease;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
        }
        .timer-btn:hover {
          filter: brightness(1.1);
        }
        .timer-btn:active {
          filter: brightness(0.9);
        }
        .timer-btn.on {
          background: var(--success-color, #4caf50);
        }
        .timer-btn.off {
          background: var(--error-color, #db4437);
        }
        .timer-btn.cancel {
          background: var(--disabled-text-color, #757575);
        }
        .cancel-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding-bottom: 4px;
          border-bottom: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        }
        .cancel-row .label {
          font-size: 0.95em;
          color: var(--primary-color);
        }
      </style>
      <ha-card tabindex="0" role="button">
        <ha-icon id="icon"></ha-icon>
        <div class="info">
          <div class="name" id="name"></div>
          <div class="state" id="state"></div>
          <div class="timer" id="timer"></div>
        </div>
      </ha-card>
    `;

    const card = this.shadowRoot.querySelector("ha-card");
    card.addEventListener("click", () => this._openDialog());
    card.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        this._openDialog();
      }
    });
  }

  _updateCard() {
    if (!this._hass || !this._config) return;
    const stateObj = this._hass.states[this._config.entity];

    const iconEl = this.shadowRoot.getElementById("icon");
    const nameEl = this.shadowRoot.getElementById("name");
    const stateEl = this.shadowRoot.getElementById("state");

    if (!stateObj) {
      nameEl.textContent = this._config.entity;
      stateEl.textContent = "unavailable";
      iconEl.icon = this._config.icon || "mdi:help-circle-outline";
      return;
    }

    nameEl.textContent = this._config.name || stateObj.attributes.friendly_name || this._config.entity;
    stateEl.textContent = this._hass.formatEntityState
      ? this._hass.formatEntityState(stateObj)
      : stateObj.state;
    iconEl.icon =
      this._config.icon || stateObj.attributes.icon || "mdi:toggle-switch-outline";
  }

  _updateTimerFromHass() {
    const sensor = this._hass.states[PENDING_SENSOR_ENTITY_ID];
    if (!sensor) return;

    // Grace period after our own optimistic set/cancel: setting a timer
    // flips the target entity's own state first and the pending-timers
    // sensor second (and cancelling only touches the sensor), so this
    // card can receive one or more hass updates carrying a stale
    // snapshot of the sensor before it actually reflects our change.
    // Trust our own optimistic value for a few seconds rather than
    // comparing server timestamps against the browser's clock. Read
    // from the module-level map (see top of file), not an instance
    // field, so this still holds even if Lovelace recreated this card
    // element in the meantime.
    const optimistic = optimisticByEntity.get(this._config.entity);
    if (optimistic) {
      if (Date.now() - optimistic.setAt < OPTIMISTIC_GRACE_MS) {
        this._timer = optimistic.timer;
        this._tick();
        return;
      }
      optimisticByEntity.delete(this._config.entity);
    }

    const timers = (sensor.attributes && sensor.attributes.timers) || {};
    const info = timers[this._config.entity];
    this._timer = info ? { due: info.until, description: info.revert_state } : null;
    this._tick();
  }

  _tick() {
    const el = this.shadowRoot && this.shadowRoot.getElementById("timer");
    if (!el) return;

    if (!this._timer) {
      el.classList.remove("visible");
      el.textContent = "";
      return;
    }

    const remainingMs = new Date(this._timer.due).getTime() - Date.now();
    if (remainingMs <= 0) {
      // The integration reverts to-the-second, so this should be
      // momentary — shown only for the brief window before the next
      // hass state update clears this._timer.
      el.classList.add("visible");
      el.textContent = `Turns ${this._timerVerb()} any moment…`;
      return;
    }

    el.classList.add("visible");
    el.textContent = `Turns ${this._timerVerb()} in ${this._formatDuration(remainingMs)}`;
  }

  _timerVerb() {
    return this._timer && this._timer.description === "on" ? "ON" : "OFF";
  }

  _formatDuration(ms) {
    const totalSeconds = Math.max(0, Math.round(ms / 1000));
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = totalSeconds % 60;
    if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
    if (m > 0) return `${m}m ${String(s).padStart(2, "0")}s`;
    return `${s}s`;
  }

  _defaultDateTimeLocal(hoursFromNow) {
    const d = new Date(Date.now() + hoursFromNow * 3600 * 1000);
    d.setSeconds(0, 0);
    const pad = (n) => String(n).padStart(2, "0");
    return (
      d.getFullYear() +
      "-" +
      pad(d.getMonth() + 1) +
      "-" +
      pad(d.getDate()) +
      "T" +
      pad(d.getHours()) +
      ":" +
      pad(d.getMinutes())
    );
  }

  _openDialog() {
    if (!this._hass) return;

    const stateObj = this._hass.states[this._config.entity];
    const title = this._config.name || (stateObj && stateObj.attributes.friendly_name) || this._config.entity;

    const dialog = document.createElement("ha-dialog");
    dialog.heading = title;
    dialog.open = true;

    const wrap = document.createElement("div");
    wrap.style.display = "flex";
    wrap.style.flexDirection = "column";
    wrap.style.gap = "20px";
    wrap.style.minWidth = "280px";

    if (this._timer) {
      wrap.appendChild(this._buildCancelRow(dialog));
    }

    const onRow = this._buildRow(
      "Turn ON until",
      this._defaultDateTimeLocal(1),
      "on",
      dialog
    );
    const offRow = this._buildRow(
      "Turn OFF until",
      this._defaultDateTimeLocal(1),
      "off",
      dialog
    );

    wrap.appendChild(onRow);
    wrap.appendChild(offRow);
    dialog.appendChild(wrap);

    dialog.addEventListener("closed", () => dialog.remove());

    this.shadowRoot.appendChild(dialog);
    this._dialog = dialog;
  }

  _buildCancelRow(dialog) {
    const row = document.createElement("div");
    row.className = "cancel-row";

    const labelEl = document.createElement("div");
    labelEl.className = "label";
    const remainingMs = new Date(this._timer.due).getTime() - Date.now();
    labelEl.textContent =
      remainingMs > 0
        ? `Currently: turns ${this._timerVerb()} in ${this._formatDuration(remainingMs)}`
        : `Currently: turns ${this._timerVerb()} any moment…`;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "timer-btn cancel";
    button.textContent = "Cancel";
    button.addEventListener("click", () => {
      this._hass.callService("entity_timer", "cancel", {
        entity_id: this._config.entity,
      });

      this._timer = null;
      optimisticByEntity.set(this._config.entity, { timer: null, setAt: Date.now() });
      this._tick();

      dialog.open = false;
    });

    row.appendChild(labelEl);
    row.appendChild(button);
    return row;
  }

  _buildRow(label, defaultValue, state, dialog) {
    const row = document.createElement("div");
    row.style.display = "flex";
    row.style.flexDirection = "column";
    row.style.gap = "8px";

    const labelEl = document.createElement("div");
    labelEl.textContent = label;
    labelEl.style.fontWeight = "500";

    const controls = document.createElement("div");
    controls.style.display = "flex";
    controls.style.gap = "8px";
    controls.style.alignItems = "center";

    const input = document.createElement("input");
    input.type = "datetime-local";
    input.value = defaultValue;
    input.style.flex = "1";
    input.style.font = "inherit";
    input.style.padding = "6px";

    const button = document.createElement("button");
    button.type = "button";
    button.className = `timer-btn ${state}`;
    button.textContent = state === "on" ? "Turn ON" : "Turn OFF";
    button.addEventListener("click", () => {
      if (!input.value) return;
      const untilIso = new Date(input.value).toISOString();
      this._hass.callService("entity_timer", "set", {
        entity_id: this._config.entity,
        state,
        until: untilIso,
      });

      // Optimistic local update — show the countdown immediately instead of
      // waiting for the next state update. Recorded in optimisticByEntity
      // (see _updateTimerFromHass) so a stale hass update can't clobber it.
      this._timer = { due: untilIso, description: state === "on" ? "off" : "on" };
      optimisticByEntity.set(this._config.entity, { timer: this._timer, setAt: Date.now() });
      this._tick();

      dialog.open = false;
    });

    controls.appendChild(input);
    controls.appendChild(button);
    row.appendChild(labelEl);
    row.appendChild(controls);
    return row;
  }
}

customElements.define("entity-timer-card", EntityTimerCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "entity-timer-card",
  name: "Entity Timer Card",
  description: "Tap an entity to schedule turning it on or off until a chosen date & time.",
});
