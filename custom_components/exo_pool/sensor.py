from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .api import get_coordinator, ERROR_CODES, DOMAIN
from homeassistant.const import EntityCategory
import logging

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor platform for Exo Pool."""
    # Initialize or retrieve shared coordinator
    coordinator = await get_coordinator(hass, entry)

    # Add sensors
    entities = [
        TempSensor(entry, coordinator),
        ORPSensor(entry, coordinator),
        ORPBoostTimeSensor(entry, coordinator),
        PHSensor(entry, coordinator),
        PumpRPMSensor(entry, coordinator),
        ErrorCodeSensor(entry, coordinator),
        WifiRssiSensor(entry, coordinator),
        HardwareSensor(entry, coordinator),
    ]
    async_add_entities(entities)


# Sensor Classes
class TempSensor(CoordinatorEntity, SensorEntity):
    """Representation of a temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:pool-thermometer"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Temperature"
        self._attr_unique_id = f"{entry.entry_id}_temp"
        self._attr_native_unit_of_measurement = "°C"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def native_value(self):
        return (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("sns_3", {})
            .get("value")
        )


class ORPSensor(CoordinatorEntity, SensorEntity):
    """Representation of an ORP sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-check"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "ORP"
        self._attr_unique_id = f"{entry.entry_id}_orp"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def native_value(self):
        return (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("sns_2", {})
            .get("value")
        )


class ORPBoostTimeSensor(CoordinatorEntity, SensorEntity):
    """Representation of an ORP boost time sensor."""

    _attr_icon = "mdi:timer-sand"
    _attr_native_unit_of_measurement = "min"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "ORP Boost Time Remaining"
        self._attr_unique_id = f"{entry.entry_id}_orp_boost_time"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def native_value(self):
        """Convert HH:MM boost_time to total minutes."""
        time_str = (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("boost_time")
        )
        if time_str and isinstance(time_str, str) and ":" in time_str:
            try:
                hours, minutes = map(int, time_str.split(":"))
                return hours * 60 + minutes
            except (ValueError, TypeError):
                _LOGGER.error("Invalid boost_time format: %s", time_str)
                return None
        return None


class PHSensor(CoordinatorEntity, SensorEntity):
    """Representation of a pH sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:test-tube"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "pH"
        self._attr_unique_id = f"{entry.entry_id}_ph"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def native_value(self):
        value = (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("sns_1", {})
            .get("value")
        )
        return value / 10 if value is not None else None


class PumpRPMSensor(CoordinatorEntity, SensorEntity):
    """Representation of a pump RPM sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "RPM"
    _attr_icon = "mdi:fan"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Pump RPM"
        self._attr_unique_id = f"{entry.entry_id}_pump_rpm"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def native_value(self):
        # Implement pool_get_schedule_info logic
        schedules = self.coordinator.data.get("schedules", {})
        for key, value in schedules.items():
            if (
                isinstance(value, dict)
                and value.get("endpoint")
                and "vsp" in value.get("endpoint")
                and value.get("enabled") == 1
                and value.get("active") == 1
            ):
                return value.get("rpm")
        return 0  # Default to 0 if no active VSP schedule found


class ErrorCodeSensor(CoordinatorEntity, SensorEntity):
    """Representation of an error code sensor."""

    _attr_icon = "mdi:alert-circle"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Error Code"
        self._attr_unique_id = f"{entry.entry_id}_error_code"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def native_value(self):
        return (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("error_code")
        )

    @property
    def extra_state_attributes(self):
        """Provide the error message as an attribute."""
        code = (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("error_code")
        )
        return {
            "error_message": ERROR_CODES.get(
                int(code) if code is not None else 0, "Unknown Error"
            )
        }


class WifiRssiSensor(CoordinatorEntity, SensorEntity):
    """Representation of a WiFi RSSI sensor."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "dBm"
    _attr_icon = "mdi:wifi"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "WiFi RSSI"
        self._attr_unique_id = f"{entry.entry_id}_wifi_rssi"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def native_value(self):
        """Return the WiFi RSSI value."""
        return self.coordinator.data.get("debug", {}).get("RSSI")


class HardwareSensor(CoordinatorEntity, SensorEntity):
    """Representation of hardware configuration information."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information-outline"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Hardware"
        self._attr_unique_id = f"{entry.entry_id}_hardware"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def native_value(self):
        """Return a summary of enabled hardware capabilities."""
        capabilities = []
        if (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("ph_only", 0)
            == 1
        ):
            capabilities.append("PH")
        if (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("dual_link", 0)
            == 1
        ):
            capabilities.append("ORP")
        if (
            self.coordinator.data.get("equipment", {}).get("swc_0", {}).get("vsp", 0)
            == 1
        ):
            capabilities.append("VSP")
        return ", ".join(capabilities) if capabilities else "None"

    @property
    def extra_state_attributes(self):
        """Provide detailed hardware capability flags."""
        return {
            "variable_speed_pump": self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("vsp", 0)
            == 1,
            "ph_control": self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("ph_only", 0)
            == 1,
            "orp_control": self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("dual_link", 0)
            == 1,
        }
