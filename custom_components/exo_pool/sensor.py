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
        PHSensor(entry, coordinator),
        ErrorCodeSensor(entry, coordinator),
        ErrorCodeTextSensor(entry, coordinator),
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

    @property
    def extra_state_attributes(self):
        """Provide additional ORP attributes."""
        return {
            "set_point": self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("orp_sp")
        }


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

    @property
    def extra_state_attributes(self):
        """Provide additional pH attributes."""
        return {
            "set_point": self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("ph_sp")
            / 10  # Convert to pH scale (e.g., 72 → 7.2)
        }


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


class ErrorCodeTextSensor(CoordinatorEntity, SensorEntity):
    """Representation of an error code text sensor."""

    _attr_icon = "mdi:alert-circle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Error Code Text"
        self._attr_unique_id = f"{entry.entry_id}_error_code_text"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def native_value(self):
        """Return the error message text."""
        code = (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("error_code")
        )
        return ERROR_CODES.get(int(code) if code is not None else 0, "No Error")


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
