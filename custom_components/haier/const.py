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
CONF_TIMEOUT: Final = "timeout"

# Options
HEALTH_MODE_TYPES: Final = ["switch", "light"]

# Platforms
PLATFORMS: Final = ["climate", "switch", "light"]

# Default values
DEFAULT_TIMEOUT: Final = 3000  # milliseconds
DEFAULT_SCAN_INTERVAL: Final = 30

# Haier-specific constants
HAIER_MODE_AUTO: Final = 1
HAIER_MODE_COOL: Final = 2
HAIER_MODE_HEAT: Final = 3
HAIER_MODE_FAN: Final = 4
HAIER_MODE_DRY: Final = 5

HAIER_FAN_AUTO: Final = 0
HAIER_FAN_LOW: Final = 1
HAIER_FAN_MEDIUM: Final = 2
HAIER_FAN_HIGH: Final = 3

HAIER_SWING_OFF: Final = 0
HAIER_SWING_VERTICAL: Final = 1

# Services
SERVICE_SET_FAN_SPEED: Final = "set_fan_speed"
SERVICE_SET_SWING_MODE: Final = "set_swing_mode"

# Attributes
ATTR_INSIDE_TEMPERATURE: Final = "inside_temperature"
ATTR_OUTSIDE_TEMPERATURE: Final = "outside_temperature"
ATTR_HUMIDITY: Final = "humidity"
ATTR_FILTER_STATUS: Final = "filter_status"
ATTR_ENERGY_CONSUMPTION: Final = "energy_consumption"
ATTR_DEVICE_MAC: Final = "device_mac"
ATTR_DEVICE_IP: Final = "device_ip"