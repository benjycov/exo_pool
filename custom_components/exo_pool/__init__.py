from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.core import HomeAssistant
import logging
import asyncio
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
    await _update_device_info(
        hass, entry, coordinator, device_registry, device_entry.id
    )

    # Store task reference to manage it
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "update_task": None,
    }

    # Start the periodic update task
    update_task = hass.async_create_task(
        _async_start_periodic_updates(
            hass, entry, coordinator, device_registry, device_entry.id
        )
    )
    hass.data[DOMAIN][entry.entry_id]["update_task"] = update_task

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
        # Cancel the periodic update task if it exists
        if (
            entry.entry_id in hass.data.get(DOMAIN, {})
            and "update_task" in hass.data[DOMAIN][entry.entry_id]
        ):
            task = hass.data[DOMAIN][entry.entry_id]["update_task"]
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    _LOGGER.debug(
                        "Periodic update task cancelled for entry: %s", entry.entry_id
                    )

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


async def _update_device_info(
    hass,
    entry,
    coordinator: DataUpdateCoordinator,
    device_registry: DeviceRegistry,
    device_id: str,
):
    """Update device info with capabilities and serial number."""
    if coordinator.data is None:
        _LOGGER.warning("Coordinator data is None, skipping device info update")
        return

    serial_number = coordinator.data.get("equipment", {}).get("swc_0", {}).get("sn")
    sw_version = coordinator.data.get("debug", {}).get("Version Firmware")

    device_registry.async_update_device(
        device_id,
        manufacturer="Zodiac",
        sw_version=sw_version,
        serial_number=serial_number,
    )
    _LOGGER.debug(
        "Updated device info: serial_number=%s, sw_version=%s",
        serial_number,
        sw_version,
    )


async def _async_start_periodic_updates(
    hass,
    entry,
    coordinator: DataUpdateCoordinator,
    device_registry: DeviceRegistry,
    device_id: str,
):
    """Start periodic updates for device info."""
    while True:
        await _update_device_info(hass, entry, coordinator, device_registry, device_id)
        await asyncio.sleep(60)  # Update every minute
