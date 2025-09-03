from __future__ import annotations

import datetime as dt
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_DEVICE_ID, CONF_TYPE
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

# Action types
ACTION_SET_SCHEDULE = "set_schedule"
ACTION_DISABLE_SCHEDULE = "disable_schedule"

ACTION_TYPES: set[str] = {ACTION_SET_SCHEDULE, ACTION_DISABLE_SCHEDULE}


def _device_is_exo(hass: HomeAssistant, device_id: str) -> bool:
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get(device_id)
    if not device:
        return False
    return any(domain == DOMAIN for domain, _ in device.identifiers)


async def async_get_actions(hass: HomeAssistant, device_id: str) -> list[ConfigType]:
    if not _device_is_exo(hass, device_id):
        return []
    return [
        {"domain": DOMAIN, CONF_DEVICE_ID: device_id, CONF_TYPE: ACTION_SET_SCHEDULE},
        {"domain": DOMAIN, CONF_DEVICE_ID: device_id, CONF_TYPE: ACTION_DISABLE_SCHEDULE},
    ]


async def async_call_action(
    hass: HomeAssistant, action: ConfigType, variables: dict, context
) -> None:
    action_type: str = action[CONF_TYPE]
    device_id: str = action[CONF_DEVICE_ID]

    if action_type == ACTION_SET_SCHEDULE:
        schedule = action.get("schedule")
        start = action.get("start")
        end = action.get("end")
        rpm = action.get("rpm")

        def fmt(t):
            if t is None:
                return None
            if isinstance(t, dt.time):
                return t.strftime("%H:%M")
            if isinstance(t, str):
                return t[:5]
            return None

        data = {
            "device_id": device_id,
            "schedule": schedule,
        }
        if (s := fmt(start)) is not None:
            data["start"] = s
        if (e := fmt(end)) is not None:
            data["end"] = e
        if rpm is not None:
            data["rpm"] = rpm

        await hass.services.async_call(DOMAIN, "set_schedule", data, context=context)
        return

    if action_type == ACTION_DISABLE_SCHEDULE:
        schedule = action.get("schedule")
        data = {"device_id": device_id, "schedule": schedule}
        await hass.services.async_call(
            DOMAIN, "disable_schedule", data, context=context
        )
        return


async def async_get_action_capabilities(
    hass: HomeAssistant, action: ConfigType
) -> dict[str, vol.Schema]:
    action_type: str = action[CONF_TYPE]
    if action_type == ACTION_SET_SCHEDULE:
        return {
            "extra_fields": vol.Schema(
                {
                    vol.Required("schedule"): cv.string,
                    vol.Optional("start"): cv.time,
                    vol.Optional("end"): cv.time,
                    vol.Optional("rpm"): vol.Coerce(int),
                }
            )
        }
    if action_type == ACTION_DISABLE_SCHEDULE:
        return {
            "extra_fields": vol.Schema({vol.Required("schedule"): cv.string})
        }
    return {"extra_fields": vol.Schema({})}

