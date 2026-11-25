# FORScan's named settings on a 2017 Ford Focus

Every setting FORScan 2.3.72 names for this car, as read on 2026-11-24 with an
OBDLink EX on COM5 under Wine (see [ford-focus-2017.md](ford-focus-2017.md) for
the setup). Everything here was only read; nothing was written to the car.

What each module offered:

- **Body control, APIM (SYNC), ABS, power steering, cluster**: a named view
  ("Module configuration") that opened without a bootloader.
- **Audio**: the named view read its blocks but showed no names.
- **Body control central configuration (CCC)**: opened only after FORScan
  loaded a secondary bootloader (`F1ET-14C025-BB.VBF`) into the module. The
  same bytes can be read without it: see [the CCC byte map](data/focus-2017-ccc-map.txt)
  and "Reading the central configuration" in [ford-focus-2017.md](ford-focus-2017.md).

The named settings sit in the as-built blocks listed in
[focus-2017-asbuilt.txt](data/focus-2017-asbuilt.txt), but FORScan does not show
which bits each one uses. A few can be placed by value alone:

| Setting | Value | Where |
|---|---|---|
| Battery Capacity (Rated), A*h | 56 | body control `DE00` byte 11 = `38` (56) |
| TPM - Number of tires | 4 | body control `DE01` byte 1 = `04` |
| TPM - Placard Pressure Front / Rear, psi | 36 / 36 | body control `DE01` bytes 2 and 3 = `24 24` |

These are matches of value, not proven by changing the setting.

Duplicate names in the tables are separate entries; FORScan lists one per field.

Duplicate names are separate entries (FORScan lists one per as-built field).

## BdyCM — Module configuration
| Setting | Value |
|---|---|
| Alarm Sound Type | Vehicle Horn |
| Ambient Light Sensor | Enabled |
| Approach Light | Enabled |
| Approach Light | Disabled |
| Auto Engine Idle Shutdown | Enabled |
| Auto Light Sensor | Disabled |
| Battery Capacity (Rated), A*h | 56 |
| Battery Charge Curve | Battery less than 760 CCA |
| Battery Type | Incorrect value or not configured |
| Battery Type | T5 56Ah 590 CCA |
| Climate Control Type | Manual A/C |
| Configuration for lost PKE Notification | Disabled |
| Crash Horn | Enabled |
| Defroster LED Control | BCM |
| Double Honk On Leaving Cabine | Disabled |
| Drip Wipe Pause Time | 0 |
| Drip Wipe Pause Time | Disabled |
| Froster Automatic Operation (FAO) Request | Request Acknowledged |
| Fuel Level Sensor connection | BCM |
| Fuel Supply | DECOS |
| Fuel Supply | DECOS |
| Fuel pump | Present |
| Heated Steering Wheel | Disabled |
| Heated Steering Wheel | Level 3 Heating |
| Impact Trigger | Not Present |
| Impact Trigger | Not equipped |
| Keypad | Disabled |
| OBDII Protection Activation | Disabled |
| One Press Global Open | Disabled |
| Profile Personalization | Passive (Non-CGEA 1.3) |
| RVC Connection Type | LIN Connection |
| Rain Sensor Car Code | Disabled |
| Rated Battery Capacity | T5 56Ah 590 CCA |
| Rear Defroster Work Time, min | 0 |
| Rear Window Defroster | Enabled |
| Remote Start | Disabled |
| Smart Front Wiper | Disabled |
| Steering angle sensor | Present |
| Stop and Turn Lamps Type | Separated Stop and Turn Lights |
| TCU Gateway Type | GWM |
| TPM - Auto Learn | Enabled |
| TPM - Market | Combined North America / Rest Of The World |
| TPM - Number of tires | 4 |
| TPM - Placard Pressure Front, psi | 36 |
| TPM - Placard Pressure Rear, psi | 36 |
| TPM - Sensor Auto Range | Enabled |
| TPM - Sensor Pressure Range | Low |
| TPM - Sensor type | MY09 |
| TPM - Signal Receiver | BCM |
| Tailgate Timer | 150 ms |
| Trunk Illumination | Disabled |
| Trunk Illumination | Disabled |
| Unlock HVAC Purge | Disabled |
| Wake Up Active | Gas |
| Wash Activation | Active in Accessory |
| Wash Activation in Accessory mode | Enabled |
| Wash Before Wipe Time | 300 ms |
| Washer Fluid Sensor | Enabled |
| Wiper Auto Park | Disabled |
| Wiper Type | Smart |

## APIM — Module configuration
FORScan detected SYNC version **SYNC 1.1** (it warns to confirm the version before writing; names decode against that version).

| Setting | Value |
|---|---|
| Alternate Audio Gain Set | Disabled |
| Alternative Emergency Call Strategy | Disabled |
| Architecture Type | C1MCA (Europe) |
| Audio Input Jack | Enabled |
| Automatic Gain Control Target Gain, dB | 0 |
| Brand | Ford |
| Country Code | US |
| Display Feature Set | MFD 4 |
| Driver Distraction Rules | Enabled |
| Emergency Call | Enabled |
| Emergency Call Strategy | North America |
| Engine Type | Gasoline/Petrol |
| GPS Messages from MFD | Disabled |
| Global Positioning System Module | Enabled |
| HS1 Forced Sleep | Disabled |
| Language Lock | No Lock |
| Microphone Gain, dB | 0 |
| Mobile Apps | Enabled |
| Rotary Button EFP | Enabled |
| SYNC Services | Disabled |
| USB2 | Enabled |
| VIN Network | PCM |
| Vehicle Health Report | Disabled |
| Voice Radio Control AM/FM | Enabled |
| Voice Radio Control CD | Enabled |
| Voice Radio Control DAB | Disabled |
| Voice Radio Control HD | Disabled |
| Voice Radio Control SDARS | Enabled |

