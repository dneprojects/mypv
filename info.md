# myPV

Home Assistant Component for myPV

<a href="https://github.com/dneprojects/mypv"></a>
<p align="center">
  <img src="https://img.shields.io/badge/Home%20Assistant-Marketplace-41BDF5.svg" alt="Home Assistant Marketplace">
  <img src="https://img.shields.io/github/v/release/dneprojects/mypv" alt="Current version">
</p>

## Installation

myPV is listed in the Home Assistant Marketplace.

1. Open the **Marketplace** from **Settings**, search for **myPV** and install it.
2. Restart Home Assistant when asked.
3. Devices on the same network are detected and offered under **Settings → Devices & Services**; otherwise add **myPV** there and enter the device's IP.

## Configuration

The integration is configurated via UI.
Enter an IP address, at which a myPV devices will be found.

## Features

The myPV custom integration works locally in the home network utilizing the http api. So it doesn't need any login.
- The integration is written to support multiple devices. However, it is only tested just with one (ELWA 2). For multiple devices, please use the configuration step with a different IP address.
- It offers binary sensors and sensors for all data points provided by the myPV devices.
- The heating power can be set manually by an input number between 0 and 3000 W (3600 W for ELWA 2, 9000 W for AC THOR 9s). This will turn on the heater for a predefined time period. This period has to been setup via web or cloud setup, as it is not supported by the myPV api. However, if the power value (usually the surplus of collected solar power) is set by an automation repeatedly within that period, a continuous control can be achieved.
- Alternatively, the device's own PID controller can do the regulating. The PID power value is not a setpoint but a measurement: it is the power at the grid connection point, positive for surplus and negative for power drawn from the grid, and the device adopts it as its surplus and regulates its heating power from it. This is the way to use a meter that myPV does not support directly but Home Assistant can read. It uses the same time period as the external control described above, and it has to be written repeatedly for the device's controller to follow it -- a single value is dropped again when the time period expires.
  - **It has to be a live measurement, and it has to include the device's own consumption.** That is what closes the control loop: as the heater draws power, the surplus falls, and the controller stops raising it. A fixed value never falls, so the controller keeps going until the device runs at maximum power — on an AC ELWA 2, a constant "surplus" of 250 W drove the output to 3.5 kW and held it there. The device reacts within one write interval, so how often you write is how quickly it responds to a change in load. It regulates towards the target grid power configured on the device, not towards zero, so a small part of the surplus is left unused.
- In order to enable both control entities, the control type has to be set to "html" via web or cloud setup. Otherwise, only sensor data points will be exposed as Home Assistant entities.

## Credits

This integration is based on an implementation https://github.com/zaubererty/homeassistant-mvpv.
Although it worked fine, the main feature, controlling the device by home assistant automations was not possible.
So I totally rewrote the integration. 
However, thanks to the work of zaubererty at this place!
