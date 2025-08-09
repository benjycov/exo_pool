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
        ExoPoolTempSensor(entry, coordinator),
        ExoPoolORPSensor(entry, coordinator),
        ExoPoolORPBoostTimeSensor(entry, coordinator),
        ExoPoolPHSensor(entry, coordinator),
        ExoPoolPumpRPMSensor(entry, coordinator),
        ExoPoolErrorCodeSensor(entry, coordinator),
        ExoPoolFirmwareSensor(entry, coordinator),
    ]
    async_add_entities(entities)


# Sensor Classes
class ExoPoolTempSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Exo Pool temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:pool-thermometer"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Exo Pool Temperature"
        self._attr_unique_id = f"{entry.entry_id}_temp"
        self._attr_native_unit_of_measurement = "°C"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
        }

    @property
    def native_value(self):
        return (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("sns_3", {})
            .get("value")
        )


class ExoPoolORPSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Exo Pool ORP sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-check"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Exo Pool ORP"
        self._attr_unique_id = f"{entry.entry_id}_orp"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
        }

    @property
    def native_value(self):
        return (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("sns_2", {})
            .get("value")
        )


class ExoPoolORPBoostTimeSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Exo Pool ORP boost time sensor."""

    _attr_icon = "mdi:timer-sand"
    _attr_native_unit_of_measurement = "min"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Exo Pool ORP Boost Time Remaining"
        self._attr_unique_id = f"{entry.entry_id}_orp_boost_time"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
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


class ExoPoolPHSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Exo Pool pH sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:test-tube"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Exo Pool pH"
        self._attr_unique_id = f"{entry.entry_id}_ph"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
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


class ExoPoolPumpRPMSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Exo Pool pump RPM sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "RPM"
    _attr_icon = "mdi:fan"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Pool Pump RPM"
        self._attr_unique_id = f"{entry.entry_id}_pump_rpm"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
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


class ExoPoolErrorCodeSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Exo Pool error code sensor."""

    _attr_icon = "mdi:alert-circle"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Pool Error Code"
        self._attr_unique_id = f"{entry.entry_id}_error_code"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
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


class ExoPoolFirmwareSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Exo Pool firmware sensor."""

    _attr_icon = "mdi:chip"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Pool Firmware"
        self._attr_unique_id = f"{entry.entry_id}_firmware"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
        }

    @property
    def native_value(self):
        return self.coordinator.data.get("debug", {}).get("Version Firmware")
