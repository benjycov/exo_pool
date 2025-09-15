from homeassistant.components.number import NumberEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfTime
from .api import (
    get_coordinator,
    set_pool_value,
    DOMAIN,
    async_set_refresh_interval,
    REFRESH_MIN,
    REFRESH_MAX,
    REFRESH_DEFAULT,
)
import logging

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the number platform for Exo Pool."""
    _LOGGER.debug("Setting up number platform for entry: %s", entry.entry_id)
    # Retrieve shared coordinator
    coordinator = await get_coordinator(hass, entry)

    # Add only supported number entities based on capabilities
    swc = coordinator.data.get("equipment", {}).get("swc_0", {}) if coordinator.data else {}
    ph_capable = swc.get("ph_only", 0) == 1
    orp_capable = swc.get("dual_link", 0) == 1

    entities: list[NumberEntity] = []
    # Always add refresh interval control
    entities.append(ExoPoolRefreshIntervalNumber(entry, coordinator))
    if orp_capable:
        entities.append(ExoPoolORPSetPointNumber(entry, coordinator))
    if ph_capable:
        entities.append(ExoPoolPHSetPointNumber(entry, coordinator))

    async_add_entities(entities)


class ExoPoolORPSetPointNumber(CoordinatorEntity, NumberEntity):
    """Representation of an Exo Pool ORP set point number entity."""

    _attr_icon = "mdi:water-check"
    _attr_mode = "box"
    _attr_step = 10
    _attr_native_min_value = 600
    _attr_native_max_value = 900

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "ORP Set Point"
        self._attr_unique_id = f"{entry.entry_id}_orp_set_point"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
        }

    @property
    def native_value(self):
        """Return the current ORP set point value."""
        return self.coordinator.data.get("equipment", {}).get("swc_0", {}).get("orp_sp")

    async def async_set_native_value(self, value):
        """Set the ORP set point value."""
        await set_pool_value(self.hass, self._entry, "orp_sp", int(value))
        # Refresh coordinator to reflect updated state
        await self.coordinator.async_request_refresh()

    @property
    def available(self):
        """Return availability based on Exo Connected binary sensor and ORP capability."""
        return (
            self.coordinator.data is not None
            and bool(self.coordinator.data)
            and self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("dual_link", 0)
            == 1
        )


class ExoPoolPHSetPointNumber(CoordinatorEntity, NumberEntity):
    """Representation of an Exo Pool pH set point number entity."""

    _attr_icon = "mdi:test-tube"
    _attr_mode = "box"
    _attr_step = 0.1
    _attr_native_min_value = 6.0
    _attr_native_max_value = 7.6

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "pH Set Point"
        self._attr_unique_id = f"{entry.entry_id}_ph_set_point"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
        }

    @property
    def native_value(self):
        """Return the current pH set point value."""
        value = self.coordinator.data.get("equipment", {}).get("swc_0", {}).get("ph_sp")
        return value / 10 if value is not None else None

    async def async_set_native_value(self, value):
        """Set the pH set point value."""
        await set_pool_value(self.hass, self._entry, "ph_sp", value * 10)
        # Refresh coordinator to reflect updated state
        await self.coordinator.async_request_refresh()

    @property
    def available(self):
        """Return availability based on Exo Connected binary sensor and PH capability."""
        return (
            self.coordinator.data is not None
            and bool(self.coordinator.data)
            and self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("ph_only", 0)
            == 1
        )


class ExoPoolRefreshIntervalNumber(CoordinatorEntity, NumberEntity):
    """Number to control the data refresh interval in seconds."""

    _attr_icon = "mdi:update"
    _attr_mode = "box"
    _attr_step = 1
    _attr_native_min_value = REFRESH_MIN
    _attr_native_max_value = REFRESH_MAX
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Refresh Interval"
        self._attr_unique_id = f"{entry.entry_id}_refresh_interval"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
        }

    @property
    def native_value(self):
        """Return the current refresh interval in seconds."""
        interval = getattr(self.coordinator, "update_interval", None)
        if interval is None:
            return REFRESH_DEFAULT
        try:
            return int(interval.total_seconds())
        except Exception:
            return REFRESH_DEFAULT

    async def async_set_native_value(self, value):
        """Set the refresh interval in seconds and update coordinator."""
        await async_set_refresh_interval(self.hass, self._entry, int(value))
