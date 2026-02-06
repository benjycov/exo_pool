from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryNotReady,
    ConfigEntryState,
)
from homeassistant.core import HomeAssistant, ServiceCall
import logging
from .const import DOMAIN
from .api import get_coordinator
from . import api as exo_api
from homeassistant.helpers.device_registry import DeviceRegistry, async_get
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import voluptuous as vol
import re

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Exo Pool from a config entry."""
    _LOGGER.debug("Setting up Exo Pool: %s", entry.data)
    hass.data.setdefault(DOMAIN, {})

    # Initialize shared coordinator
    try:
        coordinator = await get_coordinator(hass, entry)
    except Exception as e:
        _LOGGER.error("Initial coordinator setup failed: %s", e)
        raise ConfigEntryNotReady("Failed to initialize Exo Pool coordinator") from e

    # Register or update device in device registry
    device_registry = async_get(hass)  # Synchronous call
    device_entry = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="Zodiac",
        name="Exo Pool",
        model="Exo",
    )

    # Add listener to update device info on coordinator refresh
    def _update_on_refresh():
        if coordinator.data is None:
            _LOGGER.warning("Coordinator data is None, skipping device info update")
            return

        serial_number = coordinator.data.get("equipment", {}).get("swc_0", {}).get("sn")
        sw_version = coordinator.data.get("debug", {}).get("Version Firmware")

        device_registry.async_update_device(
            device_entry.id,
            sw_version=sw_version,
            serial_number=serial_number,
        )
        _LOGGER.debug(
            "Updated device info: serial_number=%s, sw_version=%s",
            serial_number,
            sw_version,
        )

    coordinator.async_add_listener(_update_on_refresh)

    # Initial update
    _update_on_refresh()

    # Forward setup to sensor, binary_sensor, switch, number, button, and climate platforms
    try:
        await hass.config_entries.async_forward_entry_setups(
            entry, ["sensor", "binary_sensor", "switch", "number", "button", "climate"]
        )
    except Exception as e:
        _LOGGER.error("Failed to set up platforms: %s", e)
        raise ConfigEntryNotReady("Failed to initialize Exo Pool platforms") from e

    # Register services once per hass instance
    domain_data = hass.data[DOMAIN]
    if not domain_data.get("services_registered"):
        _register_services(hass)
        domain_data["services_registered"] = True
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        result = await hass.config_entries.async_unload_platforms(
            entry, ["sensor", "binary_sensor", "switch", "number", "button", "climate"]
        )
        if result and entry.entry_id in hass.data[DOMAIN]:
            del hass.data[DOMAIN][entry.entry_id]
        _LOGGER.debug("Unloaded platforms for entry: %s", entry.entry_id)
        return result
    except Exception as e:
        _LOGGER.error("Failed to unload platforms: %s", e)
        return False


# -----------------------
# Services registration
# -----------------------

TIME_RE = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")


def _normalize_time(val: str | None) -> str | None:
    if val is None:
        return None
    if not isinstance(val, str) or not TIME_RE.match(val):
        raise HomeAssistantError("Invalid time format; expected HH:MM or HH:MM:SS")
    # Truncate to HH:MM
    return val[0:5]


def _coerce_device_id(device_id_value) -> str:
    """Normalize device_id from service target which may be a list."""
    if isinstance(device_id_value, list):
        if not device_id_value:
            raise HomeAssistantError("No device selected")
        if len(device_id_value) > 1:
            raise HomeAssistantError("Select a single device")
        return device_id_value[0]
    if isinstance(device_id_value, str):
        return device_id_value
    raise HomeAssistantError("Invalid device target")


def _find_entry_from_device(hass: HomeAssistant, device_id) -> ConfigEntry:
    device_id = _coerce_device_id(device_id)
    device_registry = async_get(hass)
    device = device_registry.async_get(device_id)
    if not device:
        raise HomeAssistantError("Device not found")
    for domain, entry_id in device.identifiers:
        if domain == DOMAIN:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry:
                return entry
    raise HomeAssistantError("Device is not an Exo Pool device")


def _parse_schedule_from_entity_unique_id(unique_id: str | None) -> str | None:
    if not unique_id:
        return None
    marker = "_schedule_"
    if marker in unique_id:
        return unique_id.split(marker, 1)[1]
    return None


def _coerce_entity_id(entity_id_value) -> str:
    if isinstance(entity_id_value, list):
        if not entity_id_value:
            raise HomeAssistantError("No entity selected")
        if len(entity_id_value) > 1:
            raise HomeAssistantError("Select a single entity")
        return entity_id_value[0]
    if isinstance(entity_id_value, str):
        return entity_id_value
    raise HomeAssistantError("Invalid entity target")


def _resolve_target(hass: HomeAssistant, call: ServiceCall) -> tuple[ConfigEntry, str | None]:
    """Resolve service call target to (entry, schedule_key or None)."""
    entity_id = call.data.get("entity_id")
    schedule_key = call.data.get("schedule")
    if entity_id:
        entity_id = _coerce_entity_id(entity_id)
        ent_reg = er.async_get(hass)
        ent = ent_reg.async_get(entity_id)
        if not ent:
            raise HomeAssistantError("Entity not found")
        # Find config entry via device
        entry = _find_entry_from_device(hass, ent.device_id)
        # Derive schedule from unique_id if not provided
        if not schedule_key:
            schedule_key = _parse_schedule_from_entity_unique_id(ent.unique_id)
        return entry, schedule_key
    # Fallback to device targeting
    device_id = call.data.get("device_id")
    if device_id:
        entry = _find_entry_from_device(hass, device_id)
        return entry, schedule_key
    raise HomeAssistantError("Select a Schedule entity or the Exo device")


def _register_services(hass: HomeAssistant) -> None:
    async def handle_reload(call: ServiceCall) -> None:
        entry_id = call.data.get("entry_id")
        if entry_id:
            entry = hass.config_entries.async_get_entry(entry_id)
            if not entry:
                raise ServiceValidationError("Config entry not found")
        else:
            device_id = call.data.get("device_id")
            if device_id:
                entry = _find_entry_from_device(hass, device_id)
            else:
                entries = hass.config_entries.async_entries(DOMAIN)
                if len(entries) != 1:
                    raise ServiceValidationError(
                        "Select a device or config entry"
                    )
                entry = entries[0]

        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError("Config entry is not loaded")

        await hass.config_entries.async_reload(entry.entry_id)

    async def handle_set_schedule(call: ServiceCall) -> None:
        entry, schedule_key = _resolve_target(hass, call)
        start = _normalize_time(call.data.get("start"))
        end = _normalize_time(call.data.get("end"))
        rpm = call.data.get("rpm")

        if not schedule_key:
            raise HomeAssistantError("Missing schedule key; select a schedule entity or provide schedule")
        coordinator: DataUpdateCoordinator = await get_coordinator(hass, entry)
        schedules = (coordinator.data or {}).get("schedules", {})
        if schedule_key not in schedules:
            raise HomeAssistantError(f"Unknown schedule: {schedule_key}")

        # If type is not VSP, ignore rpm
        endpoint = (schedules.get(schedule_key) or {}).get("endpoint", "")
        if not str(endpoint).lower().startswith("vsp"):
            rpm = None

        await exo_api.update_schedule(hass, entry, schedule_key, start=start, end=end, rpm=rpm)

    async def handle_disable_schedule(call: ServiceCall) -> None:
        entry, schedule_key = _resolve_target(hass, call)
        if not schedule_key:
            raise HomeAssistantError("Missing schedule key; select a schedule entity or provide schedule")
        await exo_api.update_schedule(hass, entry, schedule_key, start="00:00", end="00:00", rpm=None)

    hass.services.async_register(DOMAIN, "reload", handle_reload)
    hass.services.async_register(DOMAIN, "set_schedule", handle_set_schedule)
    hass.services.async_register(DOMAIN, "disable_schedule", handle_disable_schedule)
