from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .api import get_coordinator, set_pool_value, DOMAIN
import logging
import asyncio

_LOGGER = logging.getLogger(__name__)

_LOGGER.debug("Switch platform module loaded")


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the switch platform for Exo Pool."""
    _LOGGER.debug("Setting up switch platform for entry: %s", entry.entry_id)
    # Retrieve shared coordinator
    coordinator = await get_coordinator(hass, entry)

    # Add switch entities
    entities = [
        ORPBoostSwitch(entry, coordinator),
        PowerSwitch(entry, coordinator),
        ChlorinatorSwitch(entry, coordinator),
        Aux1Switch(entry, coordinator),
        Aux2Switch(entry, coordinator),
        SWCLowSwitch(entry, coordinator),
    ]
    async_add_entities(entities)


class ORPBoostSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of an ORP Boost switch."""

    _attr_icon = "mdi:water-pump"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "ORP Boost"
        self._attr_unique_id = f"{entry.entry_id}_orp_boost"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def is_on(self):
        """Return the state of the ORP Boost."""
        return bool(
            self.coordinator.data.get("equipment", {}).get("swc_0", {}).get("boost")
        )

    @property
    def available(self):
        """Return availability based on coordinator data."""
        return (
            self.coordinator.data is not None
            and "equipment" in self.coordinator.data
            and "swc_0" in self.coordinator.data["equipment"]
        )

    @property
    def extra_state_attributes(self):
        """Provide additional ORP boost time attributes."""
        time_str = (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("boost_time")
        )
        if time_str and isinstance(time_str, str) and ":" in time_str:
            try:
                hours, minutes = map(int, time_str.split(":"))
                return {"boost_time_remaining": hours * 60 + minutes}
            except (ValueError, TypeError):
                _LOGGER.error("Invalid boost_time format: %s", time_str)
                return {}
        return {}

    async def async_turn_on(self):
        """Turn on the ORP Boost."""
        await set_pool_value(self.hass, self._entry, "boost", 1, delay_refresh=True)
        self._attr_is_on = True  # Optimistic update
        self.async_write_ha_state()

    async def async_turn_off(self):
        """Turn off the ORP Boost."""
        await set_pool_value(self.hass, self._entry, "boost", 0, delay_refresh=True)
        self._attr_is_on = False  # Optimistic update
        self.async_write_ha_state()


class PowerSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a Power switch."""

    _attr_icon = "mdi:power"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Power"
        self._attr_unique_id = f"{entry.entry_id}_exo_state"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def is_on(self):
        """Return the state of the Power."""
        return bool(
            self.coordinator.data.get("equipment", {}).get("swc_0", {}).get("exo_state")
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
        """Turn on the Power."""
        await set_pool_value(self.hass, self._entry, "exo_state", 1, delay_refresh=True)
        self._attr_is_on = True  # Optimistic update
        self.async_write_ha_state()

    async def async_turn_off(self):
        """Turn off the Power."""
        await set_pool_value(self.hass, self._entry, "exo_state", 0, delay_refresh=True)
        self._attr_is_on = False  # Optimistic update
        self.async_write_ha_state()


class ChlorinatorSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a Chlorinator switch."""

    _attr_icon = "mdi:water-plus"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Chlorinator"
        self._attr_unique_id = f"{entry.entry_id}_production"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def is_on(self):
        """Return the state of the Chlorinator."""
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
        """Turn on the Chlorinator."""
        await set_pool_value(
            self.hass, self._entry, "production", 1, delay_refresh=True
        )
        self._attr_is_on = True  # Optimistic update
        self.async_write_ha_state()

    async def async_turn_off(self):
        """Turn off the Chlorinator."""
        await set_pool_value(
            self.hass, self._entry, "production", 0, delay_refresh=True
        )
        self._attr_is_on = False  # Optimistic update
        self.async_write_ha_state()


class Aux1Switch(CoordinatorEntity, SwitchEntity):
    """Representation of an Aux 1 switch."""

    _attr_icon = "mdi:toggle-switch"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Aux 1"
        self._attr_unique_id = f"{entry.entry_id}_aux_1"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def is_on(self):
        """Return the state of Aux 1."""
        return bool(
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("aux_1", {})
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
        """Turn on Aux 1."""
        await set_pool_value(
            self.hass, self._entry, "aux_1.state", 1, delay_refresh=True
        )
        self._attr_is_on = True  # Optimistic update
        self.async_write_ha_state()

    async def async_turn_off(self):
        """Turn off Aux 1."""
        await set_pool_value(
            self.hass, self._entry, "aux_1.state", 0, delay_refresh=True
        )
        self._attr_is_on = False  # Optimistic update
        self.async_write_ha_state()


class Aux2Switch(CoordinatorEntity, SwitchEntity):
    """Representation of an Aux 2 switch."""

    _attr_icon = "mdi:toggle-switch"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Aux 2"
        self._attr_unique_id = f"{entry.entry_id}_aux_2"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def is_on(self):
        """Return the state of Aux 2."""
        return bool(
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("aux_2", {})
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
        """Turn on Aux 2."""
        await set_pool_value(
            self.hass, self._entry, "aux_2.state", 1, delay_refresh=True
        )
        self._attr_is_on = True  # Optimistic update
        self.async_write_ha_state()

    async def async_turn_off(self):
        """Turn off Aux 2."""
        await set_pool_value(
            self.hass, self._entry, "aux_2.state", 0, delay_refresh=True
        )
        self._attr_is_on = False  # Optimistic update
        self.async_write_ha_state()


class SWCLowSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a SWC Low switch."""

    _attr_icon = "mdi:water-minus"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "SWC Low"
        self._attr_unique_id = f"{entry.entry_id}_swc_low"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def is_on(self):
        """Return the state of SWC Low."""
        return bool(
            self.coordinator.data.get("equipment", {}).get("swc_0", {}).get("low")
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
        """Turn on SWC Low."""
        await set_pool_value(self.hass, self._entry, "low", 1, delay_refresh=True)
        self._attr_is_on = True  # Optimistic update
        self.async_write_ha_state()

    async def async_turn_off(self):
        """Turn off SWC Low."""
        await set_pool_value(self.hass, self._entry, "low", 0, delay_refresh=True)
        self._attr_is_on = False  # Optimistic update
        self.async_write_ha_state()
