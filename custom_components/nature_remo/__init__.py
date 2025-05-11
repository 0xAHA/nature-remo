"""The Nature Remo integration."""
import json
import logging
import os
import voluptuous as vol
import aiofiles

from datetime import timedelta
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.entity import Entity

from .const import (
    DOMAIN,
    _DEFAULT_COOL_TEMP,
    _DEFAULT_HEAT_TEMP,
    _DEFAULT_UPDATE_INTERVAL,
    _CONF_COOL_TEMP,
    _CONF_HEAT_TEMP,
    _CONF_UPDATE_INTERVAL,
    _RESOURCE,
)

_LOGGER = logging.getLogger(__name__)

def log_debug(msg, *args, **kwargs):
    """Log debug message with Nature_Remo prefix."""
    _LOGGER.debug(f"Nature_Remo: {msg}", *args, **kwargs)

def log_error(msg, *args, **kwargs):
    """Log error message with Nature_Remo prefix."""
    _LOGGER.error(f"Nature_Remo: {msg}", *args, **kwargs)

# Keep the YAML config schema for import
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("access_token"): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Nature Remo from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    access_token = entry.data["access_token"]
    update_interval = timedelta(seconds=entry.data.get(_CONF_UPDATE_INTERVAL, _DEFAULT_UPDATE_INTERVAL.seconds))
    log_debug("Setting up Nature Remo with update interval of %d seconds", update_interval.seconds)
    
    session = async_get_clientsession(hass)
    api = NatureRemoAPI(access_token, session)
    
    async def async_update_data():
        """Fetch data from API endpoint."""
        log_debug("Starting scheduled update of Nature Remo data (interval: %d seconds)", update_interval.seconds)
        try:
            data = await api.get()
            log_debug("Successfully fetched new data from Nature Remo API")
            return data
        except Exception as err:
            log_error("Error fetching Nature Remo data: %s", err, exc_info=True)
            raise
    
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Nature Remo update",
        update_method=async_update_data,
        update_interval=update_interval,
    )
    
    # Add coordinator update listener
    @callback
    def coordinator_update():
        """Log coordinator updates."""
        log_debug("Coordinator update received, last_update_success: %s", coordinator.last_update_success)
    
    coordinator.async_add_listener(coordinator_update)
    
    log_debug("Starting initial data fetch for Nature Remo")
    try:
        await coordinator.async_refresh()
        log_debug("Initial data fetch complete")
    except Exception as err:
        log_error("Error during initial data fetch: %s", err, exc_info=True)
        raise
    
    # Store coordinator in hass data
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "config": {
            _CONF_COOL_TEMP: _DEFAULT_COOL_TEMP,
            _CONF_HEAT_TEMP: _DEFAULT_HEAT_TEMP,
        }
    }
    
    log_debug("Setting up platforms with coordinator (update_interval: %s)", coordinator.update_interval)
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "climate"])
    log_debug("Platform setup complete")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "climate"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Nature Remo component."""
    hass.data.setdefault(DOMAIN, {})

    # Simple file-based approach to track notification state
    storage_file = hass.config.path(f".{DOMAIN}_notification_state.json")
    log_debug("Using storage file at: %s", storage_file)
    
    notification_shown = False
    
    try:
        if os.path.exists(storage_file):
            async with aiofiles.open(storage_file, 'r') as f:
                data = json.loads(await f.read())
                notification_shown = data.get('acknowledged', False)
    except Exception as ex:
        log_debug("Error loading notification state: %s", ex)

    if DOMAIN in config:
        log_debug("Found YAML configuration for Nature Remo")

        # If notification hasn't been shown yet
        if not notification_shown:
            # Create persistent notification
            notification_id = f"{DOMAIN}_config_imported"
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Nature Remo Configuration Imported",
                    "message": (
                        "Your YAML configuration for Nature Remo has been imported into the UI configuration.\n\n"
                        "Please remove the configuration from your configuration.yaml file to avoid conflicts.\n\n"
                        "You can now manage your configuration through the UI. "
                        "Click DISMISS to prevent this message from appearing again."
                    ),
                    "notification_id": notification_id,
                },
            )
            
            # Log all events to see what's happening
            async def log_all_events(event):
                """Log all events to see what's happening."""
                # Any event that looks related to notifications
                if "notification" in event.event_type.lower():
                    # See if our notification_id appears anywhere in the event data
                    event_data_str = str(event.data)
                    if notification_id in event_data_str:
                        try:
                            # Save the acknowledged state regardless of the exact event type
                            async with aiofiles.open(storage_file, 'w') as f:
                                await f.write(json.dumps({"acknowledged": True}))
                        except Exception as ex:
                            log_debug("Failed to save acknowledged state: %s", ex)
            
            # Listen for ALL events for diagnostic purposes
            remove_listener = hass.bus.async_listen("*", log_all_events)
            
            # Store the listener so it doesn't get garbage collected
            hass.data[DOMAIN]["remove_listener"] = remove_listener
            
            # Also create a one-time task to auto-acknowledge after 5 minutes
            # as a fallback in case the event system isn't working
            async def auto_acknowledge():
                """Automatically acknowledge after a timeout."""
                import asyncio
                await asyncio.sleep(300)  # 5 minutes
                
                # Check if we've already acknowledged
                try:
                    if os.path.exists(storage_file):
                        async with aiofiles.open(storage_file, 'r') as f:
                            data = json.loads(await f.read())
                            if data.get('acknowledged', False):
                                return  # Already acknowledged, nothing to do
                    
                    # Not acknowledged yet, do it now
                    log_debug("Auto-acknowledging notification after timeout")
                    async with aiofiles.open(storage_file, 'w') as f:
                        await f.write(json.dumps({"acknowledged": True}))
                except Exception as ex:
                    log_debug("Error in auto-acknowledge: %s", ex)
            
            # Start the auto-acknowledge task
            hass.async_create_task(auto_acknowledge())
        else:
            log_debug("Notification was previously acknowledged, skipping")

        # Forward the YAML config to the config flow
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=config[DOMAIN],
            )
        )

    return True

