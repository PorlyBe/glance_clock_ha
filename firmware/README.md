# Glance Clock Firmware

This directory contains firmware files for the Glance Clock device.

## Current Firmware

The ZIP file in this directory contains the latest compatible firmware for use with this Home Assistant integration.

## How to Update Firmware

1. Download the firmware ZIP file from this directory
2. Install **nRF Connect** app on your phone:
   - [Android](https://play.google.com/store/apps/details?id=no.nordicsemi.android.mcp)
   - [iOS](https://apps.apple.com/us/app/nrf-connect-for-mobile/id1054362403)
3. Open nRF Connect and connect to your Glance Clock
4. Tap the **DFU** icon (circular arrows) in the top right
5. Select **Distribution packet (ZIP)**
6. Browse and select the firmware ZIP file
7. Tap **Start** to begin the update
8. Wait for completion (do not disconnect during update)
9. The clock will restart automatically when finished

## Important Notes

- Always perform a factory reset before updating firmware
- Set the time using CTS (Current Time Service) after firmware update
- Do not disconnect the device during the update process
- Keep your phone close to the clock during the update

## Version Information

Check the filename of the ZIP file for version information.
