"""Constants for the Nature Remo integration."""
from datetime import timedelta

DOMAIN = "nature_remo"

# Internal constants for climate control
_CONF_COOL_TEMP = "cool_temperature"
_CONF_HEAT_TEMP = "heat_temperature"
_DEFAULT_COOL_TEMP = 28
_DEFAULT_HEAT_TEMP = 20

# Update interval configuration
_CONF_UPDATE_INTERVAL = "update_interval"
_DEFAULT_UPDATE_INTERVAL = timedelta(seconds=60)
UPDATE_INTERVAL_OPTIONS = [10, 15, 30, 45, 60, 90, 120]  # Available options in seconds

_RESOURCE = "https://api.nature.global/1/" 