## ABS — Module configuration
| Setting | Value |
|---|---|
| ABS Evacuate and Fill Process Status | Production Line Fill |
| Vehicle Identification Number | (VIN stored in ABS — matches the car; redacted here) |

## PSCM — Module configuration
| Setting | Value |
|---|---|
| Pull Drift Compensation | Enabled |
| Pull Drift Compensation Initial Torque, Nm | 0.00000000 |

## ACM — Module configuration
Read 8 blocks successfully, but FORScan decodes **no named settings** for this ACM — the list is empty. Use the AS BUILT blocks instead.

## IPC — Module configuration
| Setting | Value |
|---|---|
| Adaptive Cruise Control/Forward collision warning | Enabled |
| Adaptive Speed Limiter Device | Enabled |
| Auto High Beam Sensitivity Menu | No Menu (default low) |
| Brake Transmission Shift Interlock | Disabled |
| Chimes - Adaptive Cruise Control / Forward Collision Warning | Enabled |
| Chimes - Adjustable Speed Limiter Diesel | Enabled |
| Chimes - Alarm | Enabled |
| Chimes - Beltminder | Enabled |
| Chimes - Cross Traffic Alert | Enabled |
| Chimes - Door Open | Enabled |
| Chimes - Engine On | Disabled |
| Chimes - Hard Warning | Enabled |
| Chimes - Headlamps On | Enabled |
| Chimes - Hill Start Assist | Enabled |
| Chimes - Home Safe Light | Enabled |
| Chimes - Ignition Off | Enabled |
| Chimes - Information | Enabled |
| Chimes - Key In Ignition | Enabled |
| Chimes - Key Left In Car | Enabled |
| Chimes - Key Outside Car | Enabled |
| Chimes - Liftgate | Disabled |
| Chimes - Low Fuel | Enabled |
| Chimes - Mechanical Park Brake | Enabled |
| Chimes - Memory Seat | Enabled |
| Chimes - Overspeed | Enabled |
| Chimes - PRNDL Not In Park | Enabled |
| Chimes - Parking Brake | Enabled |
| Chimes - Select Shift Press Clutch | Enabled |
| Chimes - Select Shift Select Neutral | Enabled |
| Chimes - Select Shift Turn Ignition Off | Enabled |
| Chimes - Soft Warning | Enabled |
| Climate Control | Disabled |
| Compass | GPS Compass |
| Cross Traffic Alert | Enabled |
| Cruise Control | Enabled |
| Deflation Detection System | Enabled |
| Driver Alert System (DAS) | Enabled |
| Driver Beltminder | Enabled |
| Driver Seat | Disabled |
| Driver Settings Menu - Alarm | Enabled |
| Driver Settings Menu - Ambient Light | Enabled |
| Driver Settings Menu - Auto High Beam | Enabled |
| Driver Settings Menu - Auxiliary Heater | Enabled |
| Driver Settings Menu - Blind Spot Monitoring | Enabled |
| Driver Settings Menu - Compass | Enabled |
| Driver Settings Menu - Cross Traffic Alert | Enabled |
| Driver Settings Menu - Cruise Control | Enabled |
| Driver Settings Menu - Daytime Running Lights | Enabled |
| Driver Settings Menu - Deflation Detection System | Enabled |
| Driver Settings Menu - Dimming | Enabled |
| Driver Settings Menu - Driver Monitor | Enabled |
| Driver Settings Menu - ESP | Enabled |
| Driver Settings Menu - Forward Collision Alert | Enabled |
| Driver Settings Menu - Hill Start Assist | Enabled |
| Driver Settings Menu - Home Light | Enabled |
| Driver Settings Menu - Lane Assist Mode | Enabled |
| Driver Settings Menu - Lane Departure | Enabled |
| Driver Settings Menu - Lane Departure Warning Intensity | Enabled |
| Driver Settings Menu - Measurement Units for Europe | Enabled |
| Driver Settings Menu - MyKey | Enabled |
| Driver Settings Menu - MyKey Miles | Enabled |
| Driver Settings Menu - MyKeys Programmed | Enabled |
| Driver Settings Menu - Navigation Info | Enabled |
| Driver Settings Menu - Parking Heater | Enabled |
| Driver Settings Menu - Rain Sensing | Disabled |
| Driver Settings Menu - Rain and Light sensor | Enabled |
| Driver Settings Menu - Seat Belts | Enabled |
| Driver Settings Menu - Stop / Start | Disabled |
| Driver Settings Menu - Tire Pressure Monitor | Disabled |
| Driver Settings Menu - Traffic Side | Disabled |
| Driver Settings Menu - Traffic Sign Recognition | Enabled |
| Driver Settings Menu - Traffic Sign Recognition Overspeed Warning | Enabled |
| Driver Settings Menu - Vehicle Graphics | Enabled |
| ECO Mode | Enabled |
| ECO Scout | Enabled |
| External Air Temperature | Enabled |
| Ford Logo (MFD 3) | Disabled |
| Ford ST | Disabled |
| Fuel metering in gallons | Enabled |
| Fuel per hour | Disabled |
| Heated Steering Wheel on Remote Start | Disabled |
| Ice indicator | Disabled |
| Indicators - ABS | Enabled |
| Indicators - Airbag Malfunction (RIL) | Enabled |
| Indicators - Auto High Beam Control | Enabled |
| Indicators - Beltminder | Enabled |
| Indicators - Blind Spot Monitoring | Enabled |
| Indicators - Charge System Malfunction | Enabled |
| Indicators - Cruise Control | Enabled |
| Indicators - Diesel Pre-Heat | Enabled |
| Indicators - Distance Alert | Enabled |
| Indicators - Engine Malfunction (MIL) | Enabled |
| Indicators - Forward Collision Warning | Enabled |
| Indicators - Front Fog | Enabled |
| Indicators - Gear Shift | Enabled |
| Indicators - High Beam | Enabled |
| Indicators - Lane Departure Warning | Enabled |
| Indicators - Left Turn | Enabled |
| Indicators - Lights On | Enabled |
| Indicators - Low Fuel Reminder | Enabled |
| Indicators - Parking Brake | Enabled |
| Indicators - Rear Fog | Enabled |
| Indicators - Right Turn | Enabled |
| Indicators - Stability Control | Enabled |
| Indicators - Stability Control Off | Enabled |
| Indicators - Stop / Start | Enabled |
| Indicators - TCS Hill Mode | Enabled |
| Indicators - Tire Pressure Monitor | Enabled |
| Instant Fuel Economy Display | Bar |
| Keyless Control In Settings | Disabled |
| Lane Centering Aid | Enabled |
| Lane Departure Warning | Enabled |
| Lane Keeping Aid | Enabled |
| Languages - Arabic | Disabled |
| Languages - Chinese Simplified | Disabled |
| Languages - Chinese Traditional | Disabled |
| Languages - Czech | Disabled |
| Languages - Danish | Disabled |
| Languages - Dutch | Disabled |
| Languages - English Australian | Disabled |
| Languages - English UK | Disabled |
| Languages - English US | Enabled |
| Languages - French | Disabled |
| Languages - French Canada | Enabled |
| Languages - German | Disabled |
| Languages - Italian | Disabled |
| Languages - Japanese | Disabled |
| Languages - Korean | Disabled |
| Languages - Norwegian | Disabled |
| Languages - Polish | Disabled |
| Languages - Portuguese | Disabled |
| Languages - Portuguese Brazil | Disabled |
| Languages - Russian | Disabled |
| Languages - Spanish | Disabled |
| Languages - Spanish Mexico | Enabled |
| Languages - Swedish | Disabled |
| Languages - Turkish | Disabled |
| Menu - Languages | Enabled |
| Messages - #100 Supplementary heater off | Enabled |
| Messages - #1015 Diesel Engine Start Pending | Enabled |
| Messages - #102 Supplementary heater on | Enabled |
| Messages - #201 High engine temperature | Enabled |
| Messages - #203 Washer fluid Level Low | Enabled |
| Messages - #204 Brake fluid Level Low | Enabled |
| Messages - #212 Driver door open | Enabled |
| Messages - #213 Driver side rear door open | Enabled |
| Messages - #214 Passenger door open | Enabled |
| Messages - #215 Passenger side rear door open | Enabled |
| Messages - #216 Boot / Trunk open | Enabled |
| Messages - #217 Bonnet / Hood open | Enabled |
| Messages - #218d Traction control deactivated | Enabled |
| Messages - #245 Passive keys - key in trunk | Enabled |
| Messages - #250 Powertrain cooling | Disabled |
| Messages - #254 Oil Level Low | Enabled |
| Messages - #350 Electric Parking Brake (EPB) warning - total failure | Enabled |
| Messages - #351c Electric Parking Brake (EPB) warning - park brake not app(lied) | Enabled |
| Messages - #365 TCM - gear engagement info at low temperature | Enabled |
| Messages - #366 TCM - press brake pedal | Enabled |
| Messages - #368 Water in Fuel | Enabled |
| Messages - #400 Tire Pressure Monitor System (TPMS) malfunction | Enabled |
| Messages - #411 Forward Alert (FA) failure - not recoverable | Enabled |
| Messages - #412 Adapive Cruse Control (ACC) Sensor failure - to be cleaned | Enabled |
| Messages - #413 Forward Alert (FA) failure - recoverable | Enabled |
| Messages - #414 Adapive Cruse Control (ACC) Service - not recoverable | Enabled |
| Messages - #415 Adapive Cruse Control (ACC) and Forward Alert (FA) failure | Enabled |
| Messages - #419 Alarm triggered | Enabled |
| Messages - #423 Immobilizer active | Enabled |
| Messages - #427 Hill Start Assist (HSA) active | Enabled |
| Messages - #428 Hill Start Assist (HSA) release | Enabled |
| Messages - #429 Hill Start Assist (HSA) not available | Enabled |
| Messages - #431 Headlamp Low Beam Bulb Fault | Enabled |
| Messages - #432 Rear Fog Lamps Bulb Fault | Enabled |
| Messages - #433 Brake/Stop Lamp Bulb Fault | Enabled |
| Messages - #434 Position Lamps Bulb Fault | Enabled |
| Messages - #435 Head Light System Bulb Fault | Enabled |
| Messages - #436 Trailer Stop Lamps Bulb Fault | Enabled |
| Messages - #437 Trailer Turn Signal Bulb Fault | Enabled |
| Messages - #438 Adaptive Cruise Control (ACC) failure - recoverable | Enabled |
| Messages - #440 Engine malfunction - soft warning | Enabled |
| Messages - #440b Engine malfunction - hard warning | Enabled |
| Messages - #441 IVDC Malfunction | Enabled |
| Messages - #449 Oil service Indication | Enabled |
| Messages - #455 Charging status - overvoltage | Enabled |
| Messages - #456 Charging status - battery low | Disabled |
| Messages - #466 Adaptive Cruise Control (CADS) service required | Enabled |
| Messages - #469 Service Indication - oil change | Enabled |
| Messages - #474 Tire Pressure Monitoring System (TPMS) sensors not dete(cted) | Enabled |
| Messages - #476 Alarm System service required | Enabled |
| Messages - #477 Electric Parking Brake (EPB) - pre-conditions for drive awa(y) | Enabled |
| Messages - #478 Electric Parking Brake (EPB) - releasing by switch and driv(e) | Enabled |
| Messages - #479 Electric Parking Brake (EPB) - service required | Enabled |
| Messages - #480 Electric Parking Brake (EPB) - park brake not fully released | Enabled |
| Messages - #485 Automated Transmission warning - press brake | Enabled |
| Messages - #487 | Enabled |
| Messages - #488 Automated Transmission warning - not in Park | Enabled |
| Messages - #491 Electric Parking Brake (EPB) Status - applied (if telltale blo…) | Enabled |
| Messages - #492 Electric Parking Brake (EPB) Status - released (if telltale bl…) | Enabled |
| Messages - #493 Tire Pressure Monitoring System (TPMS) global warning | Enabled |
| Messages - #494 Keyless Vehicle (KV) - steering malfunction 1 | Enabled |
| Messages - #495 Keyless Vehicle (KV) - steering malfunction 2 | Enabled |
| Messages - #496 Keyless Vehicle (KV) - key not detected | Enabled |
| Messages - #497 Driver Door Open | Enabled |
| Messages - #498 Keyless Vehicle (KV) - key outside car | Enabled |
| Messages - #499 Keyless Vehicle (KV) - press brake | Enabled |
| Messages - #500 Keyless Vehicle (KV) - steering locked | Enabled |
| Messages - #502 Keyless Vehicle (KV) - press clutch | Enabled |
| Messages - #512 Deflation Detection System (DDS) Warning | Enabled |
| Messages - #513 Deflation Detection System (DDS) Fault | Enabled |
| Messages - #516 Driver door open - 2 | Enabled |
| Messages - #517 Passenger door open - 2 | Enabled |
| Messages - #518 Driver side rear door open - 2 | Enabled |
| Messages - #519 Passenger side rear door open - 2 | Enabled |
| Messages - #520 Boot / Trunk open - 2 | Enabled |
| Messages - #521 Bonnet / Hood open - 2 | Enabled |
| Messages - #522 Keyless Vehicle (KV) - Change passive key battery | Enabled |
| Messages - #530 Restraints indicator | Enabled |
| Messages - #531 MPS6 Transmission Heat protection - 0 | Enabled |
| Messages - #532 MPS6 Transmission Heat protection - 1 | Enabled |
| Messages - #533 MPS6 Transmission Heat protection - 2 | Enabled |
| Messages - #534 MPS6 Transmission Heat protection - 3 | Enabled |
| Messages - #567 Immobilizer malfunction | Enabled |
| Messages - #577 Keyless Vehicle (KV) - Engine preheating (Diesel) | Enabled |
| Messages - #582 Hill Start Assist (HSA) release - chime | Enabled |
| Messages - #584 Park assistance failure | Enabled |
| Messages - #586 Mini liftgate open | Enabled |
| Messages - #588 Mini liftgate open | Enabled |
| Messages - #589 Power operated tailgate malfunction | Enabled |
| Messages - #591 Automated Transmission - limited function | Enabled |
| Messages - #600 Electric Power Assist Steering (EPAS) - steering assist not… | Enabled |
| Messages - #601 Electric Power Assist Steering (EPAS) - increased friction | Enabled |
| Messages - #602 Electric Power Assist Steering (EPAS) - malfunction | Enabled |
| Messages - #606 Brake Pad Wear | Enabled |
| Messages - #607 Low Brake Vacuum | Enabled |
| Messages - #608 Secondary brake not available | Enabled |
| Messages - #609 Trailer Sway | Enabled |
| Messages - #610 Blind Spot Monitoring (BLIS) - right sensor blocked | Enabled |
| Messages - #611 Blind Spot Monitoring (BLIS) - left sensor blocked | Enabled |
| Messages - #612 Blind Spot Monitoring (BLIS) - right sensor malfunction | Enabled |
| Messages - #613 Blind Spot Monitoring (BLIS) - left sensor malfunction | Enabled |
| Messages - #614 Blind Spot Monitoring (BLIS) - trailer connected - deactivat(ed) | Enabled |
| Messages - #625 Park brake applied - 1 | Enabled |
| Messages - #626 Park brake applied - 2 | Enabled |
| Messages - #630 Keyless Vehicle (KV) - place key in key holder | Enabled |
| Messages - #632 Keyless Vehicle (KV) - press brake and clutch | Enabled |
| Messages - #633 Keyless Vehicle (KV) - Hold Key next to symbol | Enabled |
| Messages - #640 Start / Stop - Engine starting | Enabled |
| Messages - #641 Start / Stop - press clutch 2 | Enabled |
| Messages - #642 Start / Stop - malfunction | Enabled |
| Messages - #643 Start / Stop - turn ignition off | Enabled |
| Messages - #644 Start / Stop - select neutral | Enabled |
| Messages - #650 Child power lock | Enabled |
| Messages - #651 Belt minder sensor failure | Enabled |
| Messages - #655 One Touch Integrated Start (OTIS) - press brake to start | Enabled |
| Messages - #656 One Touch Integrated Start (OTIS) - press clutch to start | Enabled |
| Messages - #657 One Touch Integrated Start (OTIS) - press clutch and brak(e) | Enabled |
| Messages - #658 One Touch Integrated Start (OTIS) - cranking time exceed(ed) | Enabled |
| Messages - #660 My Key Active - Drive Safely | Enabled |
| Messages - #661 Greeting: Speed Limited to 80 MPH (130 km/h) | Enabled |
| Messages - #662 Greeting: Speed Limited to 130 km/h | Enabled |
| Messages - #665 Check Speed - Drive Safely | Enabled |
| Messages - #666 Vehicle Near Top Speed of MyKey Setting | Enabled |
| Messages - #667 Vehicle at Top Speed of MyKey Setting | Enabled |
| Messages - #670 Buckle Up to Unmute Audio | Enabled |
| Messages - #680 Front camera reduced visibility | Enabled |
| Messages - #681 Lane Departure Warning System (LDWS) Camera malfuncti(on) | Enabled |
| Messages - #682 Front camera not available | Enabled |
| Messages - #685 Lane Departure Warning System malfunction | Enabled |
| Messages - #688 Driver impairment monitor 1st warning | Enabled |
| Messages - #689 Driver impairment monitor 2nd warning | Enabled |
| Messages - #695 Auto High Beam Control (AHBC) on | Enabled |
| Messages - #696 Auto High Beam Control (AHBC) off | Enabled |
| Messages - #710 City Safety auto braking | Enabled |
| Messages - #711 City Safety sensor blocked | Enabled |
| Messages - #712 City Safety malfunction | Enabled |
| Messages - #723 Transmission State | Enabled |
| Messages - #724 Transmission State | Enabled |
| Messages - #725 Transmission Heat Protection | Enabled |
| Messages - #746 Brake system malfunction | Enabled |
| Messages - #760 Remote Start Active | Enabled |
| Messages - #761 Remote Start Passive Entry Passive Start | Enabled |
| Messages - #790 One Touch Integrated Start (OTIS) - engine start pending, … | Enabled |
| Messages - #791 One Touch Integrated Start (OTIS) - engine start cancelled | Enabled |
| Messages - #98 Engine On | Enabled |
| Metric Units Type | L/100 km |
| MyKey Menu - Blind Spot Monitoring | Enabled |
| MyKey Menu - Cross Traffic Alert | Enabled |
| MyKey Menu - Forward Collision Alert | Disabled |
| MyKey Menu - Lane Departure Warning | Disabled |
| Navigation Repeater | Enabled |
| Passenger Beltminder | Enabled |
| Passenger Seat | Disabled |
| RS Feature | Disabled |
| RS Feature - Animation | Base |
| RS Feature - Exhaust Settings | Disabled |
| RS Feature - Launch Control | Disabled |
| RS Feature - Peformance Shift Control | Disabled |
| RS Feature - Selectable Drive Modes | Disabled |
| Rear Defrost | Disabled |
| Rear beltminder | Enabled |
| Remote Start | Enabled |
| Remote Start | Disabled |
| Remote Start - Driver Seat | Disabled |
| Remote Start - Passenger Seat | Disabled |
| Remote Start - Steering Wheel | Disabled |
| Remote Start Front Defrost HVAC | Disabled |
| Remote Start Menu - Climate Mode | Disabled |
| Remote Start Menu - Duration Timer | Disabled |
| Remote Start Menu - Front windows and washer jets defroster | Disabled |
| Remote Start Menu - Quiet Mode On/Off | Disabled |
| Remote Start Menu - Rear windows and mirrors defroster | Disabled |
| Remote Start Menu - Remote Start enable/disable | Disabled |
| Remote Start Menu - Reset to default | Disabled |
| Tire Pressure Monitor | Enabled |
| Trip Computer - All Values | Enabled |
| Trip Computer - Average Fuel Economy | Enabled |
| Trip Computer - Average Speed | Disabled |
| Trip Computer - Digital Speedometer | Enabled |
| Trip Computer - Distance Till Empty | Enabled |
| Trip Computer - Instant Fuel Economy | Enabled |
| Trip Computer - Navigation Repeater | Enabled |
| Trip Computer - Trip Timer | Enabled |
| Trip Computer 1 - Screen A (upper left) | Trip Odometer |
| Trip Computer 1 - Screen B (upper right) | Average Fuel Economy |
| Trip Computer 1 - Screen C (down left) | Instant Fuel Economy |
| Trip Computer 1 - Screen D (down right) | Distance Till Empty |
| Trip Computer 2 - Screen A (upper left) | Trip Odometer |
| Trip Computer 2 - Screen B (upper right) | Average Fuel Economy |
| Trip Computer 2 - Screen C (down left) | Instant Fuel Economy |
| Trip Computer 2 - Screen D (down right) | Distance Till Empty |
| Trip Computer B | Enabled |
| Trip Computer Type | North America |
| Trip Computer Units | Imperial |
| Vehicle Graphics | Enabled |

