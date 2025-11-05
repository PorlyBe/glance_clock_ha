# Glance Clock Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/PorlyBe/glance_clock_ha.svg)](https://github.com/PorlyBe/glance_clock_ha/releases)
[![License](https://img.shields.io/github/license/PorlyBe/glance_clock_ha.svg)](LICENSE)

Home Assistant custom integration for Glance Clock devices via Bluetooth.

<!-- [IMAGE: Banner image showing the Glance Clock device] -->

## Features

- 🔔 **Send Notifications** - Display custom messages with animations and sounds
- 💡 **Light Control** - Adjust brightness and power state
- 🔄 **Switch Controls** - Toggle various clock features (time mode, night mode, points display)
- 🎛️ **Select Options** - Choose different display modes and date formats
- 📊 **Sensor Data** - Monitor battery level and device information
- 🌤️ **Weather Forecast** - Send 24-hour weather data with color gradients
- 🔗 **Bluetooth Native** - Leverages Home Assistant's built-in Bluetooth integration

<!-- [IMAGE: Screenshot of the integration in Home Assistant UI] -->

## Prerequisites

⚠️ **Important:** Before using this integration, you must:

1. Reset your Glance Clock to factory settings
2. Synchronize the time using nRF Connect
3. Update the firmware (recommended)
4. Pair with your system's Bluetooth

### Step 1: Factory Reset Your Glance Clock

Before setup, perform a complete factory reset on your Glance Clock. This ensures a clean state for pairing and configuration.

**To reset your Glance Clock:**

Hold the reset button + Power button. Let go of the reset button and keep holding the Power button until the LED blinking pattern changes. Then release it as well.

NOTE: this will also reset the firmware back to the factory version.

### Step 2: Set Time and Update Firmware (nRF Connect)

The Glance Clock requires time synchronization and may need a firmware update before use.

#### Download nRF Connect

- **Android**: [nRF Connect on Google Play](https://play.google.com/store/apps/details?id=no.nordicsemi.android.mcp)
- **iOS**: [nRF Connect on App Store](https://apps.apple.com/us/app/nrf-connect-for-mobile/id1054362403)

#### Set the Time

1. Open nRF Connect app on your phone
2. Go to the **Configure GATT server** tab (server icon)
3. Tap **Add service**
4. Select **Current Time Service (CTS)** - UUID: 0x1805
5. Tap **OK** to add the service
6. Go back to the **Scanner** tab
7. Find your Glance Clock in the device list
8. Tap **Connect**
9. The clock should automatically read the time from your phone
10. Once synchronized, disconnect from the clock

#### Update Firmware (Optional but Recommended)

1. Download the latest firmware from the [`/firmware`](firmware/) directory in this repository
2. In nRF Connect, reconnect to your Glance Clock
3. Tap the **DFU** icon (circular arrows) in the top right
4. Select **Distribution packet (ZIP)**
5. Browse and select the firmware ZIP file you downloaded
6. Tap **Start** to begin the update
7. Wait for the update to complete (do not disconnect)
8. The clock will restart automatically when finished

### Step 3: Pair Your Glance Clock with Home Assistant

After resetting, setting time, and updating firmware, pair the clock with Home Assistant.

Open a terminal in Home Assistant (Settings → System → Terminal) and run:

```bash
bluetoothctl
agent on
default-agent
scan on
```

Wait until you see your Glance Clock appear (look for "Glance" in the name). Note the MAC address (format: `XX:XX:XX:XX:XX:XX`), then:

```bash
pair XX:XX:XX:XX:XX:XX
```

Replace `XX:XX:XX:XX:XX:XX` with your actual MAC address. When prompted, enter the PIN shown on the Glance Clock display, then exit:

```bash
exit
```

Your Glance Clock is now paired and ready to add to Home Assistant.

## Installation

### Via HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add the repository URL: `https://github.com/PorlyBe/glance_clock_ha`
6. Select category "Integration"
7. Click "Add"
8. Find "Glance Clock" in the integration list and click "Download"
9. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/PorlyBe/glance_clock_ha/releases)
2. Extract the `glance_clock` folder to your `custom_components` directory
3. Restart Home Assistant

## Configuration

After pairing your Glance Clock, Home Assistant will automatically discover it.

1. Go to **Settings** → **Devices & Services**
2. You should see a "Discovered" notification for your Glance Clock
3. Click **Configure** on the discovered device
4. Follow the prompts to complete setup

If the device doesn't appear automatically, you can manually add it:
1. Click **Add Integration**
2. Search for "Glance Clock"
3. Select your Glance Clock from the list of discovered devices
4. Click **Submit**

<!-- [IMAGE: Configuration flow screenshot] -->

## Entities

Once configured, the integration provides:

- **Light** - Control brightness and power state
- **Switches** - Time Mode, Night Mode, Always Show Points
- **Selects** - Date Format options
- **Sensors** - Battery level percentage
- **Notify** - Send notifications via `notify.glance_clock`

## Services

### Send Notification

Send a custom notification to your Glance Clock.

**Service:** `notify.glance_clock`

```yaml
service: notify.glance_clock
data:
  message: "Meeting in 5 minutes!"
  data:
    title: "Calendar Reminder"
    animation: "pulse"
    sound: "bells"
    color: "blue"
    priority: "high"
```

**Parameters:**

- `message` (required): Notification text
- `title`: Notification title
- `animation`: Animation effect (none, pulse, wave, fire, wheel, flower, sun, thunderstorm, cloud)
- `sound`: Sound effect (none, waves, rise, bells, radar, hello, complete)
- `color`: Display color (white, red, blue, lime, dark_orange, blue_violet, lawn_green)
- `priority`: Priority level (low, medium, high, critical)
- `text_modifier`: Text effect (none, repeat, rapid, delay)

### Update Display Settings

Configure display settings on your Glance Clock.

**Service:** `glance_clock.update_display_settings`

```yaml
service: glance_clock.update_display_settings
data:
  nightModeEnabled: true
  displayBrightness: 128
  timeModeEnable: true
  timeFormat12: false
  dateFormat: 1
```

### Send Weather Forecast

Send weather forecast data with color gradients.

**Service:** `glance_clock.send_forecast`

```yaml
service: glance_clock.send_forecast
data:
  weather_entity: weather.home
  max_color: "#FF0000"
  min_color: "#0000FF"
```

### Read Current Settings

Retrieve current device settings.

**Service:** `glance_clock.read_current_settings`

### Refresh Entities

Force refresh all entity states.

**Service:** `glance_clock.refresh_entities`

## Automations

### Weather Forecast Automation

Automatically update your Glance Clock with weather forecast data whenever it changes.

1. Go to **Settings** → **Automations & Scenes**
2. Click **Create Automation** → **Create new automation**
3. Click the three dots (⋮) and select **Edit in YAML**
4. Paste the following configuration:

```yaml
alias: Weather Update
description: Update Glance Clock with weather forecast
triggers:
  - trigger: state
    entity_id:
      - weather.forecast_home  # Replace with your weather entity
conditions: []
actions:
  - action: glance_clock.send_forecast
    data:
      weather_entity: weather.forecast_home  # Replace with your weather entity
      max_color: [255, 102, 0]    # Orange for hot temperatures
      min_color: [0, 120, 255]    # Blue for cold temperatures
      min_value: 0                # Minimum temperature scale (°C)
      max_value: 40               # Maximum temperature scale (°C)
  - action: glance_clock.send_notice
    data:
      text: Weather Updated
      animation: sun
      sound: none
      color: blue
      priority: medium
mode: single
```

5. Update `weather.forecast_home` to match your weather entity
6. Adjust `min_value` and `max_value` to suit your local temperature range
7. Click **Save** and give your automation a name

The clock will now automatically display a 24-hour temperature forecast with color gradients whenever the weather updates!

## Troubleshooting

### Integration won't add or connect

- Ensure your Glance Clock is **paired** with your system via Bluetooth (see Prerequisites)
- Verify the MAC address is correct (use `bluetoothctl devices` to list paired devices)
- Check that Home Assistant's Bluetooth integration is enabled and working
- Restart Home Assistant and try again

### Device shows as unavailable

- The Glance Clock may have gone to sleep or moved out of range
- Check Bluetooth adapter signal strength
- Re-pair the device if connection issues persist

### Notifications not appearing

- Ensure the Glance Clock is powered on and connected
- Check that the message text is not empty
- Try sending a simple notification without optional parameters

### Battery sensor shows unavailable

- Some Glance Clock models may not support battery reporting via Bluetooth
- Battery data updates periodically, not in real-time

## Credits

This integration uses protocol and implementation insights from [Hypfer's Glance Clock project](https://github.com/Hypfer/glance-clock). Special thanks to the original developers for documenting the Glance Clock protocol and providing a foundation for Bluetooth communication.

## Support

- [Report Issues](https://github.com/PorlyBe/glance_clock_ha/issues)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
