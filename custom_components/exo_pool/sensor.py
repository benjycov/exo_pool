from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.components.number import NumberEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
import aiohttp
import async_timeout
from datetime import timedelta
import logging
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# API endpoints and keys from config_flow.py and REST sensors
LOGIN_URL = "https://prod.zodiac-io.com/users/v1/login"
DATA_URL_TEMPLATE = "https://prod.zodiac-io.com/devices/v1/{}/shadow"
API_KEY_PROD = "EOOEMOW4YR6QNB11"

# Error code translation
ERROR_CODES = {
    0: "",
    3: "Low Conductivity",
    4: "Check Output",
    6: "Low Water Temp",
    7: "pH Dosing Stop",
    9: "ORP Stop",
}

# Class-level flag to track authentication status
_authentication_failed = False
_last_auth_error = None


async def async_update_data(
    hass: HomeAssistant, entry: ConfigEntry, session: aiohttp.ClientSession
):
    """Fetch data from the Exo Pool API, handling token refresh."""
    global _authentication_failed, _last_auth_error
    _authentication_failed = False  # Reset flag
    _last_auth_error = None
    serial_number = entry.data["serial_number"]
    id_token = entry.data.get("id_token")

    # Refresh token if missing or expired
    if (
        not id_token
        or _last_auth_error == '{"message":"The incoming token has expired"}'
    ):
        _LOGGER.debug(
            "Refreshing authentication tokens due to missing or expired token"
        )
        headers = {"Content-Type": "application/json", "User-Agent": "okhttp/3.14.7"}
        payload = {
            "api_key": API_KEY_PROD,
            "email": entry.data["email"],
            "password": entry.data["password"],
        }
        _LOGGER.debug("Login payload: %s", {**payload, "password": "REDACTED"})
        async with session.post(LOGIN_URL, json=payload, headers=headers) as response:
            _LOGGER.debug("Login response status: %s", response.status)
            if response.status != 200:
                error_text = await response.text()
                _LOGGER.error("Failed to authenticate: %s", error_text)
                _authentication_failed = True
                _last_auth_error = error_text
                raise Exception(f"Authentication failed: {error_text}")
            data = await response.json()
            _LOGGER.debug(
                "Login response data: %s",
                {k: v if k != "id_token" else v[:10] + "..." for k, v in data.items()},
            )
            id_token = data.get("userPoolOAuth", {}).get("IdToken")
            auth_token = data.get("authentication_token")
            user_id = data.get("id")
            if not id_token:
                _LOGGER.error("No userPoolOAuth.IdToken in response: %s", data)
                _authentication_failed = True
                _last_auth_error = "No userPoolOAuth.IdToken received"
                raise Exception("No userPoolOAuth.IdToken received")
            if not auth_token:
                _LOGGER.error("No authentication_token in response: %s", data)
                _authentication_failed = True
                _last_auth_error = "No authentication_token received"
                raise Exception("No authentication_token received")
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    "id_token": id_token,
                    "auth_token": auth_token,
                    "user_id": user_id,
                },
            )

    # Fetch device data
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "okhttp/3.14.7",
        "Authorization": id_token,
    }
    _LOGGER.debug("Fetching data for serial_number: %s", serial_number)
    async with session.get(
        DATA_URL_TEMPLATE.format(serial_number), headers=headers
    ) as response:
        _LOGGER.debug("Data fetch response status: %s", response.status)
        if response.status != 200:
            error_text = await response.text()
            _LOGGER.error("Failed to fetch device data: %s", error_text)
            if "The incoming token has expired" in error_text:
                _last_auth_error = error_text  # Trigger re-authentication on next cycle
            raise Exception(f"Device data fetch failed: {error_text}")
        data = await response.json()
        _LOGGER.debug("Device data: %s", data)
        return data.get("state", {}).get("reported", {})


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor, number, and switch platforms for Exo Pool."""
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Exo Pool",
        update_method=lambda: async_update_data(hass, entry, aiohttp.ClientSession()),
        update_interval=timedelta(seconds=60),
    )

    # Attempt initial data fetch
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.error("Initial data fetch failed: %s", e)
        raise

    # Add sensors, numbers, and binary sensors
    entities = [
        ExoPoolTempSensor(entry, coordinator),
        ExoPoolORPSensor(entry, coordinator),
        ExoPoolORPBoostTimeSensor(entry, coordinator),
        ExoPoolPHSensor(entry, coordinator),
        ExoPoolPumpRPMSensor(entry, coordinator),
        ExoPoolErrorCodeSensor(entry, coordinator),
        ExoPoolErrorSensor(entry, coordinator),
        ExoPoolFirmwareSensor(entry, coordinator),
        ExoPoolFilterPumpBinarySensor(entry, coordinator),
        ExoPoolErrorStateBinarySensor(entry, coordinator),
        ExoPoolSaltWaterChlorinatorBinarySensor(entry, coordinator),
        ExoPoolAuthenticationStatusSensor(entry, coordinator),
        ExoPoolConnectedBinarySensor(entry, coordinator),
        ExoPoolORPSetPointNumber(entry, coordinator),
        ExoPoolPHSetPointNumber(entry, coordinator),
    ]
    async_add_entities(entities)


# Sensor Classes
class ExoPoolTempSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Exo Pool temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:pool-thermometer"

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
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

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
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

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
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
        return (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("boost_time")
        )


class ExoPoolPHSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Exo Pool pH sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:test-tube"

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
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

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
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

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
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


class ExoPoolErrorSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Exo Pool error message sensor."""

    _attr_icon = "mdi:alert-octagon"

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Pool Error"
        self._attr_unique_id = f"{entry.entry_id}_error"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
        }

    @property
    def native_value(self):
        code = (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("error_code")
        )
        return ERROR_CODES.get(int(code) if code is not None else 0, "Unknown Error")


class ExoPoolFirmwareSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Exo Pool firmware sensor."""

    _attr_icon = "mdi:chip"

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
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


class ExoPoolAuthenticationStatusSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Exo Pool authentication status sensor."""

    _attr_icon = "mdi:lock-check"

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
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
    def native_value(self):
        """Return the authentication status."""
        return "Successful" if not _authentication_failed else "Failed"

    @property
    def extra_state_attributes(self):
        """Provide additional details about authentication status."""
        return {"last_error": _last_auth_error} if _authentication_failed else {}


# Binary Sensor Classes
class ExoPoolFilterPumpBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an Exo Pool filter pump binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:pump"

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
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

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
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
    def available(self):
        """Return availability based on data fetch success."""
        return self.coordinator.data is not None


class ExoPoolSaltWaterChlorinatorBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an Exo Pool salt water chlorinator binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:water-plus"

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
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


class ExoPoolConnectedBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an Exo Pool connected binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:signal"

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
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


# Number Classes
class ExoPoolORPSetPointNumber(CoordinatorEntity, NumberEntity):
    """Representation of an Exo Pool ORP set point number entity."""

    _attr_icon = "mdi:water-check"
    _attr_mode = "box"
    _attr_step = 10
    _attr_min_value = 600
    _attr_max_value = 900

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Pool ORP Set Point"
        self._attr_unique_id = f"{entry.entry_id}_orp_set_point"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Exo Pool",
        }

    @property
    def native_value(self):
        """Return the current ORP set point value."""
        return self.coordinator.data.get("equipment", {}).get("swc_0", {}).get("orp_sp")

    async def async_set_value(self, value):
        """Set the ORP set point value."""
        await set_pool_value(self.hass, self._entry, "orp_sp", value)

    @property
    def available(self):
        """Return availability based on data fetch success."""
        return self.coordinator.data is not None


class ExoPoolPHSetPointNumber(CoordinatorEntity, NumberEntity):
    """Representation of an Exo Pool pH set point number entity."""

    _attr_icon = "mdi:test-tube"
    _attr_mode = "box"
    _attr_step = 0.1
    _attr_min_value = 6.0
    _attr_max_value = 7.6

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Pool pH Set Point"
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

    async def async_set_value(self, value):
        """Set the pH set point value."""
        await set_pool_value(self.hass, self._entry, "ph_sp", value)

    @property
    def available(self):
        """Return availability based on data fetch success."""
        return self.coordinator.data is not None


async def set_pool_value(hass, entry, setting, value):
    """Set a pool setting value via the API."""
    serial_number = entry.data["serial_number"]
    id_token = entry.data.get("id_token")
    if not id_token:
        _LOGGER.error("No id_token available for setting %s", setting)
        return

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
