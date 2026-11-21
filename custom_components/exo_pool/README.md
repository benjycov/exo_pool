# Exo Pool – Home Assistant Integration

A custom integration to connect your Zodiac iAqualink **Exo** pool system to Home Assistant, providing full control and monitoring of your pool’s features.

## 🆕 What’s New

- ** 27 Apr 2026** – 🚀 Real-time MQTT Integration (Major Upgrade)
1) Real-time updates via AWS IoT MQTT
  1.1) The integration now connects to the same AWS IoT device shadow used by the official iAqualink app.
  1.2) State updates are sub-second instead of polling-based.
2) Zero 429 rate limit issues
  2.1) Reads and writes no longer rely on REST polling under normal operation.
  2.2) Eliminates “Too Many Requests” errors entirely in most setups.
3) Instant writes
  3.1) Changes (pH, ORP, schedules, switches) are sent via MQTT and applied immediately.
4) Automatic fallback to REST
  4.1) If MQTT is unavailable, the integration safely falls back to REST polling.
  4.2) A low-frequency (1 hour) poll ensures resilience.
5) Automatic credential handling
  5.1) AWS credentials are extracted from the Zodiac API and refreshed automatically.
  5.2) Seamless reconnects with no user intervention.
6) No configuration changes required
  6.1) Existing setups continue to work unchanged.
  6.2) No MQTT broker or additional setup needed.

- **7 Feb 2026**
1) Small retry fix to get around 401 'token expired' errors on schedule write attempts (and associated logging updates).

- **6 Feb 2026**

1) Much better protection against cloud rate-limits.
  1.1) The integration now carefully spaces out API calls and avoids overlapping reads and writes.
  1.2) This greatly reduces “Too Many Requests (429)” errors.
2) Smarter handling of changes
  2.1) When you adjust pH, ORP, or schedules, changes are queued and applied safely.
  2.2) Multiple quick changes are merged together instead of hammering the cloud API.
3) No more read/write collisions
  3.1) The integration will not poll the cloud while a setting change is in progress.
  3.2) A short “settling period” after changes prevents unnecessary follow-up requests.
4) Improved schedule reliability
  4.1) Schedule updates are applied more reliably, even when making multiple edits.
  4.2) Optional delayed confirmation refresh avoids unnecessary cloud traffic.
5) New manual refresh feature - you can force a data refresh (though all safety rails still apply)
6) Optional entities now appear reliably
  6.1) pH and ORP setpoint controls will appear automatically once the device reports support.
  6.2) Temporary startup issues (for example during rate-limits) no longer cause them to disappear permanently.
7) More robust startup behavior
  7.1) If the cloud is temporarily unavailable during startup, the integration now recovers cleanly once connectivity returns.
8) Added a 'AWS Status' to the diagnostics. This sensor indicates whether your Exo unit itself is connected to AWS.

- **11 Jan 2026**

1) Changes to refresh rates, now by default we only refresh data from the API every 5 minutes (this will gracefully reduce if 429s are detected), but temporarily boost the rate to every 10s when a user change (for example PH set point) is made.
2) SWC sensors were incorrect before. Now SWC normal and low levels are settable with the correct switch ('low' from shadow data) reflecting if low mode is enabled. In the future we will hide these levels for systems with an ORP sensor (like me), as the swc levels are all 0. For now though I have left it in for debugging purposes.
3) Added a service `exo_pool.reload` to reload the integration if you ever need it (ideally not with the new refresh timings).

- **20 Oct 2025** - Modifications for SSP (Single Speed Pump) - single speed pumps should now be correctly recognised.
- **23 Sep 2025** - Added experimental climate entity for systems with the heat pump enabled.
- **15 Sep 2025** – Added option to adjust API refresh rate to avoid *“Too Many Requests”* errors.
- **3 Sep 2025** – Added binary_sensors for each schedule plus actions to change schedules.

---

## Installation (via HACS)

1. In Home Assistant, go to **HACS → Integrations**.
2. Search for **Exo Pool** and click **Install**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration**, search for **Exo Pool**, and follow the prompts.

---

## Features

- **Automatic Authentication** – Secure login to the iAqualink API using your email and password.
- **System Selection** – Pick your Exo system from multiple pools/devices (filtered to `device_type: "exo"`).
- **Real-time MQTT Updates** – Instant state sync via AWS IoT (no polling required)
- **Sensors** – Temperature, pH, ORP, ORP Boost Time Remaining, Pump RPM, Error Code, Wi-Fi RSSI.
- **Binary Sensors** – Filter Pump running, Chlorinator running, Error State, Authentication Status, Connected, and one per schedule.
- **Switches** – ORP Boost, Power State, Production, Aux 1, Aux 2 (unavailable in heater mode), Heat Pump Priority, SWC Low.
- **Numbers** – SWC Output, SWC Low Output, Refresh Interval, plus pH/ORP Set Points when supported.
- **Climate** – Heat Pump control when the controller reports a `heating` section.
- **Services** – Control and modify schedules (see below).
- **Diagnostics & Dynamic Device Info** – View hardware configuration and live status; serial number and software version update periodically.
- **Rest Fallback** - Automatic resilience if MQTT is unavailable.

