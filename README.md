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




