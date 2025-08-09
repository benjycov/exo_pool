from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.core import HomeAssistant
import logging
from .const import DOMAIN
from .api import get_coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Exo Pool from a config entry."""
    _LOGGER.debug("Setting up Exo Pool: %s", entry.data)
    hass.data.setdefault(DOMAIN, {})

    # Initialize shared coordinator
    try:
        await get_coordinator(hass, entry)
    except Exception as e:
        _LOGGER.error("Initial coordinator setup failed: %s", e)
        raise ConfigEntryNotReady("Failed to initialize Exo Pool coordinator") from e

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
