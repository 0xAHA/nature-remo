"""Config flow for Nature Remo integration."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.config_entries import ConfigEntryState

from . import NatureRemoAPI
from .const import (
    DOMAIN,
    _CONF_UPDATE_INTERVAL,
    _DEFAULT_UPDATE_INTERVAL,
    UPDATE_INTERVAL_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)

def log_debug(msg, *args, **kwargs):
    """Log debug message with Nature_Remo prefix."""
    _LOGGER.debug(f"Nature_Remo Config Flow: {msg}", *args, **kwargs)

class NatureRemoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nature Remo."""

    VERSION = 2  # Increment version to trigger migration

    @staticmethod
    async def async_migrate_entry(hass: HomeAssistant, entry: config_entries.ConfigEntry) -> bool:
        """Migrate old entry."""
        log_debug("Starting migration for entry %s (version %s, state %s)", 
                 entry.entry_id, entry.version, entry.state)
        log_debug("Current entry data: %s", entry.data)

        try:
            if entry.version == 1:
                log_debug("Migrating from version 1 to 2")
                # Version 1 to 2: Add update interval
                new_data = {**entry.data, _CONF_UPDATE_INTERVAL: _DEFAULT_UPDATE_INTERVAL.seconds}
                log_debug("New data will be: %s", new_data)
                
                # Update the entry
                hass.config_entries.async_update_entry(
                    entry,
                    data=new_data,
                    version=2,
                    state=ConfigEntryState.NOT_LOADED  # Reset state to allow reload
                )
                log_debug("Migration to version 2 successful")
                return True

            log_debug("No migration needed for version %s", entry.version)
            return False
        except Exception as err:
            log_debug("Error during migration: %s", err, exc_info=True)
            # If migration fails, we need to mark the entry as failed
            try:
                hass.config_entries.async_update_entry(
                    entry,
                    state=ConfigEntryState.SETUP_ERROR,
                )
                log_debug("Marked entry as SETUP_ERROR")
            except Exception as update_err:
                log_debug("Failed to update entry state: %s", update_err, exc_info=True)
            return False

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        log_debug("Starting user step with input: %s", user_input)
        errors = {}

        # Check if already configured
        current_entries = self._async_current_entries()
        log_debug("Current entries: %s", [(e.entry_id, e.version, e.state) for e in current_entries])

        if current_entries:
            # If we have an entry in MIGRATION_ERROR state, we need to handle it
            for entry in current_entries:
                log_debug("Checking entry %s (state: %s)", entry.entry_id, entry.state)
                if entry.state in (ConfigEntryState.MIGRATION_ERROR, ConfigEntryState.SETUP_ERROR):
                    log_debug("Found entry in error state, removing: %s", entry.entry_id)
                    try:
                        await self.hass.config_entries.async_remove(entry.entry_id)
                        log_debug("Successfully removed entry %s", entry.entry_id)
                    except Exception as err:
                        log_debug("Error removing entry: %s", err, exc_info=True)
                    break
            else:
                log_debug("No entries in error state, aborting as already configured")
                return self.async_abort(reason="already_configured")

        if user_input is not None:
            log_debug("Processing user input")
            try:
                await self._validate_token(user_input[CONF_ACCESS_TOKEN])
                log_debug("Token validation successful")
                return self.async_create_entry(
                    title="Nature Remo",
                    data={
                        CONF_ACCESS_TOKEN: user_input[CONF_ACCESS_TOKEN],
                        _CONF_UPDATE_INTERVAL: user_input[_CONF_UPDATE_INTERVAL],
                    },
                )
            except InvalidAuth:
                log_debug("Invalid authentication")
                errors["base"] = "invalid_auth"
            except Exception as err:  # pylint: disable=broad-except
                log_debug("Unexpected exception: %s", err, exc_info=True)
                errors["base"] = "unknown"

        log_debug("Showing form with errors: %s", errors)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ACCESS_TOKEN): str,
                vol.Required(_CONF_UPDATE_INTERVAL, default=_DEFAULT_UPDATE_INTERVAL.seconds): vol.In(UPDATE_INTERVAL_OPTIONS),
            }),
            errors=errors,
            description_placeholders={
                "url": "https://home.nature.global",
                "min_interval": str(min(UPDATE_INTERVAL_OPTIONS)),
                "max_interval": str(max(UPDATE_INTERVAL_OPTIONS)),
            }
        )

    async def async_step_import(self, import_info) -> FlowResult:
        """Handle import from configuration.yaml."""
        # Check if already configured
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        # Extract just the access token from the YAML config
        access_token = import_info.get(CONF_ACCESS_TOKEN)
        if not access_token:
            return self.async_abort(reason="invalid_yaml_config")
            
        try:
            await self._validate_token(access_token)
            return self.async_create_entry(
                title="Nature Remo",
                data={
                    CONF_ACCESS_TOKEN: access_token,
                    _CONF_UPDATE_INTERVAL: _DEFAULT_UPDATE_INTERVAL.seconds,
                },
            )
        except InvalidAuth:
            return self.async_abort(reason="invalid_auth")
        except Exception:  # pylint: disable=broad-except
            log_debug("Unexpected exception", exc_info=True)
            return self.async_abort(reason="unknown")

    async def async_step_reconfigure(self, user_input=None) -> FlowResult:
        """Handle reconfiguration."""
        log_debug("Starting reconfigure step with input: %s", user_input)
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if not entry:
            log_debug("Entry not found for reconfigure")
            return self.async_abort(reason="not_found")

        log_debug("Found entry %s (state: %s)", entry.entry_id, entry.state)

        # If the entry is in error state, we need to remove it first
        if entry.state in (ConfigEntryState.MIGRATION_ERROR, ConfigEntryState.SETUP_ERROR):
            log_debug("Entry in error state, removing and starting fresh")
            try:
                await self.hass.config_entries.async_remove(entry.entry_id)
                log_debug("Successfully removed entry %s", entry.entry_id)
            except Exception as err:
                log_debug("Error removing entry: %s", err, exc_info=True)
            return await self.async_step_user(user_input)

        errors = {}
        if user_input is not None:
            log_debug("Processing reconfigure input")
            try:
                await self._validate_token(user_input[CONF_ACCESS_TOKEN])
                log_debug("Token validation successful")
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        CONF_ACCESS_TOKEN: user_input[CONF_ACCESS_TOKEN],
                        _CONF_UPDATE_INTERVAL: user_input[_CONF_UPDATE_INTERVAL],
                    },
                )
                log_debug("Entry updated, reloading")
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")
            except InvalidAuth:
                log_debug("Invalid authentication")
                errors["base"] = "invalid_auth"
            except Exception as err:  # pylint: disable=broad-except
                log_debug("Unexpected exception: %s", err, exc_info=True)
                errors["base"] = "unknown"

        log_debug("Showing reconfigure form with errors: %s", errors)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required(CONF_ACCESS_TOKEN, default=entry.data.get(CONF_ACCESS_TOKEN, "")): str,
                vol.Required(_CONF_UPDATE_INTERVAL, default=entry.data.get(_CONF_UPDATE_INTERVAL, _DEFAULT_UPDATE_INTERVAL.seconds)): vol.In(UPDATE_INTERVAL_OPTIONS),
            }),
            errors=errors,
            description_placeholders={
                "url": "https://home.nature.global",
                "min_interval": str(min(UPDATE_INTERVAL_OPTIONS)),
                "max_interval": str(max(UPDATE_INTERVAL_OPTIONS)),
            }
        )

    async def _validate_token(self, access_token: str) -> None:
        """Validate the access token."""
        log_debug("Validating access token")
        session = async_get_clientsession(self.hass)
        api = NatureRemoAPI(access_token, session)
        try:
            await api.get()
            log_debug("Token validation successful")
        except Exception as err:
            log_debug("Error validating access token: %s", err, exc_info=True)
            raise InvalidAuth from err

class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth.""" 