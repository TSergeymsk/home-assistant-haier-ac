# Haier AC Custom Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

This custom integration allows you to control Haier air conditioners through your local network using the official protocol. The integration communicates directly with devices via TCP, without cloud services.

## Supported Devices

- Haier air conditioners with Wi-Fi module support
- Models supporting direct TCP connection on port 56800

## Features

- Power on/off control
- Temperature setting (16-30°C)
- Operation mode selection (AUTO, COOL, HEAT, DRY, FAN)
- Fan speed control (AUTO, LOW, MEDIUM, HIGH)
- Health mode control
- Vertical swing mode control (enabled/disabled)
- Current temperature monitoring
- Automatic reconnection on connection loss

## Installation

### Method 1: HACS (Recommended)

1. Add this repository to HACS:
   - Go to HACS → Integrations → Menu (three dots) → Custom repositories
   - Add the URL of this repository
   - Select category "Integration"

2. Install the integration through HACS

3. Restart Home Assistant

### Method 2: Manual Installation

1. Download the latest release from the [Releases](https://github.com/your-username/haier-ac-homeassistant/releases) section

2. Copy the `custom_components/haier` folder to your Home Assistant `custom_components` directory

3. Restart Home Assistant

## Configuration

### Via UI (Recommended)

1. After installation, go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for **"Haier AC"**
4. Follow the setup wizard to add your devices

### Manual Configuration via configuration.yaml

Alternatively, you can add devices manually in your `configuration.yaml`:

```yaml
haier:
  devices:
    - name: "Living Room AC"
      ip_address: "192.168.1.100"
      mac: "123456789ABC"
      health_mode: false
      health_mode_type: "switch"
    - name: "Bedroom AC"
      ip_address: "192.168.1.101"
      mac: "DEF123456789"
      health_mode: true
      health_mode_type: "switch"
```

## Configuration Options

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | string | Yes | - | Friendly name for the device |
| `ip_address` | string | Yes | - | IP address of the device |
| `mac` | string | Yes | - | MAC address of the device (12 characters, without separators) |
| `health_mode` | boolean | No | `false` | Enable health mode by default |
| `health_mode_type` | string | No | `"switch"` | Type of health mode control (`switch` or `button`) |
| `timeout` | integer | No | `5000` | Connection timeout in milliseconds |

## Available Entities

After installation, the following entities will be created for each device:

- **Climate entity** - Main control for temperature, mode, and fan speed
- **Switch entity** - Power on/off (if not included in climate entity)
- **Health mode switch** - Control for health/ionizer mode
- **Swing mode switch** - Control for vertical swing
- **Sensor** - Current temperature reading

## Usage

### Basic Controls

1. **Power Control**: Use the climate entity or dedicated switch to turn the AC on/off
2. **Temperature Adjustment**: Set desired temperature on the climate entity
3. **Mode Selection**: Choose between AUTO, COOL, HEAT, DRY, or FAN modes
4. **Fan Speed**: Adjust fan speed between AUTO, LOW, MEDIUM, and HIGH
5. **Health Mode**: Toggle ionizer/health mode when available
6. **Swing Mode**: Control vertical swing function

### Automation Examples

```yaml
automation:
  - alias: "Turn on AC when temperature is high"
    trigger:
      platform: numeric_state
      entity_id: sensor.living_room_temperature
      above: 26
    action:
      service: climate.turn_on
      target:
        entity_id: climate.living_room_ac

  - alias: "Turn off AC when leaving home"
    trigger:
      platform: state
      entity_id: person.your_name
      from: "home"
      to: "not_home"
    action:
      service: climate.turn_off
      target:
        entity_id: climate.living_room_ac
```

## Troubleshooting

### Common Issues

1. **Device Not Found**
   - Verify the IP address is correct
   - Check that the device is powered on and connected to the network
   - Ensure port 56800 is accessible (check firewall settings)

2. **Connection Lost**
   - The integration automatically reconnects when connection is lost
   - Check network stability
   - Verify device is still responding to ping

3. **Incorrect Temperature Readings**
   - Ensure the MAC address is entered correctly (12 characters, no separators)
   - Restart Home Assistant to reinitialize the connection

### Debug Logging

To enable debug logging for troubleshooting, add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.haier: debug
    custom_components.haier.device: debug
    custom_components.haier.protocol: debug
```

## Technical Details

### Protocol Information

This integration uses the official Haier TCP protocol on port 56800. Communication is bidirectional, with the device sending periodic status updates.

### Architecture

- **Device Class**: Handles TCP connection, command sending, and response parsing
- **Protocol Class**: Implements packet structure and state management
- **Climate Platform**: Home Assistant climate entity implementation

### Compatibility

Tested with:
- Home Assistant 2024.1.0 and above
- Python 3.10+
- Haier Wi-Fi enabled air conditioners

## Development

### Project Structure

```
custom_components/haier/
├── __init__.py
├── climate.py
├── device.py
├── protocol.py
├── manifest.json
└── translations/
```

### Building on Top of This Integration

This integration can be extended to support additional features or device models. The protocol implementation is modular and can be adapted for similar Haier devices.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## Disclaimer

This integration is not officially supported by Haier. Use at your own risk. The developers are not responsible for any damage to your devices.

## Acknowledgments

- Based on reverse engineering of the official Haier protocol
- Inspired by the [haier-ac-remote](https://github.com/vooon/hacker-ac-remote) project
- Thanks to all contributors and testers

## Support

For support, please:
1. Check the [Troubleshooting](#troubleshooting) section
2. Search existing [Issues](https://github.com/your-username/haier-ac-homeassistant/issues)
3. Open a new issue if your problem isn't already reported

---

**Note**: This integration is community-maintained and not affiliated with Haier Group.