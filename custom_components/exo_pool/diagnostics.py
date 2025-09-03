from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

REDACT_FIELDS: set[str] = {
    "email",
    "password",
    "auth_token",
    "id_token",
    "refresh_token",
    "user_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
):
    """Return diagnostics for a config entry with sensitive fields redacted."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")
    diag = {
        "config_entry": {
            "title": entry.title,
            "unique_id": entry.unique_id,
            "data": dict(entry.data),
        },
        "coordinator": {
            "last_update_success": getattr(coordinator, "last_update_success", None),
            "last_exception": str(getattr(coordinator, "last_exception", ""))
            if getattr(coordinator, "last_exception", None)
            else None,
            "data": getattr(coordinator, "data", None),
        },
    }
    return async_redact_data(diag, REDACT_FIELDS)

