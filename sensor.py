"""Support for Nature Remo E energy sensor."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfPower,
    PERCENTAGE,
    LIGHT_LUX,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.unit_system import UnitOfTemperature
from homeassistant.components.sensor import SensorDeviceClass

from . import DOMAIN, NatureRemoBase, NatureRemoDeviceBase

_LOGGER = logging.getLogger(__name__)

def log_debug(msg, *args, **kwargs):
    """Log debug message with Nature_Remo prefix."""
    _LOGGER.debug(f"Nature_Remo: {msg}", *args, **kwargs)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Nature Remo sensors based on config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    appliances = coordinator.data["appliances"]
    devices = coordinator.data["devices"]
    
    log_debug("Setting up sensors with appliances: %s", appliances)
    log_debug("Setting up sensors with devices: %s", devices)
    
    entities = [
        NatureRemoE(coordinator, appliance)
        for appliance in appliances.values()
        if appliance["type"] == "EL_SMART_METER"
    ]
    
    for device in devices.values():
        log_debug("Processing device %s with events: %s", device["name"], device["newest_events"])
        for sensor in device["newest_events"].keys():
            if sensor == "te":
                entities.append(NatureRemoTemperatureSensor(coordinator, device))
            elif sensor == "hu":
                entities.append(NatureRemoHumiditySensor(coordinator, device))
            elif sensor == "il":
                entities.append(NatureRemoIlluminanceSensor(coordinator, device))
    
    log_debug("Created %d sensor entities", len(entities))
    async_add_entities(entities)


class NatureRemoE(NatureRemoBase):
    """Implementation of a Nature Remo E sensor."""

    def __init__(self, coordinator, appliance):
        super().__init__(coordinator, appliance)
        self._unit_of_measurement = UnitOfPower.WATT
        log_debug("Initialized Nature Remo E sensor for appliance: %s", appliance)

    @property
    def state(self):
        """Return the state of the sensor."""
        appliance = self._coordinator.data["appliances"][self._appliance_id]
        log_debug("Processing Nature Remo E data for appliance %s: %s", self._appliance_id, appliance)
        
        smart_meter = appliance["smart_meter"]
        log_debug("Smart meter data: %s", smart_meter)
        
        echonetlite_properties = smart_meter["echonetlite_properties"]
        log_debug("EchonetLite properties: %s", echonetlite_properties)
        
        measured_instantaneous = next(
            value["val"] for value in echonetlite_properties if value["epc"] == 231
        )
        log_debug("Measured instantaneous power: %sW", measured_instantaneous)
        return measured_instantaneous

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return UnitOfPower.WATT

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.power

    async def async_added_to_hass(self):
        """Subscribe to updates."""
        log_debug("Nature Remo E sensor added to hass: %s", self.name)
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )

    async def async_update(self):
        """Update the entity."""
        log_debug("Updating Nature Remo E sensor: %s", self.name)
        await self._coordinator.async_request_refresh()


class NatureRemoTemperatureSensor(NatureRemoDeviceBase):
    """Implementation of a Nature Remo sensor."""

    def __init__(self, coordinator, appliance):
        super().__init__(coordinator, appliance)
        self._name = self._name.strip() + " Temperature"
        log_debug("Initialized temperature sensor for device: %s", appliance)

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._device["id"] + "-te"

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return UnitOfTemperature.CELSIUS

    @property
    def state(self):
        """Return the state of the sensor."""
        device = self._coordinator.data["devices"][self._device["id"]]
        log_debug("Processing temperature data for device %s: %s", self._device["id"], device)
        
        temperature = device["newest_events"]["te"]["val"]
        log_debug("Temperature value: %s°C", temperature)
        return temperature

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.TEMPERATURE


class NatureRemoHumiditySensor(NatureRemoDeviceBase):
    """Implementation of a Nature Remo sensor."""

    def __init__(self, coordinator, appliance):
        super().__init__(coordinator, appliance)
        self._name = self._name.strip() + " Humidity"
        log_debug("Initialized humidity sensor for device: %s", appliance)

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._device["id"] + "-hu"

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return PERCENTAGE

    @property
    def state(self):
        """Return the state of the sensor."""
        device = self._coordinator.data["devices"][self._device["id"]]
        log_debug("Processing humidity data for device %s: %s", self._device["id"], device)
        
        humidity = device["newest_events"]["hu"]["val"]
        log_debug("Humidity value: %s%%", humidity)
        return humidity

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.HUMIDITY


class NatureRemoIlluminanceSensor(NatureRemoDeviceBase):
    """Implementation of a Nature Remo sensor."""

    def __init__(self, coordinator, appliance):
        super().__init__(coordinator, appliance)
        self._name = self._name.strip() + " Illuminance"
        log_debug("Initialized illuminance sensor for device: %s", appliance)

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._device["id"] + "-il"

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return LIGHT_LUX

    @property
    def state(self):
        """Return the state of the sensor."""
        device = self._coordinator.data["devices"][self._device["id"]]
        log_debug("Processing illuminance data for device %s: %s", self._device["id"], device)
        
        illuminance = device["newest_events"]["il"]["val"]
        log_debug("Illuminance value: %slx", illuminance)
        return illuminance

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.ILLUMINANCE 
