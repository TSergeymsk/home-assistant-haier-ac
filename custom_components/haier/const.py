"""Constants for the Haier AC integration."""
from __future__ import annotations

DOMAIN: str = "haier_ac"

CONF_HOST: str = "host"
CONF_PORT: str = "port"
CONF_NAME: str = "name"
CONF_MAC: str = "mac"

DEFAULT_PORT: int = 56800
DEFAULT_NAME: str = "Haier AC"

PLATFORMS: list[str] = ["climate"]

# Matches enum Mode from bstuff/haier-ac-remote
HAIER_MODE_SMART: int = 0
HAIER_MODE_COOL: int = 1
HAIER_MODE_HEAT: int = 2
HAIER_MODE_FAN: int = 3
HAIER_MODE_DRY: int = 4