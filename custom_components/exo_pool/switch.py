import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DOMAIN, get_coordinator, set_pool_value

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the switch platform for Exo Pool."""
    # Retrieve shared coordinator
    coordinator = await get_coordinator(hass, entry)

    # Add switch entities
    entities = [
        ExoPoolORPBoostSwitch(entry, coordinator),
        ExoPoolPowerStateSwitch(entry, coordinator),
        ExoPoolProductionSwitch(entry, coordinator),
    ]
    async_add_entities(entities)


class ExoPoolORPBoostSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of an Exo Pool ORP Boost switch."""

    _attr_icon = "mdi:water-pump"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Pool ORP Boost"
        self._attr_unique_id = f"{entry.entry_id}_orp_boost"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
        }

    @property
    def is_on(self):
        """Return the state of the ORP Boost."""
        boost_time = (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("boost_time")
        )
        return bool(boost_time) and boost_time != "00:00" if boost_time else False

    @property
    def available(self):
        """Return availability based on coordinator data."""
        return (
            self.coordinator.data is not None
            and "equipment" in self.coordinator.data
            and "swc_0" in self.coordinator.data["equipment"]
        )

    async def async_turn_on(self):
        """Turn on the ORP Boost."""
        await set_pool_value(self.hass, self._entry, "boost", 1)

    async def async_turn_off(self):
        """Turn off the ORP Boost."""
        await set_pool_value(self.hass, self._entry, "boost", 0)


class ExoPoolPowerStateSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of an Exo Pool Power State switch."""

    _attr_icon = "mdi:power"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Exo Power State"
        self._attr_unique_id = f"{entry.entry_id}_exo_state"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
        }

    @property
    def is_on(self):
        """Return the state of the Exo Power."""
        return bool(
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("filter_pump", {})
            .get("state")
        )

    @property
    def available(self):
        """Return availability based on coordinator data."""
        return (
            self.coordinator.data is not None
            and "equipment" in self.coordinator.data
            and "swc_0" in self.coordinator.data["equipment"]
        )

    async def async_turn_on(self):
        """Turn on the Exo Power."""
        await set_pool_value(self.hass, self._entry, "exo_state", 1)

    async def async_turn_off(self):
        """Turn off the Exo Power."""
        await set_pool_value(self.hass, self._entry, "exo_state", 0)


class ExoPoolProductionSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of an Exo Pool Production switch."""

    _attr_icon = "mdi:water-plus"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Exo Production"
        self._attr_unique_id = f"{entry.entry_id}_production"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
        }

    @property
    def is_on(self):
        """Return the state of the Production."""
        return bool(
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("production")
        )

    @property
    def available(self):
        """Return availability based on coordinator data."""
        return (
            self.coordinator.data is not None
            and "equipment" in self.coordinator.data
            and "swc_0" in self.coordinator.data["equipment"]
        )

    async def async_turn_on(self):
        """Turn on the Production."""
        await set_pool_value(self.hass, self._entry, "production", 1)

    async def async_turn_off(self):
        """Turn off the Production."""
        await set_pool_value(self.hass, self._entry, "production", 0)
