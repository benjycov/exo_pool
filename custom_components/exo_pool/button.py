from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
import logging
from homeassistant.const import EntityCategory

from .api import get_coordinator, async_request_refresh
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the button platform for Exo Pool."""
    coordinator = await get_coordinator(hass, entry)
    async_add_entities([ExoPoolRefreshButton(entry, coordinator)])


class ExoPoolRefreshButton(CoordinatorEntity, ButtonEntity):
    """Button to force a data refresh."""

    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Refresh data"
        self._attr_unique_id = f"{entry.entry_id}_refresh_data"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        refreshed = await async_request_refresh(self.hass, self._entry, manual=True)
        if refreshed:
            _LOGGER.debug("Manual refresh completed")
