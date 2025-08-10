from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.core import HomeAssistant
import logging
from .const import DOMAIN
from .api import get_coordinator
from homeassistant.helpers.device_registry import DeviceRegistry, async_get
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

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

    # Forward setup to sensor, binary_sensor, switch, and number platforms
    try:
        await hass.config_entries.async_forward_entry_setups(
            entry, ["sensor", "binary_sensor", "switch", "number"]
        )
    except Exception as e:
        _LOGGER.error("Failed to set up platforms: %s", e)
        raise ConfigEntryNotReady("Failed to initialize Exo Pool platforms") from e
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        result = await hass.config_entries.async_unload_platforms(
            entry, ["sensor", "binary_sensor", "switch", "number"]
        )
        if result and entry.entry_id in hass.data[DOMAIN]:
            del hass.data[DOMAIN][entry.entry_id]
        _LOGGER.debug("Unloaded platforms for entry: %s", entry.entry_id)
        return result
    except Exception as e:
        _LOGGER.error("Failed to unload platforms: %s", e)
        return False
