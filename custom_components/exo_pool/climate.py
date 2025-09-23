from __future__ import annotations

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVACAction,
    HVACMode,
    ClimateEntityFeature,
)
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import get_coordinator, DOMAIN, set_heating_value, set_pool_value

import logging

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up climate entity for Exo Pool heat pump (Aux 2 mode heat)."""
    coordinator = await get_coordinator(hass, entry)
    created = False

    def _should_create() -> bool:
        data = coordinator.data or {}
        swc = data.get("equipment", {}).get("swc_0", {})
        aux2 = swc.get("aux_2", {})
        return aux2.get("mode") == 3

    # Create immediately if present
    if _should_create():
        async_add_entities([ExoHeatPumpClimate(entry, coordinator)])
        created = True
    else:
        _LOGGER.debug("Aux 2 not in heat mode; climate entity will be created when detected")

    # Discover creation later if aux_2 switches to heat mode
    def _maybe_create_later():
        nonlocal created
        if created:
            return
        if _should_create():
            async_add_entities([ExoHeatPumpClimate(entry, coordinator)])
            created = True

    coordinator.async_add_listener(_maybe_create_later)


class ExoHeatPumpClimate(CoordinatorEntity, ClimateEntity):
    """Heat Pump climate entity backed by top-level 'heating' data."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:heat-pump"

    def __init__(self, entry: ConfigEntry, coordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Heat Pump"
        self._attr_unique_id = f"{entry.entry_id}_heat_pump"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    # Availability follows Aux 2 remaining in heat mode
    @property
    def available(self) -> bool:
        data = self.coordinator.data or {}
        swc = data.get("equipment", {}).get("swc_0", {})
        aux2 = swc.get("aux_2", {})
        return aux2.get("mode") == 3 and (data.get("heating") is not None)

    @property
    def temperature_unit(self) -> str:
        return UnitOfTemperature.CELSIUS

    @property
    def current_temperature(self) -> float | None:
        # Water temperature (sns_3.value) if present
        return (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("sns_3", {})
            .get("value")
        )

    @property
    def target_temperature(self) -> float | None:
        heating = (self.coordinator.data or {}).get("heating", {})
        return heating.get("sp")

    @property
    def min_temp(self) -> float:
        heating = (self.coordinator.data or {}).get("heating", {})
        return float(heating.get("sp_min", 10))

    @property
    def max_temp(self) -> float:
        heating = (self.coordinator.data or {}).get("heating", {})
        return float(heating.get("sp_max", 40))

    @property
    def hvac_mode(self) -> HVACMode:
        data = self.coordinator.data or {}
        swc = data.get("equipment", {}).get("swc_0", {})
        aux2 = swc.get("aux_2", {})
        return HVACMode.HEAT if aux2.get("state") == 1 else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        # Prefer aux_2.state for run indicator; fall back to heating.state mapping
        data = self.coordinator.data or {}
        swc = data.get("equipment", {}).get("swc_0", {})
        aux2 = swc.get("aux_2", {})
        if aux2.get("state") == 1:
            return HVACAction.HEATING
        state = (data.get("heating", {}) or {}).get("state")
        return HVACAction.HEATING if state == 2 else HVACAction.IDLE

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        heating = data.get("heating", {}) or {}
        swc = data.get("equipment", {}).get("swc_0", {})
        aux2 = swc.get("aux_2", {})
        # Expose all other heating fields as attributes for visibility
        attrs: dict = {
            "aux2_mode": aux2.get("mode"),
            "aux2_type": aux2.get("type"),
            "aux2_state": aux2.get("state"),
            "heating_state_raw": heating.get("state"),
            "enabled": heating.get("enabled"),
            "sp_min": heating.get("sp_min"),
            "sp_max": heating.get("sp_max"),
            "vsp_rpm_index": heating.get("vsp_rpm_index"),
            "vsp_rpm_list": heating.get("vsp_rpm_list"),
            "priority_enabled": heating.get("priority_enabled"),
        }
        return attrs

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        # Clamp to reported range if available
        min_t = self.min_temp
        max_t = self.max_temp
        try:
            value = int(round(float(temp)))
        except (TypeError, ValueError):
            _LOGGER.debug("Invalid temperature value: %s", temp)
            return
        value = max(int(min_t), min(int(max_t), value))
        await set_heating_value(self.hass, self._entry, "sp", value)
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.HEAT:
            await set_pool_value(self.hass, self._entry, "aux_2.state", 1)
        elif hvac_mode == HVACMode.OFF:
            await set_pool_value(self.hass, self._entry, "aux_2.state", 0)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
