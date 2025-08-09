from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.core import HomeAssistant
import logging
import aiohttp
from .const import DOMAIN
from .sensor import async_update_data  # Import to reuse authentication logic

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Exo Pool from a config entry."""
    _LOGGER.debug("Setting up Exo Pool: %s", entry.data)
    hass.data.setdefault(DOMAIN, {})

    # Perform initial authentication to ensure a valid token
    try:
        session = aiohttp.ClientSession()
        data = await async_update_data(
            hass, entry, session
        )  # Reuse sensor's update logic
        await session.close()
    except Exception as e:
        _LOGGER.error("Initial authentication failed: %s", e)
        raise ConfigEntryNotReady("Failed to authenticate Exo Pool") from e

    try:
        await hass.config_entries.async_forward_entry_setups(
            entry, ["sensor", "switch"]
        )
    except Exception as e:
        _LOGGER.error("Failed to set up platforms: %s", e)
        raise ConfigEntryNotReady("Failed to initialize Exo Pool platforms") from e
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        result = await hass.config_entries.async_unload_platforms(
            entry, ["sensor", "switch"]
        )
        _LOGGER.debug("Unloaded platforms for entry: %s", entry.entry_id)
        return result
    except Exception as e:
        _LOGGER.error("Failed to unload platforms: %s", e)
        return False
