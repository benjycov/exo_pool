from dataclasses import dataclass, field
import random
from typing import Callable

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
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
REFRESH_DEFAULT = 600
REFRESH_MIN = 300
REFRESH_MAX = 3600
BOOST_INTERVAL = 10
BOOST_DURATION = 60
MIN_REQUEST_INTERVAL = 5.0
DEBOUNCED_REFRESH_DELAY = 30.0
WRITE_GAP_SECONDS = 8.0
POST_WRITE_COOLDOWN_SECONDS = 45.0
NO_READ_WINDOW_SECONDS = 30.0
MIN_REFRESH_GUARD_SECONDS = 120.0
SCHEDULE_REFRESH_DELAY = 180.0
READ_DEFERRAL_JITTER_MIN = 15.0
READ_DEFERRAL_JITTER_MAX = 45.0
DEBOUNCE_JITTER_MIN = 30.0
DEBOUNCE_JITTER_MAX = 90.0


async def _async_rate_limit(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Ensure a minimum delay between API requests for a config entry."""
    store = _get_entry_store(hass, entry)
    lock = store.setdefault("request_lock", asyncio.Lock())
    async with lock:
        last_request = store.get("last_request_ts")
        now = time.monotonic()
        if last_request is not None:
            wait_time = MIN_REQUEST_INTERVAL - (now - last_request)
            if wait_time > 0:
                _LOGGER.debug(
                    "Rate limiting API request for %s, sleeping %.2fs",
                    entry.entry_id,
                    wait_time,
                )
                await asyncio.sleep(wait_time)
        store["last_request_ts"] = time.monotonic()


def _get_cooldown_until(store: dict) -> float:
    return float(store.get("cooldown_until", 0.0))


def _is_write_active(store: dict) -> bool:
    quiet_until = float(store.get("write_quiet_until", 0.0))
    return store.get("write_in_flight", 0) > 0 or time.monotonic() < quiet_until


def _cooldown_remaining(hass: HomeAssistant, entry: ConfigEntry) -> float:
    store = _get_entry_store(hass, entry)
    remaining = _get_cooldown_until(store) - time.monotonic()
    return max(0.0, remaining)


def _set_cooldown(
    hass: HomeAssistant, entry: ConfigEntry, seconds: float, *, reason: str
) -> None:
    store = _get_entry_store(hass, entry)
    cooldown_until = time.monotonic() + seconds
    store["cooldown_until"] = max(_get_cooldown_until(store), cooldown_until)
    _LOGGER.debug(
        "Cooldown set for %s: %.1fs (%s)",
        entry.entry_id,
        seconds,
        reason,
    )


def _schedule_debounced_refresh(
    hass: HomeAssistant, entry: ConfigEntry, *, delay: float = DEBOUNCED_REFRESH_DELAY
) -> None:
    """Schedule a single refresh after delay or cooldown, whichever is later."""
    store = _get_entry_store(hass, entry)
    now = time.monotonic()
    target = max(now + delay, _get_cooldown_until(store))
    target += random.uniform(DEBOUNCE_JITTER_MIN, DEBOUNCE_JITTER_MAX)
    if target <= now:
        target = now

    def _clear_debounce_task() -> None:
        store.pop("debounce_refresh_task", None)
        store.pop("refresh_deadline", None)

    if existing_deadline := store.get("refresh_deadline"):
        if existing_deadline >= target:
            return
        if task := store.get("debounce_refresh_task"):
            task.cancel()

    async def _refresh_later() -> None:
        try:
            await asyncio.sleep(max(0.0, target - time.monotonic()))
        except asyncio.CancelledError:
            return
        no_read_until = store.get("no_read_until")
        if no_read_until and time.monotonic() < no_read_until:
            _clear_debounce_task()
            _schedule_debounced_refresh(hass, entry, delay=0.0)
            return
        if _cooldown_remaining(hass, entry) > 0:
            _clear_debounce_task()
            _schedule_debounced_refresh(hass, entry, delay=0.0)
            return
        last_ok = store.get("last_success_fetch_ts")
        if last_ok and time.monotonic() - last_ok < MIN_REFRESH_GUARD_SECONDS:
            _clear_debounce_task()
            return
        _clear_debounce_task()
        await async_request_refresh(hass, entry, allow_debounce=False)

    store["refresh_deadline"] = target
    store["debounce_refresh_task"] = hass.async_create_task(_refresh_later())


def _should_defer_refresh(hass: HomeAssistant, entry: ConfigEntry, store: dict) -> bool:
    no_read_until = store.get("no_read_until")
    if no_read_until and time.monotonic() < no_read_until:
        return True
    if _is_write_active(store):
        store["write_defer_seconds"] = random.uniform(
            READ_DEFERRAL_JITTER_MIN, READ_DEFERRAL_JITTER_MAX
        )
        return True
    if _cooldown_remaining(hass, entry) > 0:
        return True
    return False


async def async_request_refresh(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    manual: bool = False,
    allow_debounce: bool = True,
) -> bool:
    """Request a refresh, respecting any cooldown."""
    store = _get_entry_store(hass, entry)
    if _should_defer_refresh(hass, entry, store):
        if allow_debounce:
            delay = float(store.pop("write_defer_seconds", 0.0))
            _schedule_debounced_refresh(hass, entry, delay=delay)
        if manual:
            _LOGGER.debug("Manual refresh deferred (cooldown/write active), serving cached")
        return False
    coordinator = store.get("coordinator")
    if coordinator:
        if manual:
            _LOGGER.debug("Manual refresh requested, fetching now")
        await coordinator.async_request_refresh()
        return True
    return False

def _merge_dict(base: dict, update: dict) -> dict:
    merged = dict(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass
class _WriteItem:
    kind: str
    key: str
    target: str
    payload: dict
    futures: list[asyncio.Future] = field(default_factory=list)
    merge_func: Callable[[dict, dict], dict] | None = None
    extra_delay: float = 0.0


class _WriteManager:
    """Serialize and coalesce write operations per config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._pending: dict[str, _WriteItem] = {}
        self._order: list[str] = []
        self._worker_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def enqueue(self, item: _WriteItem) -> None:
        async with self._lock:
            store = _get_entry_store(self._hass, self._entry)
            store["no_read_until"] = time.monotonic() + NO_READ_WINDOW_SECONDS
            existing = self._pending.get(item.key)
            if existing:
                if existing.merge_func:
                    existing.payload = existing.merge_func(
                        existing.payload, item.payload
                    )
                else:
                    existing.payload = item.payload
                existing.extra_delay = max(existing.extra_delay, item.extra_delay)
                existing.futures.extend(item.futures)
            else:
                self._pending[item.key] = item
                self._order.append(item.key)
            if self._worker_task is None or self._worker_task.done():
                self._worker_task = self._hass.async_create_task(self._worker())

    async def _worker(self) -> None:
        while True:
            async with self._lock:
                if not self._order:
                    return
                key = self._order.pop(0)
                item = self._pending.pop(key, None)
            if item is None:
                continue

            cooldown = _cooldown_remaining(self._hass, self._entry)
            if cooldown > 0:
                await asyncio.sleep(cooldown)

            try:
                store = _get_entry_store(self._hass, self._entry)
                store["write_in_flight"] = store.get("write_in_flight", 0) + 1
                await _execute_write(self._hass, self._entry, item)
            except Exception as err:
                for future in item.futures:
                    if not future.done():
                        future.set_exception(err)
            else:
                for future in item.futures:
                    if not future.done():
                        future.set_result(None)
                _set_cooldown(
                    self._hass,
                    self._entry,
                    POST_WRITE_COOLDOWN_SECONDS + item.extra_delay,
                    reason="post_write",
                )
                store = _get_entry_store(self._hass, self._entry)
                store["write_quiet_until"] = time.monotonic() + POST_WRITE_COOLDOWN_SECONDS
                if item.kind == "schedule":
                    _schedule_debounced_refresh(
                        self._hass, self._entry, delay=SCHEDULE_REFRESH_DELAY
                    )
            finally:
                store = _get_entry_store(self._hass, self._entry)
                store["write_in_flight"] = max(
                    0, store.get("write_in_flight", 0) - 1
                )

            await asyncio.sleep(WRITE_GAP_SECONDS)


def _get_write_manager(hass: HomeAssistant, entry: ConfigEntry) -> _WriteManager:
    store = _get_entry_store(hass, entry)
    manager = store.get("write_manager")
    if manager is None:
        manager = _WriteManager(hass, entry)
        store["write_manager"] = manager
    return manager


async def async_update_data(hass: HomeAssistant, entry: ConfigEntry):
    """Fetch data from the Exo Pool API, handling token refresh."""
    global _authentication_failed, _last_auth_error
    _authentication_failed = False  # Reset flag
    _last_auth_error = None
    store = _get_entry_store(hass, entry)
    no_read_until = store.get("no_read_until")
    if no_read_until and time.monotonic() < no_read_until:
        _schedule_debounced_refresh(hass, entry, delay=0.0)
        coordinator = store.get("coordinator")
        return coordinator.data or {}
    if _is_write_active(store):
        _schedule_debounced_refresh(
            hass,
            entry,
            delay=random.uniform(READ_DEFERRAL_JITTER_MIN, READ_DEFERRAL_JITTER_MAX),
        )
        coordinator = store.get("coordinator")
        return coordinator.data or {}
    if _cooldown_remaining(hass, entry) > 0:
        _schedule_debounced_refresh(hass, entry, delay=0.0)
        coordinator = store.get("coordinator")
        return coordinator.data or {}
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
                _LOGGER.debug("Token refresh failed: %s, falling back to full login", e)

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
    await _async_rate_limit(hass, entry)
    async with session.get(
        DATA_URL_TEMPLATE.format(serial_number), headers=headers
    ) as response:
        _LOGGER.debug("Data fetch response status: %s", response.status)
        if response.status != 200:
            error_text = await response.text()
            is_rate_limited = response.status == 429 or "Too Many Requests" in str(
                error_text
            )
            if is_rate_limited:
                _LOGGER.warning("Rate limited fetching device data: %s", error_text)
                coordinator = (
                    hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")
                )
                if coordinator:
                    try:
                        configured = _get_configured_interval_seconds(entry)
                        current = getattr(
                            coordinator,
                            "update_interval",
                            timedelta(seconds=REFRESH_DEFAULT),
                        )
                        cur_s = (
                            int(current.total_seconds()) if current else REFRESH_DEFAULT
                        )
                        if coordinator.data:
                            # Exponential backoff up to REFRESH_MAX
                            new_s = max(cur_s, min(cur_s * 2, REFRESH_MAX))
                            if new_s != cur_s:
                                coordinator.update_interval = timedelta(seconds=new_s)
                                _set_cooldown(
                                    hass,
                                    entry,
                                    new_s,
                                    reason="read_429",
                                )
                                _LOGGER.warning(
                                    "429 Too Many Requests, backing off to %ss",
                                    new_s,
                                )
                            else:
                                _LOGGER.warning(
                                    "429 Too Many Requests, keeping %ss interval",
                                    cur_s,
                                )
                        else:
                            retry_s = max(60, min(configured, REFRESH_MAX))
                            if retry_s != cur_s:
                                coordinator.update_interval = timedelta(seconds=retry_s)
                                _set_cooldown(
                                    hass,
                                    entry,
                                    retry_s,
                                    reason="read_429",
                                )
                                _LOGGER.warning(
                                    "429 Too Many Requests, retrying in %ss",
                                    retry_s,
                                )
                    except Exception as backoff_error:
                        _LOGGER.debug(
                            "Backoff adjustment failed: %s",
                            backoff_error,
                        )
                    backoff_interval = getattr(
                        coordinator,
                        "update_interval",
                        timedelta(seconds=REFRESH_DEFAULT),
                    )
                    _set_cooldown(
                        hass,
                        entry,
                        int(backoff_interval.total_seconds()),
                        reason="read_429",
                    )
                    # Return previous data or empty data to avoid startup failure
                    _LOGGER.debug(
                        "Rate limited, returning cached data to keep coordinator loaded"
                    )
                    return coordinator.data or {}
                return {}

            _LOGGER.error("Failed to fetch device data: %s", error_text)
            if "The incoming token has expired" in error_text:
                _last_auth_error = error_text
            raise UpdateFailed(f"Device data fetch failed: {error_text}")
        data = await response.json()
        _LOGGER.debug("Device data: %s", data)
        reported = data.get("state", {}).get("reported", {})
        coordinator = (
            hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")
        )
        store["last_success_fetch_ts"] = time.monotonic()
        if coordinator:
            configured = _get_configured_interval_seconds(entry)
            current = getattr(
                coordinator,
                "update_interval",
                timedelta(seconds=REFRESH_DEFAULT),
            )
            if (
                current
                and int(current.total_seconds()) > configured
                and "boost_task" not in _get_entry_store(hass, entry)
            ):
                coordinator.update_interval = timedelta(seconds=configured)
                _LOGGER.debug(
                    "Restored polling interval to %ss after successful fetch",
                    configured,
                )
        return reported


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
    await _async_rate_limit(hass, entry)
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
    await _async_rate_limit(hass, entry)
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


def _get_configured_interval_seconds(entry: ConfigEntry) -> int:
    """Return the configured refresh interval in seconds, clamped to limits."""
    seconds = entry.options.get(REFRESH_OPTION_KEY, REFRESH_DEFAULT)
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        seconds = REFRESH_DEFAULT
    return max(REFRESH_MIN, min(REFRESH_MAX, seconds))


def _get_entry_store(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Return the data store for this config entry."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    return hass.data[DOMAIN].setdefault(entry.entry_id, {})


async def _async_boost_refresh_interval(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Temporarily increase polling frequency after a change."""
    store = _get_entry_store(hass, entry)
    coordinator: DataUpdateCoordinator | None = store.get("coordinator")
    if coordinator is None:
        return

    current = coordinator.update_interval
    current_seconds = int(current.total_seconds()) if current else REFRESH_DEFAULT
    if current_seconds > BOOST_INTERVAL:
        coordinator.update_interval = timedelta(seconds=BOOST_INTERVAL)
        _LOGGER.debug(
            "Temporarily increased polling to %ss for %s",
            BOOST_INTERVAL,
            entry.entry_id,
        )

    if task := store.get("boost_task"):
        task.cancel()

    async def _reset_interval() -> None:
        try:
            await asyncio.sleep(BOOST_DURATION)
        except asyncio.CancelledError:
            return
        configured = _get_configured_interval_seconds(entry)
        coordinator.update_interval = timedelta(seconds=configured)
        _LOGGER.debug(
            "Restored polling interval to %ss for %s",
            configured,
            entry.entry_id,
        )
        store.pop("boost_task", None)

    store["boost_task"] = hass.async_create_task(_reset_interval())


def _set_nested_value(target: dict, keys: list[str], value) -> None:
    """Set a nested value in a dict, creating missing dicts as needed."""
    node = target
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    node[keys[-1]] = value


def _build_nested_dict(keys: list[str], value) -> dict:
    nested = value
    for key in reversed(keys):
        nested = {key: nested}
    return nested


def _apply_desired_update(
    coordinator: DataUpdateCoordinator, keys: list[str], value
) -> None:
    """Optimistically update coordinator data with a desired-value change."""
    data = coordinator.data or {}
    _set_nested_value(data, keys, value)
    coordinator.async_set_updated_data(data)


def _apply_heating_update(coordinator: DataUpdateCoordinator, key: str, value) -> None:
    """Optimistically update coordinator data for heating changes."""
    data = coordinator.data or {}
    heating = data.setdefault("heating", {})
    heating[key] = value
    coordinator.async_set_updated_data(data)


def _apply_schedule_update(
    coordinator: DataUpdateCoordinator, schedule_key: str, patch: dict
) -> None:
    """Optimistically update coordinator data for schedule changes."""
    data = coordinator.data or {}
    schedules = data.setdefault("schedules", {})
    schedule = schedules.setdefault(schedule_key, {})
    schedule.update(patch)
    coordinator.async_set_updated_data(data)


async def _execute_write(
    hass: HomeAssistant, entry: ConfigEntry, item: _WriteItem
) -> None:
    serial_number = entry.data["serial_number"]
    id_token = entry.data.get("id_token")
    if not id_token:
        raise Exception(f"No id_token available for write {item.key}")

    if item.kind == "pool":
        payload = {"state": {"desired": {"equipment": {"swc_0": item.payload}}}}
    elif item.kind == "heating":
        payload = {"state": {"desired": {"heating": {item.target: item.payload}}}}
    elif item.kind == "schedule":
        payload = {"state": {"desired": {"schedules": {item.target: item.payload}}}}
    else:
        raise Exception(f"Unknown write kind: {item.kind}")

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "okhttp/3.14.7",
        "Authorization": f"Bearer {id_token}",
    }
    url = DATA_URL_TEMPLATE.format(serial_number)
    _LOGGER.debug(
        "Writing %s at %s with payload: %s",
        item.key,
        url,
        payload,
    )
    session = aiohttp_client.async_get_clientsession(hass)
    await _async_rate_limit(hass, entry)
    async with session.post(url, json=payload, headers=headers) as response:
        response_text = await response.text()
        _LOGGER.debug(
            "Write response for %s: %s %s",
            item.key,
            response.status,
            response_text,
        )
        if response.status == 429:
            _LOGGER.warning("Rate limited during write %s: %s", item.key, response_text)
            _set_cooldown(
                hass,
                entry,
                _get_configured_interval_seconds(entry),
                reason="write_429",
            )
            raise Exception(f"Rate limited for write {item.key}: {response_text}")
        if response.status != 200:
            _LOGGER.error(
                "Write failed for %s: %s (Status: %s)",
                item.key,
                response_text,
                response.status,
            )
            raise Exception(
                f"Write failed for {item.key}: {response_text} (Status: {response.status})"
            )


async def get_coordinator(hass: HomeAssistant, entry: ConfigEntry):
    """Get or create a shared DataUpdateCoordinator for the config entry."""
    store = _get_entry_store(hass, entry)
    if "coordinator" not in store:
        # Initialize refresh interval from entry options (clamped)
        seconds = _get_configured_interval_seconds(entry)
        coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name="Exo Pool",
            update_method=lambda: async_update_data(hass, entry),
            # Poll at a moderate interval to reduce cloud load
            update_interval=timedelta(seconds=seconds),
        )
        store["coordinator"] = coordinator
        # Perform initial refresh
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception as e:
            _LOGGER.error("Initial data fetch failed: %s", e)
            raise
    return store["coordinator"]


async def async_set_refresh_interval(
    hass: HomeAssistant, entry: ConfigEntry, seconds: int
):
    """Update the refresh interval for the coordinator and persist to options."""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        seconds = REFRESH_DEFAULT
    seconds = max(REFRESH_MIN, min(REFRESH_MAX, seconds))

    store = _get_entry_store(hass, entry)
    coordinator: DataUpdateCoordinator = store["coordinator"]
    if "boost_task" not in store:
        coordinator.update_interval = timedelta(seconds=seconds)
    _LOGGER.debug("Set refresh interval to %ss for %s", seconds, entry.entry_id)

    # Persist to entry options
    new_options = dict(entry.options)
    new_options[REFRESH_OPTION_KEY] = seconds
    hass.config_entries.async_update_entry(entry, options=new_options)


async def set_pool_value(hass, entry, setting, value, delay_refresh=False):
    """Set a pool setting value via the API."""
    id_token = entry.data.get("id_token")
    if not id_token:
        _LOGGER.error("No id_token available for setting %s", setting)
        return

    keys = setting.split(".")
    nested_value = _build_nested_dict(keys, value)
    coordinator = _get_entry_store(hass, entry).get("coordinator")
    if coordinator:
        _apply_desired_update(coordinator, ["equipment", "swc_0"] + keys, value)

    future = asyncio.get_running_loop().create_future()
    item = _WriteItem(
        kind="pool",
        key=f"pool:{setting}",
        target=setting,
        payload=nested_value,
        futures=[future],
        extra_delay=10.0 if delay_refresh else 0.0,
    )
    await _get_write_manager(hass, entry).enqueue(item)
    await future


async def set_heating_value(hass, entry, key: str, value, delay_refresh: bool = False):
    """Set a top-level heating value via the API (e.g., sp)."""
    id_token = entry.data.get("id_token")
    if not id_token:
        _LOGGER.error("No id_token available for heating.%s", key)
        return
    coordinator = _get_entry_store(hass, entry).get("coordinator")
    if coordinator:
        _apply_heating_update(coordinator, key, value)

    future = asyncio.get_running_loop().create_future()
    item = _WriteItem(
        kind="heating",
        key=f"heating:{key}",
        target=key,
        payload=value,
        futures=[future],
        extra_delay=10.0 if delay_refresh else 0.0,
    )
    await _get_write_manager(hass, entry).enqueue(item)
    await future


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
    if not sched_patch:
        _LOGGER.debug("No schedule updates provided for %s", schedule_key)
        return

    coordinator = _get_entry_store(hass, entry).get("coordinator")
    if coordinator:
        _apply_schedule_update(coordinator, schedule_key, sched_patch)

    future = asyncio.get_running_loop().create_future()
    item = _WriteItem(
        kind="schedule",
        key=f"schedule:{schedule_key}",
        target=schedule_key,
        payload=sched_patch,
        futures=[future],
        merge_func=_merge_dict,
    )
    await _get_write_manager(hass, entry).enqueue(item)
    await future
