# Glance Clock Integration

## Overview

This Home Assistant custom integration provides device tracking and notification capabilities for Glance Clock devices via Bluetooth.

## Features

- **Device Tracker**: Shows when your Glance Clock is paired and available
- **Notifications**: Send notifications to your Glance Clock
- **Scene Control**: Change display modes and scenes on your Glance Clock
- **Auto-Connection**: Maintains device connection across Home Assistant restarts
- **Custom Icon**: Integration displays with a custom Glance Clock icon

## Version History

### v4.0 (Current)

- **NEW**: Scene control functionality - change display modes on your Glance Clock
- **NEW**: Repository-compatible protobuf message format for better compatibility
- **IMPROVED**: Enhanced notification system with proper animation and sound mapping
- **FIXED**: Protobuf compatibility issues with Home Assistant environment
- Automatic connection management with active persistent connections
- Full notification customization with animations, sounds, and timing

### Previous Versions

- v3.x: Various implementations with memory and stability issues (resolved)
- Earlier: Basic time sync and advertisement monitoring (deprecated)

## Services

### Send Notification

Send custom notifications to your Glance Clock with various animations and sounds.

**Service**: `glance_clock.send_notification`

**Parameters**:

- `message` (required): Notification text
- `title` (optional): Notification title
- `animation`: Animation type (pulse, wave, fire, etc.)
- `sound`: Sound type (general_alert_1, calendar_alert, etc.)
- `duration`: Display duration in milliseconds
- `vibrate`: Enable vibration (true/false)
- `loop`: Loop the notification (true/false)

**Example**:

```yaml
service: glance_clock.send_notification
data:
  message: "Meeting in 5 minutes!"
  title: "Calendar Alert"
  animation: "pulse"
  sound: "calendar_alert"
  duration: 8000
  vibrate: true
```

### Change Scene

Control scene navigation and management on your Glance Clock.

**Service**: `glance_clock.change_scene`

**Parameters**:

- `scene_type` (required): Scene control action (next, prev, clear, delete)
- `scene_slot` (optional): Scene slot number for delete action (0-7)

**Examples**:

**Navigate to next scene:**

```yaml
service: glance_clock.change_scene
data:
  scene_type: "next"
```

**Navigate to previous scene:**

```yaml
service: glance_clock.change_scene
data:
  scene_type: "prev"
```

**Clear all scenes:**

```yaml
service: glance_clock.change_scene
data:
  scene_type: "clear"
```

**Delete specific scene:**

```yaml
service: glance_clock.change_scene
data:
  scene_type: "delete"
  scene_slot: 2
```

**Available Scene Controls**:

- `next` (or `start`): Navigate to next scene slot
- `prev` (or `stop`): Navigate to previous scene slot
- `clear`: Clear all scenes from the clock
- `delete`: Delete a specific scene slot

### Create Scene

Create custom scenes on your Glance Clock before navigating between them.

**Service**: `glance_clock.create_scene`

**Parameters**:

- `text` (required): Text to display in the scene
- `scene_slot` (optional): Scene slot number (0-7, default: 0)
- `display_mode` (optional): Display mode (8=ring only, 16=text only, 24=ring & text, default: 24)

**Example**:

```yaml
service: glance_clock.create_scene
data:
  text: "Weather: 22°C"
  scene_slot: 1
  display_mode: 24
```

**Note**: You need to create scenes first before you can navigate between them using `change_scene`. The clock can hold multiple scenes in different slots (0-7).

## Architecture

- **Coordinator Pattern**: Uses Home Assistant's PassiveBluetoothProcessorCoordinator
- **Bluetooth Integration**: Leverages HA's built-in bluetooth component
- **Device Management**: Automatic pairing and connection persistence
- **Clean Implementation**: No direct advertisement monitoring to prevent memory issues

## Configuration

1. Add the integration through Home Assistant's UI
2. Provide your Glance Clock's MAC address
3. The device tracker will show as "home" when paired
4. Use the notify service to send messages

## Files

- `__init__.py`: Main integration setup with Bluetooth coordinator
- `config_flow.py`: Configuration flow for device setup
- `device_tracker.py`: Device tracker platform showing connection status
- `notify.py`: Notification platform for sending messages
- `manifest.json`: Integration metadata and dependencies
- `const.py`: Constants and configuration
- `assets/icon.png`: Custom integration icon (736x736px)

## Technical Notes

- Uses BluetoothScanningMode.ACTIVE for device monitoring
- Coordinator handles automatic device connection management
- Device tracker state reflects actual connection status
- Memory-efficient implementation without direct advertisement processing
