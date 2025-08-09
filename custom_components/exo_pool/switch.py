from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import aiohttp
import async_timeout
import logging
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# API endpoint
DATA_URL_TEMPLATE = "https://prod.zodiac-io.com/devices/v1/{}/shadow"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the switch platform for Exo Pool."""
    serial_number = entry.data["serial_number"]
    id_token = entry.data.get("id_token")

    if not id_token:
        _LOGGER.error("No id_token available for switch setup")
        return

    # Add switch entities
    entities = [
        ExoPoolORPBoostSwitch(entry, hass, serial_number, id_token),
        ExoPoolPowerStateSwitch(entry, hass, serial_number, id_token),
        ExoPoolProductionSwitch(entry, hass, serial_number, id_token),
    ]
    async_add_entities(entities)


class ExoPoolORPBoostSwitch(SwitchEntity):
    """Representation of an Exo Pool ORP Boost switch."""

    _attr_icon = "mdi:water-boost"

    def __init__(
        self, entry: ConfigEntry, hass: HomeAssistant, serial_number: str, id_token: str
    ):
        self._entry = entry
        self.hass = hass
        self._serial_number = serial_number
        self._id_token = id_token
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
        data = self.hass.states.get(f"sensor.exo_pool_orp_boost_time_remaining")
        return data and data.state != "0" if data else False

    @property
    def available(self):
        """Return availability based on data fetch success."""
        return (
            self.hass.states.get(f"sensor.exo_pool_orp_boost_time_remaining")
            is not None
        )

    async def async_turn_on(self):
        """Turn on the ORP Boost."""
        await set_switch_value(
            self.hass, self._entry, self._serial_number, self._id_token, "boost", 1
        )

    async def async_turn_off(self):
        """Turn off the ORP Boost."""
        await set_switch_value(
            self.hass, self._entry, self._serial_number, self._id_token, "boost", 0
        )


class ExoPoolPowerStateSwitch(SwitchEntity):
    """Representation of an Exo Pool Power State switch."""

    _attr_icon = "mdi:power"

    def __init__(
        self, entry: ConfigEntry, hass: HomeAssistant, serial_number: str, id_token: str
    ):
        self._entry = entry
        self.hass = hass
        self._serial_number = serial_number
        self._id_token = id_token
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
        data = self.hass.states.get(f"binary_sensor.pool_filter_pump")
        return data and data.state == "on" if data else False

    @property
    def available(self):
        """Return availability based on data fetch success."""
        return self.hass.states.get(f"binary_sensor.pool_filter_pump") is not None

    async def async_turn_on(self):
        """Turn on the Exo Power."""
        await set_switch_value(
            self.hass, self._entry, self._serial_number, self._id_token, "exo_state", 1
        )

    async def async_turn_off(self):
        """Turn off the Exo Power."""
        await set_switch_value(
            self.hass, self._entry, self._serial_number, self._id_token, "exo_state", 0
        )


class ExoPoolProductionSwitch(SwitchEntity):
    """Representation of an Exo Pool Production switch."""

    _attr_icon = "mdi:water-plus"

    def __init__(
        self, entry: ConfigEntry, hass: HomeAssistant, serial_number: str, id_token: str
    ):
        self._entry = entry
        self.hass = hass
        self._serial_number = serial_number
        self._id_token = id_token
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
        data = self.hass.states.get(f"binary_sensor.pool_salt_water_chlorinator")
        return data and data.state == "on" if data else False

    @property
    def available(self):
        """Return availability based on data fetch success."""
        return (
            self.hass.states.get(f"binary_sensor.pool_salt_water_chlorinator")
            is not None
        )

    async def async_turn_on(self):
        """Turn on the Production."""
        await set_switch_value(
            self.hass, self._entry, self._serial_number, self._id_token, "production", 1
        )

    async def async_turn_off(self):
        """Turn off the Production."""
        await set_switch_value(
            self.hass, self._entry, self._serial_number, self._id_token, "production", 0
        )


async def set_switch_value(hass, entry, serial_number, id_token, setting, value):
    """Set a switch value via the API."""
    payload = {"state": {"desired": {"equipment": {"swc_0": {setting: value}}}}}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "okhttp/3.14.7",
        "Authorization": id_token,
    }
    url = DATA_URL_TEMPLATE.format(serial_number)
    _LOGGER.debug(
        "Setting %s to %s at %s with payload: %s", setting, value, url, payload
    )
    async with aiohttp.ClientSession() as session:
        async with session.put(url, json=payload, headers=headers) as response:
            if response.status != 200:
                error_text = await response.text()
                _LOGGER.error(
                    "Failed to set %s: %s (Status: %s)",
                    setting,
                    error_text,
                    response.status,
                )
            else:
                _LOGGER.debug("Successfully set %s to %s", setting, value)
