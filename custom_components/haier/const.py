"""Constants for Haier AC integration."""
from typing import Final

DOMAIN: Final = "haier"
DEFAULT_NAME: Final = "Haier AC"

# Configuration keys
CONF_IP_ADDRESS: Final = "ip_address"
CONF_MAC: Final = "mac"
CONF_NAME: Final = "name"
CONF_HEALTH_MODE: Final = "health_mode"
CONF_HEALTH_MODE_TYPE: Final = "health_mode_type"

# Options
HEALTH_MODE_TYPES: Final = ["switch", "light"]

# Platforms
PLATFORMS: Final = ["climate", "switch", "light"]

# Default values
DEFAULT_TIMEOUT: Final = 10
DEFAULT_PORT: Final = 5683  # CoAP port example
DEFAULT_SCAN_INTERVAL: Final = 30

# Services
SERVICE_SET_FAN_SPEED: Final = "set_fan_speed"
SERVICE_SET_SWING_MODE: Final = "set_swing_mode"

# Attributes
ATTR_INSIDE_TEMPERATURE: Final = "inside_temperature"
ATTR_OUTSIDE_TEMPERATURE: Final = "outside_temperature"
ATTR_HUMIDITY: Final = "humidity"
ATTR_FILTER_STATUS: Final = "filter_status"
ATTR_ENERGY_CONSUMPTION: Final = "energy_consumption"