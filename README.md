# myPV

Home Assistant Component for myPV

<a href="https://github.com/dneprojects/mypv"></a>
<p align="center">
  <a href="https://github.com/custom-components/hacs"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg"></a>
  <img src="https://img.shields.io/github/v/release/dneprojects/mypv" alt="Current version">
</p>

## Installation

### HACS (recommended)

Add user defined repository 'https://github.com/dneprojects/mypv' for type integration.
Search for integration 'myPV', use the three dot menu on the right side to download.
Restart Home Assistant.
Add integration 'myPV' in the settings.

### Manual download

Copy this folder to 'config/custom_components/mypv'.
Restart Home Assistant.
Add integration 'myPV' in the settings section.

## Configuration

Usually, devices get detected automatically if they operate in the same subnet as the Home Assistant host. However, if a device could not be detected, a manual entry of the ip is via UI still supported. A parameter called update interval is given to determine the polling time interval for the sensor values. The default value is 10 seconds. This value can be changed later, too.

## Features

The myPV custom integration works locally in the home network utilizing the http api. So it doesn't need any login.
- Automatic discovery of devices.
- The integration is written to support multiple devices. Meanwhile, it has beeny tested with ELWA, ELWA 2, AC-THOR 1, AC-THOR 9s, and SOLTHOR-DC. For multiple devices, please use the configuration step with a different IP address.
- It offers binary sensors and sensors for all data points provided by the myPV devices.
- The heating power can be set manually by an input number between 0 and 3000 W (3600 W for ELWA 2, 9000 W for AC THOR 9s). 
This will turn on the heater for a predefined time period. This period has to been setup via web or cloud setup, as it is not supported by the myPV api. However, if the power value (usually the surplus of collected solar power) is set by an automation repeatedly within that period, a continuous control can be achieved.
- In the same way, an upper power bound for the device's internal PID controller can be given. The internal PID controller uses the same time period as the external control described above.
- In order to enable both control entities, the control type has to be set to "html" via web or cloud setup. Otherwise, only sensor data points will be exposed as Home Assistant entities.
The Boost mode, if enabled, works on a weekly schedule to maintain a given minimum temperature. It can be started manually by a button press (if enabled). It stops, if the temperature preset is reached.
- Three energy consumption entities show the amount of spent energy per day, per month, or total. By means of an action called mypv.reset_energy_sensor each one of these cumulated values can be reset to zero.

## Maintenance

This integration is actively maintained. If any problem occurs, please use the issues category on github to report it. You can also open an issue report if you have an additional feature request.

## Credits

This integration is based on an implementation https://github.com/zaubererty/homeassistant-mvpv.
Although it worked fine, the main feature, controlling the device by home assistant automations was not possible.
So I totally rewrote the integration and added a lot of extensions. 
However, thanks to the work of zaubererty at this place!

