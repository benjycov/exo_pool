from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from datetime import timedelta
import aiohttp
import async_timeout
import logging

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

# Domain constant
DOMAIN = "exo_pool"


async def async_update_data(hass: HomeAssistant, entry: ConfigEntry):
    """Fetch data from the Exo Pool API, handling token refresh."""
    global _authentication_failed, _last_auth_error
    _authentication_failed = False  # Reset flag
    _last_auth_error = None
    serial_number = entry.data["serial_number"]
    id_token = entry.data.get("id_token")

    async with aiohttp.ClientSession() as session:
        # Refresh token if missing or expired
        if (
            not id_token
            or _last_auth_error == '{"message":"The incoming token has expired"}'
        ):
            _LOGGER.debug(
                "Refreshing authentication tokens due to missing or expired token"
            )
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "okhttp/3.14.7",
            }
            payload = {
                "api_key": API_KEY_PROD,
                "email": entry.data["email"],
                "password": entry.data["password"],
            }
            _LOGGER.debug("Login payload: %s", {**payload, "password": "REDACTED"})
            async with session.post(
                LOGIN_URL, json=payload, headers=headers
            ) as response:
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
                    {
                        k: v if k != "id_token" else v[:10] + "..."
                        for k, v in data.items()
                    },
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
            "Authorization": f"Bearer {id_token}",
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
                    _last_auth_error = (
                        error_text  # Trigger re-authentication on next cycle
                    )
                raise Exception(f"Device data fetch failed: {error_text}")
            data = await response.json()
            _LOGGER.debug("Device data: %s", data)
            return data.get("state", {}).get("reported", {})


async def get_coordinator(hass: HomeAssistant, entry: ConfigEntry):
    """Get or create a shared DataUpdateCoordinator for the config entry."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    if entry.entry_id not in hass.data[DOMAIN]:
        coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name="Exo Pool",
            update_method=lambda: async_update_data(hass, entry),
            update_interval=timedelta(seconds=60),
        )
        hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}
        # Perform initial refresh
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception as e:
            _LOGGER.error("Initial data fetch failed: %s", e)
            raise
    return hass.data[DOMAIN][entry.entry_id]["coordinator"]


async def set_pool_value(hass, entry, setting, value):
    """Set a pool setting value via the API."""
    serial_number = entry.data["serial_number"]
    id_token = entry.data.get("id_token")
    if not id_token:
        _LOGGER.error("No id_token available for setting %s", setting)
        return

    payload = {"state": {"desired": {"equipment": {"swc_0": {setting: value}}}}}
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "okhttp/3.14.7",
        "Authorization": f"Bearer {id_token}",
    }
    url = DATA_URL_TEMPLATE.format(serial_number)
    _LOGGER.debug(
        "Setting %s to %s at %s with payload: %s and headers: %s",
        setting,
        value,
        url,
        payload,
        {k: v if k != "Authorization" else v[:10] + "..." for k, v in headers.items()},
    )
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            response_text = await response.text()
            _LOGGER.debug(
                "Response status: %s, body: %s", response.status, response_text
            )
            if response.status != 200:
                _LOGGER.error(
                    "Failed to set %s: %s (Status: %s)",
                    setting,
                    response_text,
                    response.status,
                )
            else:
                _LOGGER.debug("Successfully set %s to %s", setting, value)
                # Refresh coordinator to reflect updated state
                coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
                await coordinator.async_request_refresh()
