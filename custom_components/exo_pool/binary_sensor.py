from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
import logging
from .api import (
    get_coordinator,
    ERROR_CODES,
    _authentication_failed,
    _last_auth_error,
    DOMAIN,
)
from homeassistant.const import EntityCategory

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the binary sensor platform for Exo Pool."""
    # Retrieve shared coordinator
    coordinator = await get_coordinator(hass, entry)

    # Add binary sensors
    entities = [
        FilterPumpBinarySensor(entry, coordinator),
        ErrorStateBinarySensor(entry, coordinator),
        SaltWaterChlorinatorBinarySensor(entry, coordinator),
        AuthenticationStatusBinarySensor(entry, coordinator),
        ConnectedBinarySensor(entry, coordinator),
    ]

    # Add a binary sensor per schedule item
    created_schedule_keys: set[str] = set()
    schedules = coordinator.data.get("schedules", {}) if coordinator.data else {}

    def _iter_schedule_items(schedules_dict):
        for key, sched in schedules_dict.items():
            if not isinstance(sched, dict):
                continue
            # Filter out meta keys like supported/programmed
            if key in {"supported", "programmed"}:
                continue
            # Must have at least an id or endpoint to be meaningful
            if not (sched.get("id") or sched.get("endpoint")):
                continue
            yield key, sched

    for key, sched in _iter_schedule_items(schedules):
        created_schedule_keys.add(key)
        entities.append(ScheduleBinarySensor(entry, coordinator, key))

    async_add_entities(entities)

    # Discover any new schedules that appear after initial setup
    def _check_new_schedules():
        new_entities: list[BinarySensorEntity] = []
        current = coordinator.data.get("schedules", {}) if coordinator.data else {}
        for key, sched in _iter_schedule_items(current):
            if key in created_schedule_keys:
                continue
            created_schedule_keys.add(key)
            new_entities.append(ScheduleBinarySensor(entry, coordinator, key))
        if new_entities:
            _LOGGER.debug("Discovered %s new schedules", len(new_entities))
            async_add_entities(new_entities)

    coordinator.async_add_listener(_check_new_schedules)


# Binary Sensor Classes
class FilterPumpBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a filter pump binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:pump"

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Filter Pump"
        self._attr_unique_id = f"{entry.entry_id}_filter_pump"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def is_on(self):
        return bool(
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("filter_pump", {})
            .get("state")
        )

    @property
    def extra_state_attributes(self):
        """Provide additional filter pump attributes."""
        schedules = self.coordinator.data.get("schedules", {})
        for key, value in schedules.items():
            if (
                isinstance(value, dict)
                and value.get("endpoint")
                and "vsp" in value.get("endpoint")
                and value.get("enabled") == 1
                and value.get("active") == 1
            ):
                return {"speed_rpm": value.get("rpm")}
        return {"speed_rpm": 0}  # Default to 0 if no active VSP schedule

    @property
    def available(self):
        """Return availability based on data fetch success."""
        return self.coordinator.data is not None


class ErrorStateBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an error state binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Error State"
        self._attr_unique_id = f"{entry.entry_id}_error_state"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def is_on(self):
        return bool(
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("error_state")
        )

    @property
    def extra_state_attributes(self):
        """Provide error code and message as attributes."""
        code = (
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("error_code")
        )
        return {
            "error_code": code,
            "error_message": ERROR_CODES.get(
                int(code) if code is not None else 0, "Unknown Error"
            ),
        }

    @property
    def available(self):
        """Return availability based on data fetch success."""
        return self.coordinator.data is not None


class SaltWaterChlorinatorBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a salt water chlorinator binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:water-plus"

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Salt Water Chlorinator"
        self._attr_unique_id = f"{entry.entry_id}_salt_water_chlorinator"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def is_on(self):
        return bool(
            self.coordinator.data.get("equipment", {})
            .get("swc_0", {})
            .get("production")
        )

    @property
    def available(self):
        """Return availability based on data fetch success."""
        return self.coordinator.data is not None


class AuthenticationStatusBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an authentication status binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:lock-check"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Authentication Status"
        self._attr_unique_id = f"{entry.entry_id}_authentication_status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def is_on(self):
        """Return true if authentication is successful."""
        return not _authentication_failed

    @property
    def extra_state_attributes(self):
        """Provide additional details about authentication status."""
        return {"last_error": _last_auth_error} if _authentication_failed else {}

    @property
    def available(self):
        """Return availability based on data fetch success."""
        return self.coordinator.data is not None


class ConnectedBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a connected binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:signal"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Connected"
        self._attr_unique_id = f"{entry.entry_id}_connected"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def is_on(self):
        return self.coordinator.data is not None and bool(self.coordinator.data)

    @property
    def available(self):
        """Return availability based on data fetch success."""
        _LOGGER.debug(
            "Connected sensor availability check: coordinator.data=%s",
            self.coordinator.data is not None,
        )
        return self.coordinator.data is not None


class ScheduleBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor representing a single schedule's active state."""

    def __init__(self, entry, coordinator, schedule_key: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._schedule_key = schedule_key
        sched = self._schedule
        name = (sched or {}).get("name") or (sched or {}).get("id") or schedule_key
        self._attr_name = f"Schedule: {name}"
        self._attr_unique_id = f"{entry.entry_id}_schedule_{schedule_key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Exo Pool",
            "manufacturer": "Zodiac",
            "model": "Exo",
        }

    @property
    def _schedule(self):
        scheds = self.coordinator.data.get("schedules", {}) if self.coordinator.data else {}
        return scheds.get(self._schedule_key)

    @staticmethod
    def _endpoint_type(endpoint: str | None) -> str | None:
        if not endpoint:
            return None
        e = endpoint.lower()
        if e.startswith("vsp"):
            return "vsp"
        if e.startswith("aux"):
            return "aux"
        if e.startswith("swc"):
            return "swc"
        return e

    @property
    def is_on(self) -> bool | None:
        sched = self._schedule
        if not isinstance(sched, dict):
            return None
        return bool(sched.get("active", 0))

    @property
    def available(self) -> bool:
        return isinstance(self._schedule, dict)

    @property
    def extra_state_attributes(self):
        sched = self._schedule or {}
        timer = sched.get("timer", {}) or {}
        endpoint = sched.get("endpoint")
        typ = self._endpoint_type(endpoint)
        attrs = {
            "schedule": self._schedule_key,
            "enabled": bool(sched.get("enabled", 0)),
            "start_time": timer.get("start"),
            "end_time": timer.get("end"),
            "type": typ,
        }
        if typ == "vsp" and "rpm" in sched:
            attrs["rpm"] = sched.get("rpm")
        return attrs

    @property
    def icon(self) -> str | None:
        """Return an icon representing the schedule type and state."""
        typ = self._endpoint_type((self._schedule or {}).get("endpoint"))
        on = bool(self.is_on)
        if typ == "vsp":
            return "mdi:pump" if on else "mdi:pump-off"
        if typ == "swc":
            return "mdi:water-plus" if on else "mdi:water-off"
        if typ == "aux":
            return "mdi:toggle-switch" if on else "mdi:toggle-switch-off-outline"
        # Fallback to calendar icons for unknown types
        return "mdi:calendar-check" if on else "mdi:calendar-remove"
