from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers import aiohttp_client
from datetime import timedelta
import aiohttp
import async_timeout
import logging
import time
import asyncio

_LOGGER = logging.getLogger(__name__)

# API endpoints and keys from config_flow.py and REST sensors
LOGIN_URL = "https://prod.zodiac-io.com/users/v1/login"
REFRESH_URL = "https://prod.zodiac-io.com/users/v1/refresh"
DATA_URL_TEMPLATE = "https://prod.zodiac-io.com/devices/v1/{}/shadow"
API_KEY_PROD = "EOOEMOW4YR6QNB11"
API_KEY_R = "EOOEMOW4YR6QNB07"

# Error code translation
ERROR_CODES = {
    0: "No Error",
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
# User-configurable refresh interval (seconds)
REFRESH_OPTION_KEY = "refresh_interval"
REFRESH_DEFAULT = 30
REFRESH_MIN = 10
REFRESH_MAX = 600


async def async_update_data(hass: HomeAssistant, entry: ConfigEntry):
    """Fetch data from the Exo Pool API, handling token refresh."""
    global _authentication_failed, _last_auth_error
    _authentication_failed = False  # Reset flag
    _last_auth_error = None
    serial_number = entry.data["serial_number"]
    id_token = entry.data.get("id_token")
    expires_at = entry.data.get("expires_at", 0)

    # Reuse Home Assistant's shared aiohttp client session
    session = aiohttp_client.async_get_clientsession(hass)
    # Refresh token if missing, expired, or about to expire
    if (
        not id_token
        or _last_auth_error == '{"message":"The incoming token has expired"}'
        or time.time() > expires_at
    ):
        _LOGGER.debug(
            "Refreshing authentication tokens due to missing, expired, or upcoming expiration"
        )
        refreshed = False
        if "refresh_token" in entry.data:
            # Try refresh first
            try:
                refreshed = await _refresh_token(hass, entry, session)
            except Exception as e:
                _LOGGER.debug(
                    "Token refresh failed: %s, falling back to full login", e
                )

        if not refreshed:
            # Full login
            await _full_login(hass, entry, session)

        id_token = entry.data.get("id_token")  # Update after refresh/login
        _LOGGER.debug("Authentication token refreshed: %s", id_token[:10] + "...")

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
            is_rate_limited = response.status == 429 or "Too Many Requests" in str(error_text)
            if is_rate_limited:
                _LOGGER.warning("Rate limited fetching device data: %s", error_text)
            else:
                _LOGGER.error("Failed to fetch device data: %s", error_text)
            # Gracefully handle rate limiting: keep previous data and back off
            if is_rate_limited:
                coordinator = (
                    hass.data.get(DOMAIN, {})
                    .get(entry.entry_id, {})
                    .get("coordinator")
                )
                if coordinator and coordinator.data is not None:
                    try:
                        current = getattr(coordinator, "update_interval", timedelta(seconds=REFRESH_DEFAULT))
                        cur_s = int(current.total_seconds()) if current else REFRESH_DEFAULT
                        # Exponential backoff up to REFRESH_MAX
                        new_s = max(cur_s, min(cur_s * 2, REFRESH_MAX))
                        if new_s != cur_s:
                            coordinator.update_interval = timedelta(seconds=new_s)
                            _LOGGER.warning(
                                "429 Too Many Requests. Keeping previous data and backing off to %ss",
                                new_s,
                            )
                        else:
                            _LOGGER.warning(
                                "429 Too Many Requests. Keeping previous data at %ss interval",
                                cur_s,
                            )
                    except Exception as be:
                        _LOGGER.debug("Backoff adjustment failed: %s", be)
                    # Return previous data to avoid gaps
                    return coordinator.data
            if "The incoming token has expired" in error_text:
                _last_auth_error = (
                    error_text  # Trigger re-authentication on next cycle
                )
            raise Exception(f"Device data fetch failed: {error_text}")
        data = await response.json()
        _LOGGER.debug("Device data: %s", data)
        return data.get("state", {}).get("reported", {})


async def _full_login(
    hass: HomeAssistant, entry: ConfigEntry, session: aiohttp.ClientSession
):
    """Perform full login with email and password."""
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
            global _authentication_failed, _last_auth_error
            _authentication_failed = True
            _last_auth_error = error_text
            raise Exception(f"Authentication failed: {error_text}")
        data = await response.json()
        _LOGGER.debug(
            "Login response data: %s",
            {k: v if k != "id_token" else v[:10] + "..." for k, v in data.items()},
        )
        id_token = data.get("userPoolOAuth", {}).get("IdToken")
        refresh_token = data.get("userPoolOAuth", {}).get("RefreshToken")
        auth_token = data.get("authentication_token")
        user_id = data.get("id")
        expires_in = data.get("userPoolOAuth", {}).get(
            "ExpiresIn", 3600
        )  # Default to 1 hour if not present
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
        update_data = {
            **entry.data,
            "id_token": id_token,
            "auth_token": auth_token,
            "user_id": user_id,
            "expires_at": time.time()
            + expires_in
            - 60,  # Refresh 1 min before expiration
        }
        if refresh_token:
            update_data["refresh_token"] = refresh_token
        hass.config_entries.async_update_entry(entry, data=update_data)


async def _refresh_token(
    hass: HomeAssistant, entry: ConfigEntry, session: aiohttp.ClientSession
) -> bool:
    """Refresh token using refresh_token."""
    headers = {"Content-Type": "application/json", "User-Agent": "okhttp/3.14.7"}
    payload = {
        "email": entry.data["email"],
        "refresh_token": entry.data["refresh_token"],
    }
    _LOGGER.debug("Refresh token payload: %s", {**payload, "refresh_token": "REDACTED"})
    async with session.post(REFRESH_URL, json=payload, headers=headers) as response:
        _LOGGER.debug("Refresh response status: %s", response.status)
        if response.status != 200:
            error_text = await response.text()
            _LOGGER.error("Failed to refresh token: %s", error_text)
            return False
        data = await response.json()
        _LOGGER.debug(
            "Refresh response data: %s",
            {k: v if k != "id_token" else v[:10] + "..." for k, v in data.items()},
        )
        id_token = data.get("userPoolOAuth", {}).get("IdToken")
        refresh_token = data.get("userPoolOAuth", {}).get(
            "RefreshToken"
        )  # May not be present
        auth_token = data.get("authentication_token")
        user_id = data.get("id")
        expires_in = data.get("userPoolOAuth", {}).get("ExpiresIn", 3600)
        if not id_token:
            _LOGGER.error("No userPoolOAuth.IdToken in refresh response: %s", data)
            return False
        update_data = {
            **entry.data,
            "id_token": id_token,
            "auth_token": auth_token,
            "user_id": user_id,
            "expires_at": time.time() + expires_in - 60,
        }
        if refresh_token:
            update_data["refresh_token"] = refresh_token
        hass.config_entries.async_update_entry(entry, data=update_data)
        return True


async def get_coordinator(hass: HomeAssistant, entry: ConfigEntry):
    """Get or create a shared DataUpdateCoordinator for the config entry."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    if entry.entry_id not in hass.data[DOMAIN]:
        # Initialize refresh interval from entry options (clamped)
        seconds = entry.options.get(REFRESH_OPTION_KEY, REFRESH_DEFAULT)
        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            seconds = REFRESH_DEFAULT
        seconds = max(REFRESH_MIN, min(REFRESH_MAX, seconds))
        coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name="Exo Pool",
            update_method=lambda: async_update_data(hass, entry),
            # Poll at a moderate interval to reduce cloud load
            update_interval=timedelta(seconds=seconds),
        )
        hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}
        # Perform initial refresh
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception as e:
            _LOGGER.error("Initial data fetch failed: %s", e)
            raise
    return hass.data[DOMAIN][entry.entry_id]["coordinator"]


async def async_set_refresh_interval(
    hass: HomeAssistant, entry: ConfigEntry, seconds: int
):
    """Update the refresh interval for the coordinator and persist to options."""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        seconds = REFRESH_DEFAULT
    seconds = max(REFRESH_MIN, min(REFRESH_MAX, seconds))

    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    coordinator.update_interval = timedelta(seconds=seconds)
    _LOGGER.debug("Set refresh interval to %ss for %s", seconds, entry.entry_id)

    # Persist to entry options
    new_options = dict(entry.options)
    new_options[REFRESH_OPTION_KEY] = seconds
    hass.config_entries.async_update_entry(entry, options=new_options)


async def set_pool_value(hass, entry, setting, value, delay_refresh=False):
    """Set a pool setting value via the API."""
    serial_number = entry.data["serial_number"]
    id_token = entry.data.get("id_token")
    if not id_token:
        _LOGGER.error("No id_token available for setting %s", setting)
        return

    # Build nested dict for setting
    def build_nested_dict(keys, val):
        d = val
        for key in reversed(keys):
            d = {key: d}
        return d

    keys = setting.split(".")
    nested_value = build_nested_dict(keys, value)

    payload = {"state": {"desired": {"equipment": {"swc_0": nested_value}}}}
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
    session = aiohttp_client.async_get_clientsession(hass)
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
                # Refresh coordinator with delay if requested
                if delay_refresh:
                    await asyncio.sleep(10)  # Wait 10 seconds for Exo to update
                    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
                    await coordinator.async_request_refresh()
                else:
                    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
                    await coordinator.async_request_refresh()


async def set_heating_value(hass, entry, key: str, value, delay_refresh: bool = False):
    """Set a top-level heating value via the API (e.g., sp)."""
    serial_number = entry.data["serial_number"]
    id_token = entry.data.get("id_token")
    if not id_token:
        _LOGGER.error("No id_token available for heating.%s", key)
        return

    payload = {"state": {"desired": {"heating": {key: value}}}}
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "okhttp/3.14.7",
        "Authorization": f"Bearer {id_token}",
    }
    url = DATA_URL_TEMPLATE.format(serial_number)
    _LOGGER.debug(
        "Setting heating.%s to %s at %s with payload: %s",
        key,
        value,
        url,
        payload,
    )
    session = aiohttp_client.async_get_clientsession(hass)
    async with session.post(url, json=payload, headers=headers) as response:
        response_text = await response.text()
        _LOGGER.debug("Heating set response status: %s, body: %s", response.status, response_text)
        if response.status != 200:
            _LOGGER.error(
                "Failed to set heating.%s: %s (Status: %s)",
                key,
                response_text,
                response.status,
            )
        else:
            _LOGGER.debug("Successfully set heating.%s to %s", key, value)
            coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
            if delay_refresh:
                await asyncio.sleep(10)
            await coordinator.async_request_refresh()


async def update_schedule(
    hass: HomeAssistant,
    entry: ConfigEntry,
    schedule_key: str,
    *,
    start: str | None = None,
    end: str | None = None,
    rpm: int | None = None,
):
    """Update a schedule's timer (and rpm for VSP) via the API."""
    serial_number = entry.data["serial_number"]
    id_token = entry.data.get("id_token")
    if not id_token:
        _LOGGER.error("No id_token available for schedule %s", schedule_key)
        raise Exception("Unauthenticated")

    sched_patch: dict = {}
    if start is not None or end is not None:
        timer: dict = {}
        if start is not None:
            timer["start"] = start
        if end is not None:
            timer["end"] = end
        sched_patch["timer"] = timer
    if rpm is not None:
        try:
            sched_patch["rpm"] = int(rpm)
        except (TypeError, ValueError):
            _LOGGER.warning("Invalid rpm value %s for schedule %s", rpm, schedule_key)

    payload = {"state": {"desired": {"schedules": {schedule_key: sched_patch}}}}
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "okhttp/3.14.7",
        "Authorization": f"Bearer {id_token}",
    }
    url = DATA_URL_TEMPLATE.format(serial_number)
    _LOGGER.debug(
        "Updating schedule %s at %s with payload: %s",
        schedule_key,
        url,
        payload,
    )
    session = aiohttp_client.async_get_clientsession(hass)
    async with session.post(url, json=payload, headers=headers) as response:
        response_text = await response.text()
        _LOGGER.debug("Schedule update response: %s %s", response.status, response_text)
        if response.status != 200:
            _LOGGER.error(
                "Failed to update schedule %s: %s (Status: %s)",
                schedule_key,
                response_text,
                response.status,
            )
            raise Exception(f"Schedule update failed: {response_text}")
    # Refresh to reflect updated schedule
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    await coordinator.async_request_refresh()