class NatureRemoAPI:
    """Nature Remo API client"""

    def __init__(self, access_token, session):
        """Init API client"""
        self._access_token = access_token
        self._session = session
        log_debug("Initialized Nature Remo API client")

    async def get(self):
        """Get appliance and device list"""
        log_debug("Fetching data from Nature Remo API")
        headers = {"Authorization": f"Bearer {self._access_token}"}
        
        # Get appliances
        log_debug("Fetching appliances from %s/appliances", _RESOURCE)
        try:
            response = await self._session.get(f"{_RESOURCE}/appliances", headers=headers)
            response.raise_for_status()  # Raise exception for bad status codes
            appliances_data = await response.json()
            log_debug("Received appliances data: %s", appliances_data)
            appliances = {x["id"]: x for x in appliances_data}
        except Exception as err:
            log_error("Error fetching appliances: %s", err, exc_info=True)
            raise
        
        # Get devices
        log_debug("Fetching devices from %s/devices", _RESOURCE)
        try:
            response = await self._session.get(f"{_RESOURCE}/devices", headers=headers)
            response.raise_for_status()  # Raise exception for bad status codes
            devices_data = await response.json()
            log_debug("Received devices data: %s", devices_data)
            devices = {x["id"]: x for x in devices_data}
        except Exception as err:
            log_error("Error fetching devices: %s", err, exc_info=True)
            raise
        
        log_debug("API call completed successfully")
        return {"appliances": appliances, "devices": devices}

    async def post(self, path, data):
        """Post any request"""
        log_debug("Making POST request to %s%s with data: %s", _RESOURCE, path, data)
        headers = {"Authorization": f"Bearer {self._access_token}"}
        try:
            response = await self._session.post(
                f"{_RESOURCE}{path}", data=data, headers=headers
            )
            response.raise_for_status()  # Raise exception for bad status codes
            response_data = await response.json()
            log_debug("Received POST response: %s", response_data)
            return response_data
        except Exception as err:
            log_error("Error in POST request: %s", err, exc_info=True)
            raise

class NatureRemoBase(Entity):
    """Nature Remo entity base class."""

    def __init__(self, coordinator, appliance):
        self._coordinator = coordinator
        self._name = f"Nature Remo {appliance['nickname']}"
        self._appliance_id = appliance["id"]
        self._device = appliance["device"]

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._appliance_id

    @property
    def should_poll(self):
        """Return the polling requirement of the entity."""
        return False

    @property
    def device_info(self):
        """Return the device info for the sensor."""
        return {
            "identifiers": {(DOMAIN, self._device["id"])},
            "name": self._device["name"],
            "manufacturer": "Nature Remo",
            "model": self._device["serial_number"],
            "sw_version": self._device["firmware_version"],
        }

class NatureRemoDeviceBase(Entity):
    """Nature Remo device entity base class."""

    def __init__(self, coordinator, device):
        """Initialize the device entity."""
        self._coordinator = coordinator
        self._device = device
        self._name = f"Nature Remo {device['name']}"
        self._device_id = device["id"]

    @property
    def name(self):
        """Return the name of the device."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._device_id

    @property
    def should_poll(self):
        """Return the polling requirement of the entity."""
        return False

    @property
    def device_info(self):
        """Return the device info for the sensor."""
        return {
            "identifiers": {(DOMAIN, self._device["id"])},
            "name": self._device["name"],
            "manufacturer": "Nature Remo",
            "model": self._device["serial_number"],
            "sw_version": self._device["firmware_version"],
        }
