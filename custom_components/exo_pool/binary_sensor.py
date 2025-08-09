from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .api import (
    get_coordinator,
    ERROR_CODES,
    _authentication_failed,
    _last_auth_error,
    DOMAIN,
)
import logging

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the binary sensor platform for Exo Pool."""
    # Retrieve shared coordinator
    coordinator = await get_coordinator(hass, entry)

    # Add binary sensors
    entities = [
        ExoPoolFilterPumpBinarySensor(entry, coordinator),
        ExoPoolErrorStateBinarySensor(entry, coordinator),
        ExoPoolSaltWaterChlorinatorBinarySensor(entry, coordinator),
        ExoPoolAuthenticationStatusBinarySensor(entry, coordinator),
        ExoPoolConnectedBinarySensor(entry, coordinator),
    ]
    async_add_entities(entities)


# Binary Sensor Classes
class ExoPoolFilterPumpBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an Exo Pool filter pump binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:pump"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Pool Filter Pump"
        self._attr_unique_id = f"{entry.entry_id}_filter_pump"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
        }

    @property
    def is_on(self):
        return bool(
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("filter_pump", {})
            .get("state")
        )

    @property
    def available(self):
        """Return availability based on data fetch success."""
        return self.coordinator.data is not None


class ExoPoolErrorStateBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an Exo Pool error state binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Pool Error State"
        self._attr_unique_id = f"{entry.entry_id}_error_state"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
        }

    @property
    def is_on(self):
        return bool(
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("error_state")
        )

    @property
    def extra_state_attributes(self):
        """Provide error code and message as attributes."""
        code = (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("error_code")
        )
        return {
            "error_code": code,
            "error_message": ERROR_CODES.get(
                int(code) if code is not None else 0, "Unknown Error"
            ),
        }

    @property
    def available(self):
        """Return availability based on data fetch success."""
        return self.coordinator.data is not None


class ExoPoolSaltWaterChlorinatorBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an Exo Pool salt water chlorinator binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:water-plus"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Pool Salt Water Chlorinator"
        self._attr_unique_id = f"{entry.entry_id}_salt_water_chlorinator"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
        }

    @property
    def is_on(self):
        return bool(
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("production")
        )

    @property
    def available(self):
        """Return availability based on data fetch success."""
        return self.coordinator.data is not None


class ExoPoolAuthenticationStatusBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an Exo Pool authentication status binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:lock-check"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Exo Authentication Status"
        self._attr_unique_id = f"{entry.entry_id}_authentication_status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
        }

    @property
    def is_on(self):
        """Return true if authentication is successful."""
        return not _authentication_failed

    @property
    def extra_state_attributes(self):
        """Provide additional details about authentication status."""
        return {"last_error": _last_auth_error} if _authentication_failed else {}

    @property
    def available(self):
        """Return availability based on data fetch success."""
        return self.coordinator.data is not None


class ExoPoolConnectedBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an Exo Pool connected binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:signal"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Exo Connected"
        self._attr_unique_id = f"{entry.entry_id}_connected"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
        }

    @property
    def is_on(self):
        return self.coordinator.data is not None and bool(self.coordinator.data)

    @property
    def available(self):
        """Return availability based on data fetch success."""
        return self.coordinator.data is not None
