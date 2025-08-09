# Exo Pool - Home Assistant Integration

A custom integration to connect your Zodiac iAqualink Exo pool system to Home Assistant, providing control and monitoring of your pool's features.

## Installation via HACS

1. Go to **HACS → Integrations → Custom Repositories**.
2. Add `https://github.com/benjycov/exo_pool` as type `Integration`.
3. Install **Exo Pool** from the list.
4. Restart Home Assistant.
5. Configure via the **Integrations UI** under **Settings > Devices & Services > Add Integration**.

## Features

- **Automatic Authentication**: Secure login to the iAqualink API with email and password.
- **System Selection**: Choose your Exo system from multiple pools/devices (filtered to `device_type: "exo"`).
- **Sensors**: Monitor pool parameters including:
  - Temperature
  - pH
  - ORP
  - ORP Boost Time Remaining
  - Pump RPM
  - Error Code
  - WiFi RSSI
- **Switches**: Control pool components including:
  - ORP Boost
  - Power State
  - Production
  - Aux 1
  - Aux 2
  - SWC Low
- **Number Entities**: Adjust set points for:
  - pH Set Point
  - ORP Set Point
- **Diagnostic Information**: View hardware configuration (e.g., PH, ORP, VSP support) and status (e.g., Error State, Authentication Status, Connected) in the device info page.
- **Dynamic Device Info**: Displays Serial Number and Software Version, updated periodically.

## History

Classicly the core iAqualink interogration doesn't support Exo devices (european Zodiac branded chlorinators). There has been a long thread on the topic here 'https://github.com/flz/iaqualink-py/discussions/16'.

@martinfrench92 did make changes to the core integration, however these changes never made it to the main branch, and it was cumbersome for people to patch the changes in manually.
I then created some really dirty Node Red flows which queried the API and did the basics (pH, Chlore, etc.). A couple of years later I migrated these to rest_commands with a bunch of related template sensors/switches, but what we really needed was a stand alone integration... so I knuckled down and with a little help from my AI minions smashed out this integration.


## Limitations

- Deliberately restricted to exo devices only, for anything else use the core iAqualink integration (which doesn't support Exo)
- Changing things on the Exo devices (ORP set points, Aux switch on/off, etc.) is a bit laggy, currently the switches are optimistic with a 10s refresh delay. Please let me know if you need a longer delay in your deployment

## Compatibility

Should work with any Zodiac Exo pool system, confirmed to work with:

- Exo IQ LS (with Dual-link ORP & PH, and Zodiac VSP pump)
- ??? Let me know what you get it working with!