---

## 🧠 Architecture

The integration uses a **hybrid cloud model** combining real-time MQTT updates with REST as a fallback.

### Primary Path (MQTT – Real-time)

1. Home Assistant authenticates with the Zodiac API (email/password).
2. The API response includes temporary **AWS IoT credentials**.
3. The integration connects to Zodiac’s AWS IoT endpoint using MQTT over WebSockets.
4. It subscribes to the device’s **shadow topics** (same mechanism used by the official iAqualink app).
5. When the pool system updates state, AWS pushes changes instantly to Home Assistant.
6. Updates are fed directly into the HA coordinator → entities update in real time.

- ✔ Sub-second updates  
- ✔ No polling  
- ✔ No rate limits  

---

### Write Path (MQTT → REST fallback)

- Commands (pH, ORP, schedules, switches) are sent via MQTT to the device shadow:

desired state → AWS IoT → device

- If MQTT is unavailable:
  - The integration automatically falls back to REST API writes.

---

### Fallback Path (REST)

- A low-frequency REST poll (~1 hour) runs as a safety net.
- If MQTT disconnects:
  - REST polling temporarily resumes to maintain visibility.

- ✔ Ensures resilience  
- ✔ Prevents total loss of state  

---

### Credential Lifecycle

- AWS credentials are **temporary (~1 hour lifetime)**.
- The integration:
  - refreshes them before expiry
  - reconnects MQTT automatically
  - recovers cleanly from failures

---
## Schedule Services

Each Exo schedule is exposed as a binary sensor:

- **State**: `on` when active.
- **Attributes**: `schedule`, `enabled`, `start_time`, `end_time`, `type` (`vsp` | `swc` | `aux` | other), and `rpm` (VSP only).
- **Icons**: VSP → pump/pump-off, SWC → water-plus/water-off, AUX → toggle, calendar fallback.

### `exo_pool.set_schedule`
Create or update a schedule’s time range and optional VSP RPM.

```yaml
service: exo_pool.set_schedule
data:
  entity_id: binary_sensor.schedule_filter_pump_2
  start: "11:00"
  end: "23:00"
  rpm: 2000
```

You can also target the device and specify `schedule: sch6` instead of the entity:

```yaml
service: exo_pool.set_schedule
data:
  device_id: 1a2b3c4d5e6f7g8h9i0j
  schedule: sch6
  start: "11:00"
  end: "23:00"
```

### `exo_pool.disable_schedule`
Disable a schedule by setting start and end to `00:00`.

```yaml
service: exo_pool.disable_schedule
data:
  entity_id: binary_sensor.schedule_salt_water_chlorinator_2
```

### `exo_pool.reload`
Reload the integration. If you only have one Exo Pool entry, no data is required.

```yaml
service: exo_pool.reload
```

To target a specific entry or device:

```yaml
service: exo_pool.reload
data:
  entry_id: 8955375327824e14ba89e4b29cc3ec9a
```

---

## Device Actions (Automations)

When creating an automation:
**Device → your Exo Pool device → Actions**: *Set schedule* or *Disable schedule*.
These map directly to the services above.

---

## History

The core iAqualink integration never supported Exo devices (European Zodiac-branded chlorinators). See the long-running discussion: [flz/iaqualink-py#16](https://github.com/flz/iaqualink-py/discussions/16).
After early Node-RED flows and REST template hacks, this dedicated integration was built to provide full native support.

---

## Limitations

- Restricted to **Exo** devices only; use the core iAqualink integration for other hardware.
- Schedule keys, names and endpoints are determined by the device; disabling a schedule is modelled as `00:00–00:00`.
- RPM is only relevant to VSP schedules.
- The heat pump climate entity appears when the controller reports a `heating` section. Its on/off control uses `heating.enabled`; priority mode is available as a separate switch.

---

## Compatibility

Confirmed working with:
- **Exo IQ LS** (dual-link ORP & pH, Zodiac VSP pump).

Have success with other models? Please share!

---

## Support

- **Bugs / Feature Requests**: [GitHub Issues](https://github.com/benjycov/exo_pool/issues)
- **Q&A / Discussion**: [GitHub Discussions](https://github.com/benjycov/exo_pool/discussions)

## Credits
Special thanks on this release to Andrew Brainwood (https://github.com/abrainwood) for the excellent work on the migration to MQTT.