## BdyCM — Central configuration (Main)  (CCC; read via Secondary Boot Loader F1ET-14C025-BB, read-only)
| Setting | Value |
|---|---|
| Vehicle Identification Number | (redacted) |
| Vehicle Type | Ford Focus US |
| Doors | 4 Door |
| Transmission - driveline | 2 wheel drive |
| Bi-fuel | Not bifuel |
| Engine | 2.0L GDI 160PS |
| Fuel Type | Petrol |
| Alternator | Alternator 150 Amp |
| Steering wheel position | Left hand drive |
| Gearbox | 6-speed Dual Clutch PowerShift |
| Gearbox Type | Powershift |
| Fuel tank volume | Medium tank (Gas/BEV 55L, ST 47L) |
| Alarm | No alarm |
| Headlights, type | Halogen lights with adjuster |
| Daylight running lamps | Always dipped lights except in position P. Adjustable to STDLIGHT (DTRL) |
| Dimmed dipped headlights | With dimmed dipped headlights |
| Foglight Function | No foglight |
| Rear foglight tow function | Foglamps shut off when trailer is connected |
| Trailer Module | Without trailer module |
| Keyless entry and start | Without Keyless Entry and Start |
| Additional heater | Without fuel fire heater |
| Cruise Control | Cruise Control |
| Rain Sensor | Without rain sensor |
| Headlight cleaning | Without headlamp washer |
| Trip computer | With Trip Computer And ECO-scout |
| Private locking trunk | Without private locking |
| Child lock | Manual child lock |
| Unlock Setting | Two step opening with slam lock |
| Acknowledge signal lock/alarm | Lock/unlock acknowledge |
| Automatic locking by speed | Automatic Locking |
| Reset - if alarm | Without retrigger functionality |
| Passive Alarm Activation | Without automatic alarm activate |
| Panic Alarm | Panic Alarm |
| Speed limitation | No speed limit |
| Speed Warning Device | Without speed warning |
| Tire circumference | Rolling circumference 1955 mm |
| Callstart of parking heater | Without callstart of parking heater |
| Parking brake | Manual parking brake |
| Heated windshield | No heated windshield |
| Parking assistance | Without parking assistance |
| Hill Descent Control | Without hill descent control |
| Glass type | Standard windshield glass |
| Octane rating | RON Rating Not Required (Diesel) |
| Body Style | 4 door sedan |
| Tire dimension | 215/55 R 16 H/V/W |
| Final Drive Ratio | 4.278/3.850 |
| Loudspeaker quantities | 6 Speakers |
| Integrated vehicle dynamic control | Enhanced ESP/IVD |
| Towbar | Without trailer tow attachment |
| Phone holder | Without baseplate |
| Wheelbase series and extended length option | 0.8S Series |
| Active suspension | Without continuous controlled chassis |
| Rear view mirrors | Without retractable mirrors |
| Puddle lamp | Without puddle lamp |
| Automatic Lights | Automatic Lights |
| Airbag | Passenger Airbag |
| Cutoff switch passenger airbag | Without cut-off switch for passenger airbag |
| Side airbag (thorax) driver | Side airbag (driver) |
| Side airbag (thorax) passenger | Side airbag (passenger) |
| Language | English (USA) for instruments and radio |
| Forward Collision Warning | Without forward collision warning |
| 12 Volt outlet luggage | Without 12 volt outlet in luggage compartment |
| Tire pressure monitoring system | TPMS with tire sensors 4 wheels |
| Emergency brake lamp | Without emergency brake light |
| Roof Hatch | Without roof opening |
| Power rear windows | Without rear windows |
| Frequency band and step | Frequency band and step for USA |
| Trim level | Cloth |
| In Car Entertainment | Incorrect value or not configured |
| Voice Control | Basic speech recognition |
| Speedometer bias | No speedometer bias |
| Speedometer | MPH -Miles Per Hour |
| Radio, amp and speaker system | Audio 'High Performance' 4*40W, 8 speakers |
| Centre speaker, dashboard | Not configured |
| Subwoofer | Subwoofer |
| Audio auxiliary input | With Auxilliary Audio Input |
| Audio player | Player for 1 CD with MP3 |
| Digital radio receiver | Sirius radio system |
| Microphone | Without micropone |
| Navigation system | Less navigation center |
| Rear wash wipe | Less Rear Wash Wipe |
| Auto Relocking | Without automatic re-locking |
| Audible Mislock Feedback | Audible Mislock And Second Press Lock Feedback |
| Homesafe Lighting | Without Homesafe Lighting |
| Accessory USB unit | With USB and iPod function |
| Traffic information system | No traffic information system |
| Bluetooth handsfree | SYNC G1 (BT-Phone, BT-Audio, SMS), NOT FOR VCC |
| Front Door Warning Lamps | Without front door warning lamps |
| Electronic park brake stall apply | Without stall apply |
| Electronic park brake key out apply | Without key out apply |
| Electronic park brake drive away release | Without drive away release |
| Rear Entertainment System | Without rear entertainment system |
| Speech Control Language | Incorrect value or not configured |
| Engine cooling fan performance | Fan High Performance |
| Global Open/Close | Global open/close disabled |
| Door remote control channel type | Door remote, multichannel, no remote start |
| Audio buttons on steering wheel | With Audio Buttons and MFD Remote Contoller In Steering Wheel |
| City Safety | Without City Safety |
| Mirror Mounted Turn Signal Indicator | Mirror Mounted Turn Signal Indicator |
| Fuel Pump | With small fuel pump |
| Taillamps | Taillamps Level 1: Standard Rear Combination Lamp |
| Reverse Gear Chime | Less Reverse Gear Chime |
| Retractable running board | Not configured |
| Battery | T5 56Ah 590 CCA |
| Battery Monitor Sensor | With Battery Monitor Sensor |
| Ambient aestetic light | Without ambient lighting |
| Language Region | North America |
| Stop Start | Without Stop/Start |
| Adjustable Speed Limiter | Without ASL |
| Active Grill Shutter | With Active Grill Shutter |
| MyKey | With MyKey |
| Traffic Sign Recognition | Less Traffic Sign Recognition |
| Remote Start | Without Remote Start |
| Shifter Type | Less Manual Shifter Auto Trans |

