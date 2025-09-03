# Exo Pool - Home Assistant Integration

A custom integration to connect your Zodiac iAqualink Exo pool system to Home Assistant, providing control and monitoring of your pool's features.

## Installation via HACS

1. Go to HACS → Integrations → Custom Repositories.
2. Add `https://github.com/benjycov/exo_pool` as type `Integration`.
3. Install Exo Pool from the list.
4. Restart Home Assistant.
5. Configure via the Integrations UI under Settings → Devices & Services → Add Integration.

## Features

- Automatic Authentication: Secure login to the iAqualink API with email and password.
- System Selection: Choose your Exo system from multiple pools/devices (filtered to device_type: "exo").
- Sensors: Temperature, pH, ORP, Error Code (and text), WiFi RSSI, Hardware summary.
- Binary Sensors: Filter Pump running, Chlorinator running, Error State, Authentication Status, Connected, one per schedule (see below).
- Switches: ORP Boost, Power, Production, Aux 1, Aux 2, SWC Low.
- Numbers: pH Set Point, ORP Set Point (when supported).
- Dynamic Device Info: Serial Number and Software Version, updated periodically.
- Diagnostics: Export redacted diagnostics from the device page.

## Schedule Sensors

Each schedule under the device is exposed as a binary sensor.

- State: on when `active == 1`, otherwise off.
- Attributes:
  - `schedule`: schedule key (e.g., `sch6`)
  - `enabled`: true/false
  - `start_time`: HH:MM
  - `end_time`: HH:MM
  - `type`: `vsp` | `swc` | `aux` | other
  - `rpm`: present for VSP schedules
- Icons: VSP → pump/pump-off, SWC → water-plus/water-off, AUX → toggle icons, calendar fallback.

## Services

Two services are provided under the `exo_pool` domain.

### exo_pool.set_schedule

- Purpose: Create/update a schedule’s time range and optional VSP RPM.
- Target: select either the schedule entity (recommended) or the Exo device.
- Fields:
  - `schedule` (optional if targeting a schedule entity): schedule key like `sch6`.
  - `start` (optional): HH:MM (HH:MM:SS accepted; truncated).
  - `end` (optional): HH:MM (HH:MM:SS accepted; truncated).
  - `rpm` (optional): integer; only used for VSP schedules.

Examples

- Target schedule entity directly (Developer Tools → Services):

```
service: exo_pool.set_schedule
target:
  entity_id: binary_sensor.schedule_filter_pump_2
data:
  start: "11:00"
  end: "23:00"
  rpm: 2000
```

- Target device + schedule key:

```
service: exo_pool.set_schedule
target:
  device_id: 1234567890abcdef1234567890abcdef
data:
  schedule: sch6
  start: "08:00"
  end: "11:00"
```

### exo_pool.disable_schedule

- Purpose: Disable a schedule by setting start and end to 00:00.
- Target: schedule entity or Exo device.
- Fields: `schedule` (optional if targeting a schedule entity).

Examples

```
service: exo_pool.disable_schedule
target:
  entity_id: binary_sensor.schedule_salt_water_chlorinator_2
```

or

```
service: exo_pool.disable_schedule
target:
  device_id: 1234567890abcdef1234567890abcdef
data:
  schedule: sch10
```

## Device Actions (Automation UI)

Under Automations, choose Device → your Exo Pool device → select:

- Set schedule: fields for `schedule`, optional `start`, `end`, `rpm`.
- Disable schedule: field for `schedule`.

These actions call the services above.

## History

Classicly the core iAqualink integration doesn't support Exo devices (European Zodiac-branded chlorinators). There has been a long thread on the topic here: https://github.com/flz/iaqualink-py/discussions/16. @martinfrench92 made changes to the core integration; however, they never made it to the main branch. After interim Node-RED and REST template approaches, this standalone integration was created.

## Limitations

- Deliberately restricted to Exo devices only; for other devices use the core iAqualink integration.
- Changing values (set points, Aux switch on/off, etc.) can be laggy; switches are optimistic with a ~10s refresh.
- Schedule keys, names, and endpoints are determined by the device; enabling/disabling is modeled by times: 00:00–00:00 is treated as disabled.
- RPM applies only to VSP schedules.

