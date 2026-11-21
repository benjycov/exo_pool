# Exo Pool – Home Assistant Integration

A custom integration to connect your Zodiac iAqualink **Exo** pool system to Home Assistant, providing full control and monitoring of your pool’s features.

## 🆕 What’s New

- **15 Apr 2026**
1) **Real-time updates via AWS IoT MQTT.** The integration now connects to the same AWS IoT shadow endpoint used by the official iAqualink app, giving sub-second state sync instead of REST polling. No additional setup required - it uses credentials already provided by the Zodiac login API.
2) Writes (set points, switches, schedules) now go via MQTT when connected, eliminating 429 rate limit errors on writes.
3) REST polling is kept as a 1-hour fallback in case MQTT disconnects, but under normal operation all data flows through MQTT push.
4) AWS credentials are automatically refreshed before expiry (~hourly).
5) Added `awsiotsdk` as a dependency (installed automatically by HACS).

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
- **Sensors** – Temperature, pH, ORP, ORP Boost Time Remaining, Pump RPM, Error Code, Wi-Fi RSSI.
- **Binary Sensors** – Filter Pump running, Chlorinator running, Error State, Authentication Status, Connected, and one per schedule.
- **Switches** – ORP Boost, Power State, Production, Aux 1, Aux 2 (unavailable in heater mode), Heat Pump Priority, SWC Low.
- **Numbers** – SWC Output, SWC Low Output, Refresh Interval, plus pH/ORP Set Points when supported.
- **Climate (experimental)** – Heat Pump control when the controller reports a `heating` section.
- **Services** – Control and modify schedules (see below).
- **Diagnostics & Dynamic Device Info** – View hardware configuration and live status; serial number and software version update periodically.
- **Real-time MQTT Updates** – Connects to AWS IoT for instant state sync (same protocol as the official app). No MQTT broker or addon required.
- **Configurable Refresh Rate** – The `Refresh Interval` number (300-3600 s) controls the REST fallback poll interval. Under normal MQTT operation this rarely fires.

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
- Commands (set points, Aux switches, etc.) are near-instant via MQTT. If MQTT is unavailable, writes fall back to REST which may be subject to rate limits.
- Schedule keys, names and endpoints are determined by the device; disabling a schedule is modelled as `00:00–00:00`.
- RPM is only relevant to VSP schedules.
- The heat pump climate entity appears when the controller reports a `heating` section. Its on/off control uses `heating.enabled`; priority mode is available as a separate switch.

---

## Compatibility

Confirmed working with:
- **Exo IQ LS** (dual-link ORP & pH, Zodiac VSP pump).

Have success with other models? Please share!

---

## Development

### Prerequisites

- Docker
- Python 3.9+
- A Zodiac iAqualink account with an eXO device

### Quick start

```bash
git clone https://github.com/benjycov/exo_pool.git
cd exo_pool

# Create .env with your Zodiac credentials
echo "EXO_EMAIL=your@email.com" > .env
echo "EXO_PASSWORD=yourpassword" >> .env

# Start a dev HA instance (auto-onboards, configures integration)
make dev

# Open http://localhost:8125 (login: dev / devdevdev)
```

### Useful commands

```bash
make test       # run unit + integration tests
make logs       # tail the HA container logs
make restart    # restart HA after code changes (volume-mounted, no rebuild)
make stop       # stop the container
```

### Running tests

```bash
pip install pytest pytest-asyncio awsiotsdk
python3 -m pytest tests/ -v
```

Tests are isolated from Home Assistant - no HA installation required to run them.

---

## Support

- **Bugs / Feature Requests**: [GitHub Issues](https://github.com/benjycov/exo_pool/issues)
- **Q&A / Discussion**: [GitHub Discussions](https://github.com/benjycov/exo_pool/discussions)