### BdyCM Central configuration — extra rows shown only in "Engineering 2 (+ hidden)" mode
(Listed in FORScan's order; rows already in the Normal table above are left out.)

| Setting | Value |
|---|---|
| Header data length | 57 |
| Car configuration document number | 0031827371 |
| Car configuration issue number | 005 |
| Carriage return / line feed (separators between header fields) | 0D0A |
| Factory order number | 000000000000000000 |
| Type | 000000 |
| Chassis | 000000000000 |
| Factory Code | 0000 |
| Structure Week | 000000000000 |
| Package Identity | 0000…0000 (all zero) |
| EUCD reserved data | 0000…0000 (all zero) |
| EUCD vehicle information | 0000…0000 (all zero) |
| Spare - reserved for future use (after Alarm) | 00 |
| Headlamps | US symmetry |
| Power steering type | Electro Power Steering |
| Level sensor - if alarm | Without level sensor |
| Blind spot information system | Without blind spot information system |
| Road friction detection | Without road friction detection |
| PTC heater (supplementary air heater) | Without PTC heater |
| Battery (rear) | No rear battery |
| Coupe filter | Pollen filter |
| Climate control unit | Air conditioning |
| Instrument Cluster Calibration | Parameter file for US |
| Wheel brakes type front | Incorrect value or not configured |
| Interior motion sensor | Without interior movement sensor |
| Heartbeat sensor | Without heartbeat sensor |
| Heated rear seat | Without heated rear seat |
| Telephone | Without telephone |
| Service interval | User Defined Service interval |
| Seat heat calibration | Without heated seats |
| Heated front seats | Without heated front seat |
| Front seat ventilation | Without ventilated front seats |
| Safety belt reminder | US type including key warning |
| Brand | Ford North America |
| Frequency - remote controls | Frequency 434MHz |
| Air condition, rear | Without rear air conditioning |
| Roof type | Conventional roof |
| Emission standard | Incorrect value or not configured |
| Navigation/traveler assistance | Less Navigation Centre |
| Suspension | With standard suspension |
| Driven axle | Front wheel drive |
| Rear wheel type | Single Rear Wheels |
| Steering gear | Standard steering gear |
| Central lock, type | Without burglarproof locks |
| Side windows | Tempered side windows |
| Memory function | Without memory |
| Electric car heater | Without electric car heater |
| Cupe ventilation with park heater | Without timer controlled cupe ventilation |
| Collision mitigation by braking | Without Collision Mitigation by Braking |
| Lane departure warning | Without lane departure warning |
| Park assist camera | Park assist camera |
| Oil level sensor | Without oil level sensor |
| Roll stability control | Without roll stability control |
| El. vacuum pump, rear booster - not used | Incorrect value or not configured |
| Wheel brakes type rear | Small integrated brake caliper, solid disc, HOPB |
| Auxiliary lights | Without auxiliary lights |
| Speed lock | No speed lock |
| Cluster level | High level (TFT) |
| Tachograph | Without Tachograph |
| Headphone sockets, rear | Without headphone sockets |
| Parking brake switch | Without parking brake warning lamp |
| Terrain response fitment | Without Terrain Response |
| PAM scan pattern | Not configured |
| Front passenger seatbelt reminder | Belt minder, driver and passenger |
| Driver knee bolster | Without driver knee inflatable bolster |
| Side curtain airbags | Without side curtain airbags |
| Airbag, driver side | Driver airbag |
| Front active seat belt retractor pretensioner | Active seat belts |
| Seat belt warning | Seat belt warning device |
| Left hand side load door | Without left hand side load door |
| Right hand side load door | Without right hand side load door |
| Rear opening | Liftgate |
| Bulkhead | Without bulkhead |
| Rear Glazing | No Rear Glass |
| Roof height | Low |
| Power/Heated Mirrors | Short arm power not heated mirrors |
| Zonal opposite door locking | Without zonal opposite door locking |
| Configurable Unlocking | Without Configurable Unlocking |
| Air quality sensor | Without air quality sensor |
| Emissions - Evaporation system | No evaporation system |
| Folding rear headrests | Manual folding rear headrests |
| External alarm unit supply | Without external alarm unit |
| Occupant weight sensor (OWS) | No OWS |
| Rear belt detection | Without Rear Belt Detection |
| Pyrotechnical steeing column | Not configured |
| Adaptive load limiter front | No load limiter |
| Seat track sensors, front | With driver+passenger seat track sensors |
| Lap belt pretensioners, front | No lap belt pretensioners |
| Front crash sensing system | Front crash sensing system, low speed |
| Adaptive seat ventilation, front | No adaptive seat ventilation |
| Battery Saver Time | No timer |
| Heated steering wheel | Without heated steering wheel |
| Touchscreen - N/A | With Display, No Touchscreen, Colour, MFD 4 |
| TV Tuner | Without TV tuner |
| Self opening boot / tailgate | Without self opening boot / tailgate |
| Shift indication | Shift indication |
| Neutral control function | Without neutral control function |
| Rpm Speed Controller | No RPM speed controller |
| Damp sensor - not used | Incorrect value or not configured |
| Asthma and allergy clean zone - not used | Incorrect value or not configured |
| Trip computer mixed units | Not configured |
| Handsfree telemute function | Not configured |
| Wide Body Pack | Incorrect value or not configured |
| Key code | Key-code not activated |
| Driver Impairment Monitor | Without Driver Impairment Monitor |
| Remote Lock With Open Doors | Not configured |
| Alcohol Interlock | Not configured |
| Column Stalk radio controls | Not configured |
| Trailer Stability Assist | Without Trailer Stability Assist |
| Seats | Not configured |
| Sun Sensor | Not configured |
| Wheel Speed Sensor Type | Wheel Speed Sensor Type Without Direction Recognition |
| Racing Sub Brand | Not configured |
| Night Vision - not used | Not configured |
| Front park camera | Not configured |
| Lockable steering column | Without lockable steering column |
| Intelligent Control System (IDIS) | Not configured |
| DVD region | Not configured |
| Unit Setting - not used | Not configured |
| Integrated Control Panel (ICP) | Extended ICP |
| Infotainment Theft Protection | Not configured |
| Picture Support | Not configured |
| Hill Launch Assist | With Hill Launch Assist |
| Side Camera | Not configured |
| Rear power seats | Not configured |
| Inner Rear View Mirror Type - not used | Not configured |
| After Theft Stolen Vehicle Recovery - not used | Not configured |
| Lock Status Indication Config - not used | Incorrect value or not configured |
| Service Engine Time - not used | Not configured |
| Service Distance - not used | Not configured |
| Service Time - not used | Not configured |
| Fuel Tank table | Incorrect value or not configured |
| Steering Gears C Factor | Standard steering C-factor |
| Key code (×16 placeholder rows scattered through the list) | Not configured |
| RCM aux id - byte 1 | 65 |
| RCM aux id - byte 2 | 81 |
| EUCD padding byte 01 | 00 |
| EUCD padding byte 02 | 00 |

## Fault codes
**Before the BCM bootloader session (15:12):** only `IPC U0073:88-28` (control module communication bus "A" off).

**After it (15:24)** — new codes; the PCM freeze frame dates P193E to 15:20:13, one second after the SBL session began with the engine idling (801 rpm, 14.0 V). The BCM went silent on the bus while in bootloader, so these are almost certainly side effects of that session, not new faults:

| Module | Code | Meaning |
|---|---|---|
| OBD2 (PCM) | P025A-P | Fuel Pump Module Control Circuit Open — pending |
| PCM | P025A:00-64 | Fuel Pump Module Control Circuit Open |
| PCM | P193E:00-6C | A/C Clutch Request Signal (maturing/intermittent, MIL off) |
| PCM | U0109:00-64 | Lost communication with fuel pump control module |
| APIM | U0140:00-08 | Lost communication with BCM |
| APIM | U016A:00-08 | Lost communication (module per Ford table) |
| ABS | U0140:00-28 | Lost communication with BCM |
| IPC | U0073:88-28 | Communication bus A off (was present before) |
| IPC | U0140:00-2C | Lost communication with BCM |
| IPC | U0121:00-2C | Lost communication with ABS |
| IPC | U0151:00-2C | Lost communication with RCM |
| IPC | U0101:00-2C | Lost communication with TCM |
| IPC | U0100:00-6C | Lost communication with PCM |
| GPSM | U0140:00-88 | Lost communication with BCM |

All 15 modules (BdyCM included) answered the DTC read afterwards, so the BCM left bootloader mode normally.

At 15:33 all codes were cleared (FORScan's "Clear DTC", then an ignition cycle). A re-read showed none on any module, U0073 included.

## Module addresses (from docs/data/focus-2017-asbuilt.txt in the repo; reply = address + 8)
- BdyCM (body control)  address 726  reply 72E  bus HS-CAN 500k
- PCM (engine)  address 7E0  reply 7E8  bus HS-CAN 500k
- APIM (SYNC)  address 7D0  reply 7D8  bus HS-CAN 500k
- ABS  address 760  reply 768  bus HS-CAN 500k
- RCM (airbag)  address 737  reply 73F  bus HS-CAN 500k
- PSCM (power steering)  address 730  reply 738  bus HS-CAN 500k
- FCDIM (display)  address 7A5  reply 7AD  bus MS-CAN 125k
- ACM (audio)  address 727  reply 72F  bus MS-CAN 125k
- IPC (instrument cluster)  address 720  reply 728  bus MS-CAN 125k
- GPSM (GPS)  address 701  reply 709  bus MS-CAN 125k

