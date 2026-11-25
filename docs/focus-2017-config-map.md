# Where FORScan's named settings live: 2017 Ford Focus

Every setting in FORScan's "Module configuration" view for the body control
module (`726`) and the instrument cluster (`720`), with the configuration block,
byte and bits it occupies and what each value means. Read with
`22 <block>` to the module, as in [ford-focus-2017.md](ford-focus-2017.md); the
reply is `62 <block>` and then the block's bytes, numbered from 0 below.

The same data, for programs: [data/focus-2017-config-map.json](data/focus-2017-config-map.json).

## How this was found

Nothing was written to the car. FORScan 2.3.72 was driven, one setting at a
time, through [`../tools/forscan_dryrun_relay.py`](../tools/forscan_dryrun_relay.py),
which answers FORScan's block writes itself and logs what FORScan meant to
write. For each setting the script in [`../tools/forscan_sweep/`](../tools/forscan_sweep/)
picked a value other than the current one, pressed Write, and recorded which
bits changed. Most of the run used the relay's `--replay` mode: FORScan was
answered from recordings of the car, so the car was not needed.

The field width comes from the option numbers FORScan lists (options 0–7 make
a three-bit field); its position from the bits that changed and, where it could
be checked, from this car's current value. Each setting's option list was read
off FORScan's editor by OCR, so a label can carry a typo ("%ehicle Horn" is
"Vehicle Horn"); long lists show only the options visible without scrolling.

Things to know when reading the table:

- **Repeated names are one field read two ways.** FORScan carries alternative
  definitions (for other model years or markets) and lists all of them. Each
  pair was checked: both rows change the same bits, with their own labels
  (the two "Approach Light" rows have 0 and 1 swapped). Use the one whose
  value on this car makes sense.
- **Some different names share a field for the same reason**: "Configuration
  for lost PKE Notification" and "Double Honk On Leaving Cabine" (`DE00` byte 1
  bit 7); in the cluster, "Driver Seat" and "Remote Start - Driver Seat", and
  the other "Remote Start …" pairs in `DE23`.
- **"Remote Start" in the cluster** switches several menu bits at once (`DE23`
  byte 0 bits 6, 2, 1, 0): it is a master switch that FORScan applies to the
  menu entries.
- **"(guess)"** marks a field whose position could not be pinned by the checks
  above; the bit that changed is right, the field's extent may not be.
- **Not mapped** (body control): settings whose editor is a number box rather
  than a list. Two can be placed by value alone: the tyre count and placard
  pressures are `DE01` bytes 1, 2 and 3 (`04 24 24` = 4 tyres, 36 psi), and the
  rated battery capacity is `DE00` byte 11 in amp-hours (`38` = 56 Ah), which
  "Rated Battery Capacity" confirms.
- 17 of the cluster's shared-bit entries and the entries above were checked by
  reading the editor's own description back; the rest rely on the filter
  having picked the right row, which the checks found it did except where a
  setting's value also matched the filter text.

## BdyCM (`726`)

| Setting | Block | Byte | Bits | This car | Values |
|---|---|---|---|---|---|
| Alarm Sound Type | DE00 | 2 | 7 | Vehicle Horn | 0=%ehicle Horn, 1=Security Horn |
| Ambient Light Sensor | DE00 | 6 | 7 | Enabled | 0=Enabled, 1=Disabled |
| Approach Light | DE00 | 35 | 5 | Enabled | 0=Enabled, 1=Disabled |
| Approach Light | DE00 | 35 | 5 | Disabled | 0=Disabled, 1=Enabled |
| Auto Engine Idle Shutdown | DE00 | 12 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Auto Light Sensor | DE00 | 6 | 6 | Disabled | 0=Disabled, 1=Enabled |
| Battery Capacity (Rated), A*h | | | | 56 | not mapped: editor is not a list |
| Battery Charge Curve | DE00 | 10 | 1–0 | Battery less than 760 CCA | 1=Battery less than 760 CCaA, 2=Battery greater than or equal io 760 CCA |
| Battery Type | DE00 | 9 | 4–0 | Incorrect value or not configured | 1=H& AGM 704h 760 CCA 9MSM-10655-4*, 2=H7 AGM 804K 800 CCA DVET-10655-B*, 7=T4 434h 390 CCA 8G9M-10655-L*, 8=TS 524h 500 CCA BGE9N-10655-M*, AV2T-10655-B*, CH15-10655-C*, 9=TH 604N 590 CCA BEIN-10655-M*, AVZT-10655-C*, AR39-10655-0*, 10=T7 80Ah 700 CCA BGON-10655-P*, AVZ2T-10655-0*, 12=TS 564K 590 CCA CRIT-10655-B*, 17=TS 48Ah 500 CCA CR3T-10655-A*, 18=Incorrect value or not configured, 20=T IF 60Ah 590 CCA BYEN-10655-A%, DYAT-10655-A*, 21=T7 IF 75Ah 700 CCA BVEMN-10655-B*, CC1T-10655-B*, 22=T7 IF 75Ah 700 CCA GW4T-10655-B, 28=T7 IF 65Ah 760 CCA |XAT-10655-FA |
| Battery Type | DE00 | 9 | 4–0 | T5 56Ah 590 CCA | 1=He AGM 704h 750 CCA, 17=TS 484h 500 CCA, 18=TS Sah 590 CCA, 19=T4 434h 390 CCA |
| Climate Control Type | DE00 | 20 | 5–3 | Manual A/C | 0=Default, 1=Manual A4C, 2=Manual CAMN &/C, 3=EATC, 4=Mo AfC, 5=Type S, 6=Type 6 |
| Configuration for lost PKE Notification | DE00 | 1 | 7 | Disabled | 0=Disabled, 1=Enabled |
| Crash Horn | DE00 | 4 | 7–6 | Enabled | 0=Mot Available, 1=Enabled, 2=Disabled, 3=Mot Used |
| Defroster LED Control | DE00 | 3 | 6 | BCM | 0=BCM, 1=EATC |
| Double Honk On Leaving Cabine | DE00 | 1 | 7 | Disabled | 0=Disabled, 1=Enabled |
| Drip Wipe Pause Time | | | | 0 | not mapped: editor is not a list |
| Drip Wipe Pause Time | DE00 | 1 | 4–0 | Disabled | 0=Disabled, 20=Seconds |
| Froster Automatic Operation (FAO) Request | DE00 | 2 | 0 | Request Acknowledged | 0=IGMNORE, 1=Request Acknowledged I |
| Fuel Level Sensor connection | DE00 | 19 | 6 | BCM | 0=BCM, 1=Fuel Level Control Module {FLCR) |
| Fuel Supply | DE00 | 16 | 1–0 | DECOS | 1=Standard, 2=DECOS |
| Fuel Supply | DE00 | 16 | 1–0 | DECOS | 0=Default, 1=Standard, 2=DECOS, 3=Active Diesel |
| Fuel pump | DE00 | 17 | 1–0 | Present | 0=Default, 1=Present, 2=Mot Present |
| Heated Steering Wheel | DE00 | 9 | 5 (guess) | Disabled | 1=Enabled, 2=Enabled with soft switch, 3=A [ P R [ (N RN ul SN S (RN [N S SR |
| Heated Steering Wheel | DE00 | 31 | 1–0 | Level 3 Heating | 0=DEFALLT, 1=Level 1 Heating, 2=Level 2 Heating, 3=Level 3 Heating |
| Impact Trigger | DE00 | 18 | 1–0 | Not Present | 0=Default, 1=Present, 2=Mot Present |
| Impact Trigger | DE00 | 18 | 1–0 | Not equipped | 0=Incorrect value or not configured, 1=Equipped, 2=Mot equipped |
| Keypad | DE00 | 20 | 2 | Disabled | 0=Disabled, 1=Enabled |
| OBDII Protection Activation | | | | Disabled | not mapped: editor is not a list |
| One Press Global Open | DE00 | 7 | 6 | Disabled | 0=Disabled, 1=Enabled |
| Profile Personalization | DE00 | 20 | 6 | Passive (Non-CGEA 1.3) | 0=Passive (Mon-CGEA 1.3), 1=Manual {CGEA 1.3) |
| RVC Connection Type | DE00 | 25 | 7 | LIN Connection | 0=CaAl Connection, 1=LIN Connection |
| Rain Sensor Car Code | DE00 | 5 | 3–0 | Disabled | 0=Disabled, 10=IR Protected, 13=CMaX Standard Windshield |
| Rated Battery Capacity | DE00 | 11 | 6–0 | T5 56Ah 590 CCA | 43=T4 434h 390 CCA, 48=TS 484h 500 CCA, 56=TS 3640 590 CCA, 70=HE AGM 704h 750 CCA |
| Rear Defroster Work Time, min | DE00 | 10 | 1–0 | 0 | 1=Battery less than 760 CCaA, 2=Battery greater than or equal io 760 CCA |
| Rear Window Defroster | DE00 | 3 | 4 | Enabled | 0=Enabled, 1=Disabled |
| Remote Start | DE05 | 0 | 0 | Disabled | 0=Disabled, 1=Enabled |
| Smart Front Wiper | DE00 | 0 | 1 | Disabled | 0=Disabled, 1=Enabled |
| Steering angle sensor | DE00 | 25 | 4 | Present | 0=Mot Present, 1=Present |
| Stop and Turn Lamps Type | DE00 | 42 | 0 | Separated Stop and Turn Lights | 0=Separated Stop and Turn Lights, 1=Cambined Stop and Turn Lights |
| TCU Gateway Type | DE00 | 20 | 7 | GWM | 0=G, 1=1IPC |
| TPM - Auto Learn | DE02 | 0 | 0 | Enabled | 0=Disabled, 1=Enabled |
| TPM - Market | DE00 | 3 | 2 | Combined North America / Rest Of The World | 0=Maorth America, 1=Combined Morth America f Rest Of The \World |
| TPM - Number of tires | | | | 4 | not mapped: editor is not a list |
| TPM - Placard Pressure Front, psi | | | | 36 | not mapped: editor is not a list |
| TPM - Placard Pressure Rear, psi | | | | 36 | not mapped: editor is not a list |
| TPM - Sensor Auto Range | DE02 | 1 | 0 | Enabled | 0=Disabled, 1=Enabled |
| TPM - Sensor Pressure Range | DE03 | 1 | 0 | Low | 0=Low, 1=High |
| TPM - Sensor type | DE03 | 0 | 1–0 | MY09 | 0=MY0&, 1=M09, 2=MY15, 3=Heavy Truck |
| TPM - Signal Receiver | DE00 | 3 | 1–0 | BCM | 0=BCM, 1=kMM, 2=IRX |
| Tailgate Timer | | | | 150 ms | not mapped: editor is not a list |
| Trunk Illumination | DE00 | 2 | 1 | Disabled | 0=Disabled, 1=Enabled |
| Trunk Illumination | DE00 | 2 | 1 | Disabled | 0=Disabled, 1=Enabled |
| Unlock HVAC Purge | DE00 | 18 | 6 | Disabled | 0=Disabled, 1=Enabled |
| Wake Up Active | DE00 | 8 | 4–0 | Gas | 0=Gas, 20=Focus BEY [/ CMAX |
| Wash Activation | DE00 | 0 | 3 | Active in Accessory | 0=Active in AcCessary, 1=Mot Active in Accessory |
| Wash Activation in Accessory mode | DE00 | 0 | 3 | Enabled | 0=Enabled, 1=Disabled |
| Wash Before Wipe Time | | | | 300 ms | not mapped: editor is not a list |
| Washer Fluid Sensor | DE00 | 12 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Wiper Auto Park | DE00 | 16 | 7 | Disabled | 0=Disabled, 1=Enabled |
| Wiper Type | DE00 | 0 | 0 | Smart | 0=Conwventional, 1=5Smart |

## IPC (`720`)

| Setting | Block | Byte | Bits | This car | Values |
|---|---|---|---|---|---|
| Adaptive Cruise Control/Forward collision warning | DE1B | 0 | 1 | Enabled | 0=abled s, 1=hled |
| Adaptive Speed Limiter Device | DE1B | 0 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Auto High Beam Sensitivity Menu | DE07 | 0 | 1–0 | No Menu (default low) | 0=Mo Menu {default low), 1=Mo Menu (default normal), 2=With menu |
| Brake Transmission Shift Interlock | DE1B | 1 | 7 | Disabled | 0=Disabled, 1=Enabled |
| Chimes - Adaptive Cruise Control / Forward Collision Warning | DE11 | 1 | 3 (guess) | Enabled | 0=| Chimes - Adaptive Cruise Contral / Forward Callision \Warning | |
| Chimes - Adjustable Speed Limiter Diesel | DE11 | 1 | 5 | Enabled | 0=Disabled, 1=Enabled I |
| Chimes - Alarm | DE11 | 2 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Beltminder | DE11 | 1 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Cross Traffic Alert | DE11 | 3 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Door Open | DE11 | 2 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Engine On | DE11 | 3 | 0 | Disabled | 0=Disabled, 1=Enahled Chimes - Engine On |
| Chimes - Hard Warning | DE11 | 0 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Headlamps On | DE11 | 0 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Hill Start Assist | DE11 | 1 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Home Safe Light | DE11 | 0 | 5 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Ignition Off | DE11 | 1 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Information | DE11 | 0 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Key In Ignition | DE11 | 2 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Key Left In Car | DE11 | 2 | 5 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Key Outside Car | DE11 | 1 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Liftgate | DE1B | 2 | 2 | Disabled | 0=Disabled, 1=Enabled |
| Chimes - Low Fuel | DE11 | 0 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Mechanical Park Brake | DE11 | 2 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Memory Seat | DE11 | 1 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Overspeed | DE11 | 1 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - PRNDL Not In Park | DE11 | 0 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Parking Brake | DE1B | 0 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Select Shift Press Clutch | DE11 | 2 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Select Shift Select Neutral | DE11 | 2 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Chimes - Select Shift Turn Ignition Off | DE11 | 2 | 3 (guess) | Enabled | 1=Enabled |
| Chimes - Soft Warning | DE11 | 0 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Climate Control | DE23 | 0 | 3 | Disabled | 0=Disabled, 1=Enabled |
| Compass | DE07 | 0 | 3–2 | GPS Compass | 0=Mone, 1=LIM Compass, 2=GPS Compass, 3=MFDS GPS Compass |
| Cross Traffic Alert | DE1B | 2 | 3 | Enabled | 0=Disabled, 1=Enabled |
| Cruise Control | DE1B | 0 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Deflation Detection System | DE1B | 0 | 3 | Enabled | 0=Disabled, 1=Enabled |
| Driver Alert System (DAS) | DE1B | 0 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Driver Beltminder | DE1A | 0 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Driver Seat | DE23 | 1 | 1 | Disabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Alarm | DE22 | 2 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Ambient Light | DE22 | 2 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Auto High Beam | DE22 | 1 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Auxiliary Heater | DE22 | 2 | 5 (guess) | Enabled | 1=Enabled |
| Driver Settings Menu - Blind Spot Monitoring | DE22 | 1 | 3 | Enabled | 0=Disabled, 1=Enabled . |
| Driver Settings Menu - Compass | DE22 | 2 | 3 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Cross Traffic Alert | DE21 | 0 | 2 | Enabled | 0=Disabled, 1=Enabled I |
| Driver Settings Menu - Cruise Control | DE21 | 1 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Daytime Running Lights | DE21 | 0 | 1 | Enabled | 0=Disabled, 1=“habled . |
| Driver Settings Menu - Deflation Detection System | DE22 | 0 | 0 | Enabled | 0=abled, 1=bled B |
| Driver Settings Menu - Dimming | DE22 | 2 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Driver Monitor | DE22 | 0 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - ESP | DE22 | 1 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Forward Collision Alert | DE22 | 3 | 0 | Enabled | 0=isabled, 1=nabled - |
| Driver Settings Menu - Hill Start Assist | DE22 | 1 | 5 | Enabled | 0=Disabled, 1=Enabled I |
| Driver Settings Menu - Home Light | DE22 | 2 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Lane Assist Mode | DE22 | 0 | 4 (guess) | Enabled | 1=Enabled |
| Driver Settings Menu - Lane Departure | DE22 | 0 | 3 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Lane Departure Warning Intensity | DE22 | 0 | 5 | Enabled | 0=] E———...,, 1=| Driver Settings Menu - Lane Departure \Warning Intensity | |
| Driver Settings Menu - Measurement Units for Europe | DE22 | 3 | 6 | Enabled | 0=hled, 1=a]/=ls| - |
| Driver Settings Menu - MyKey | DE22 | 0 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - MyKey Miles | DE22 | 1 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - MyKeys Programmed | DE22 | 1 | 1 | Enabled | 0=Disabled, 1=Enabled I |
| Driver Settings Menu - Navigation Info | DE22 | 2 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Parking Heater | DE22 | 2 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Rain Sensing | DE05 | 2 | 5 | Disabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Rain and Light sensor | DE22 | 1 | 7 | Enabled | 0=Disabled, 1=Enabled . |
| Driver Settings Menu - Seat Belts | DE22 | 0 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Stop / Start | DE21 | 0 | 3 | Disabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Tire Pressure Monitor | DE22 | 0 | 2 | Disabled | 0=Disabled ., 1=Enabled |
| Driver Settings Menu - Traffic Side | DE05 | 2 | 3 | Disabled | 0=Disabled, 1=Enabled |
| Driver Settings Menu - Traffic Sign Recognition | DE22 | 3 | 1 | Enabled | 0=sabled, 1=1abled - |
| Driver Settings Menu - Traffic Sign Recognition Overspeed Warning | DE22 | 3 | 2 (guess) | Enabled | 0=river Settings Menu - Traffic Sign Recognition Overspeed \Warning |
| Driver Settings Menu - Vehicle Graphics | DE21 | 0 | 4 (guess) | Enabled | 1=Enabled |
| ECO Mode | DE02 | 0 | 5 | Enabled | 0=Disabled, 1=Enabled |
| ECO Scout | DE1B | 0 | 5 | Enabled | 0=Disabled, 1=Enabled |
| External Air Temperature | DE02 | 1 | 3 | Enabled | 0=Disabled, 1=Enabled |
| Ford Logo (MFD 3) | DE05 | 2 | 4 | Disabled | 0=Disabled, 1=Enabled |
| Ford ST | DE1B | 1 | 6 | Disabled | 0=Disabled, 1=Enabled |
| Fuel metering in gallons | DE02 | 1 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Fuel per hour | DE02 | 1 | 4 | Disabled | 0=Disabled, 1=Enabled |
| Heated Steering Wheel on Remote Start | DE23 | 0 | 7 | Disabled | 0=Disabled, 1=Enabled |
| Ice indicator | DE02 | 1 | 2 | Disabled | 0=Disabled, 1=Enabled |
| Indicators - ABS | DE10 | 0 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Airbag Malfunction (RIL) | DE10 | 0 | 5 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Auto High Beam Control | DE10 | 3 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Beltminder | DE10 | 0 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Blind Spot Monitoring | DE10 | 2 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Charge System Malfunction | DE10 | 0 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Cruise Control | DE10 | 1 | 5 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Diesel Pre-Heat | DE10 | 2 | 3 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Distance Alert | DE10 | 0 | 3 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Engine Malfunction (MIL) | DE10 | 0 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Forward Collision Warning | DE10 | 3 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Front Fog | DE10 | 1 | 3 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Gear Shift | DE1B | 0 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - High Beam | DE10 | 0 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Lane Departure Warning | DE10 | 3 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Left Turn | DE10 | 1 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Lights On | DE10 | 1 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Low Fuel Reminder | DE10 | 1 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Parking Brake | DE10 | 0 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Rear Fog | DE10 | 1 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Right Turn | DE10 | 1 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Stability Control | DE10 | 2 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Stability Control Off | DE10 | 2 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Stop / Start | DE10 | 1 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - TCS Hill Mode | DE10 | 3 | 3 | Enabled | 0=Disabled, 1=Enabled |
| Indicators - Tire Pressure Monitor | DE10 | 2 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Instant Fuel Economy Display | DE02 | 1 | 5 | Bar | 0=Bar, 1=Mumeric |
| Keyless Control In Settings | DE05 | 1 | 4 | Disabled | 0=Disabled, 1=Enabled |
| Lane Centering Aid | DE1B | 1 | 3 | Enabled | 0=Disabled, 1=Enabled |
| Lane Departure Warning | DE1B | 1 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Lane Keeping Aid | DE1B | 1 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Languages - Arabic | DE00 | 2 | 4 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Chinese Simplified | DE00 | 3 | 4 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Chinese Traditional | DE00 | 3 | 7 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Czech | DE00 | 2 | 1 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Danish | DE00 | 2 | 2 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Dutch | DE00 | 1 | 4 | Disabled | 0=Disabled, 1=Enabled |
| Languages - English Australian | DE00 | 0 | 3 | Disabled | 0=Disabled, 1=Enabled |
| Languages - English UK | DE00 | 0 | 2 | Disabled | 0=Disabled, 1=Enabled |
| Languages - English US | DE00 | 0 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Languages - French | DE00 | 0 | 7 | Disabled | 0=Disabled, 1=Enabled |
| Languages - French Canada | DE00 | 0 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Languages - German | DE00 | 0 | 4 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Italian | DE00 | 0 | 5 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Japanese | DE00 | 3 | 5 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Korean | DE00 | 3 | 6 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Norwegian | DE00 | 2 | 3 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Polish | DE00 | 1 | 5 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Portuguese | DE00 | 2 | 0 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Portuguese Brazil | DE00 | 1 | 7 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Russian | DE00 | 1 | 3 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Spanish | DE00 | 1 | 1 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Spanish Mexico | DE00 | 1 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Languages - Swedish | DE00 | 1 | 6 | Disabled | 0=Disabled, 1=Enabled |
| Languages - Turkish | DE00 | 1 | 2 | Disabled | 0=Disabled, 1=Enabled |
| Menu - Languages | DE00 | 0 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #100 Supplementary heater off | DE12 | 0 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #1015 Diesel Engine Start Pending | DE14 | 1 | 6 | Enabled | 0=Disabled, 1=Enabled . |
| Messages - #102 Supplementary heater on | DE12 | 0 | 1 (guess) | Enabled | 1=Enabled |
| Messages - #201 High engine temperature | DE12 | 0 | 2 (guess) | Enabled | 1=Enabled |
| Messages - #203 Washer fluid Level Low | DE12 | 0 | 3 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #204 Brake fluid Level Low | DE12 | 0 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #212 Driver door open | DE12 | 0 | 5 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #213 Driver side rear door open | DE12 | 0 | 6 | Enabled | 0=Disabled, 1=Enabled I |
| Messages - #214 Passenger door open | DE12 | 0 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #215 Passenger side rear door open | DE12 | 1 | 0 | Enabled | 0=Disabled, 1=“habled . |
| Messages - #216 Boot / Trunk open | DE12 | 1 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #217 Bonnet / Hood open | DE12 | 1 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #218d Traction control deactivated | DE15 | 3 | 7 | Enabled | 0=Disabled, 1=“habled . |
| Messages - #245 Passive keys - key in trunk | DE12 | 1 | 3 | Enabled | 0=Disabled, 1=Enabled l |
| Messages - #250 Powertrain cooling | DE16 | 0 | 6 | Disabled | 0=Disabled, 1=Enabled |
| Messages - #254 Oil Level Low | DE12 | 1 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #350 Electric Parking Brake (EPB) warning - total failure | DE12 | 1 | 5 (guess) | Enabled | 0=lessages - #3950 Electric Parking Brake (EPR) warning - total failure |
| Messages - #351c Electric Parking Brake (EPB) warning - park brake not app(lied) | DE16 | 0 | 0 (guess) | Enabled | 25=#351c Electric Parking Brake (EPB) warning - park brake not app |
| Messages - #365 TCM - gear engagement info at low temperature | DE12 | 1 | 6 (guess) | Enabled | 0=Ylessages - #365 TCM - gear engagement info at low temperature |
| Messages - #366 TCM - press brake pedal | DE12 | 1 | 7 (guess) | Enabled | 1=Enabled |
| Messages - #368 Water in Fuel | DE12 | 2 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #400 Tire Pressure Monitor System (TPMS) malfunction | DE12 | 2 | 1 (guess) | Enabled | 0=lessages - #400 Tire Pressure Monitor System (TPMS) malfunction |
| Messages - #411 Forward Alert (FA) failure - not recoverable | DE12 | 2 | 2 (guess) | Enabled | 0=| Messages - #411 Forward Alert (FA) failure - not recaverable | |
| Messages - #412 Adapive Cruse Control (ACC) Sensor failure - to be cleaned | DE12 | 2 | 3 (guess) | Enabled | 0=ges - #412 Adapive Cruse Contral (ACC) Sensor failure - to be clear |
| Messages - #413 Forward Alert (FA) failure - recoverable | DE12 | 2 | 4 | Enabled | 0=d > B B9, 1=| Messages - #413 Forward Alert (FA) failure - recoverable | |
| Messages - #414 Adapive Cruse Control (ACC) Service - not recoverable | DE12 | 2 | 5 (guess) | Enabled | 0=sages - #414 Adapive Cruse Confrol {ACC) Service - not recoverable |
| Messages - #415 Adapive Cruse Control (ACC) and Forward Alert (FA) failure | DE12 | 2 | 6 (guess) | Enabled | 0=iges - #415 Adapive Cruse Confrol {ACC) and Forward Alert (FA) fail |
| Messages - #419 Alarm triggered | DE12 | 2 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #423 Immobilizer active | DE12 | 3 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #427 Hill Start Assist (HSA) active | DE12 | 3 | 1 | Enabled | 0=isabled, 1=nabled - |
| Messages - #428 Hill Start Assist (HSA) release | DE12 | 3 | 2 | Enabled | 0=sabled, 1=1abled - |
| Messages - #429 Hill Start Assist (HSA) not available | DE12 | 3 | 3 | Enabled | 0=led - > 69— @, 1=| Messages - #4209 Hill Start Assist (HSA) not available | |
| Messages - #431 Headlamp Low Beam Bulb Fault | DE12 | 3 | 4 | Enabled | 0=Disabled, 1=Enabled . |
| Messages - #432 Rear Fog Lamps Bulb Fault | DE12 | 3 | 5 | Enabled | 0=Disabled, 1=Enabled I |
| Messages - #433 Brake/Stop Lamp Bulb Fault | DE12 | 3 | 6 | Enabled | 0=Disabled, 1=Enabled I |
| Messages - #434 Position Lamps Bulb Fault | DE12 | 3 | 7 | Enabled | 0=Disabled, 1=Enabled I |
| Messages - #435 Head Light System Bulb Fault | DE13 | 0 | 0 | Enabled | 0=Disabled, 1=Enabled . |
| Messages - #436 Trailer Stop Lamps Bulb Fault | DE13 | 0 | 1 | Enabled | 0=Disabled, 1=“habled . |
| Messages - #437 Trailer Turn Signal Bulb Fault | DE13 | 0 | 2 | Enabled | 0=isabled, 1=nabled - |
| Messages - #438 Adaptive Cruise Control (ACC) failure - recoverable | DE13 | 0 | 3 (guess) | Enabled | 0=essages - #4358 Adaptive Cruise Control (ACC) failure - recoverable |
| Messages - #440 Engine malfunction - soft warning | DE13 | 0 | 4 | Enabled | 0=abled, 1=bled B |
| Messages - #440b Engine malfunction - hard warning | DE16 | 0 | 1 | Enabled | 0=bled, 1=bled e |
| Messages - #441 IVDC Malfunction | DE13 | 0 | 5 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #449 Oil service Indication | DE13 | 0 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #455 Charging status - overvoltage | DE13 | 0 | 7 | Enabled | 0=Disabled, 1=“habled . |
| Messages - #456 Charging status - battery low | DE13 | 1 | 0 | Disabled | 0=Disabled ., 1=“habled |
| Messages - #466 Adaptive Cruise Control (CADS) service required | DE16 | 0 | 5 (guess) | Enabled | 0=Yessages - #4656 Adaptive Cruise Confrol (CADS) service required |
| Messages - #469 Service Indication - oil change | DE13 | 1 | 1 | Enabled | 0=sabled, 1=1abled - |
| Messages - #474 Tire Pressure Monitoring System (TPMS) sensors not dete(cted) | DE13 | 1 | 2 (guess) | Enabled | 5=#474 Tire Pressure Monitoring System (TPMS) sensors not detec |
| Messages - #476 Alarm System service required | DE13 | 1 | 3 | Enabled | 0=Disabled, 1=“habled . |
| Messages - #477 Electric Parking Brake (EPB) - pre-conditions for drive awa(y) | DE13 | 1 | 4 | Enabled | 0=#477 Electric Parking Brake (EPB) - pre-conditions for drive away no, 1=... |
| Messages - #478 Electric Parking Brake (EPB) - releasing by switch and driv(e) | DE13 | 1 | 5 | Enabled | 0=“lectric Parking Brake (EPB) - releasing by switch and driver present r, 1=... |
| Messages - #479 Electric Parking Brake (EPB) - service required | DE13 | 1 | 6 (guess) | Enabled | 0=Messages - #479 Electric Parking Brake {(EFB) - service required |
| Messages - #480 Electric Parking Brake (EPB) - park brake not fully released | DE13 | 1 | 7 (guess) | Enabled | 0=ages - #480 Electric Parking Brake (EPB) - park brake not fully release |
| Messages - #485 Automated Transmission warning - press brake | DE13 | 2 | 2 (guess) | Enabled | 0=Messages - #485 Automated Transmission warning - press brake |
| Messages - #487 | DE13 | 2 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #488 Automated Transmission warning - not in Park | DE13 | 2 | 3 (guess) | Enabled | 0=| Messages - #488 sutomated Transmission warning - not in Park |
| Messages - #491 Electric Parking Brake (EPB) Status - applied (if telltale blo…) | DE13 | 2 | 4 (guess) | Enabled | 0=#491 Electric Parking Brake (EPB) Status - applied {if tellitale bloch |
| Messages - #492 Electric Parking Brake (EPB) Status - released (if telltale bl…) | DE13 | 2 | 5 (guess) | Enabled | 0=#492 Electric Parking Brake (EPR) Status - released (if telltale bloc |
| Messages - #493 Tire Pressure Monitoring System (TPMS) global warning | DE13 | 2 | 6 (guess) | Enabled | 0=zages - #493 Tire Pressure Monitoring System (TPMS) global warnin |
| Messages - #494 Keyless Vehicle (KV) - steering malfunction 1 | DE13 | 2 | 7 (guess) | Enabled | 0=| Messages - #494 Keyless Vehicle (KY) - steering malfunction 1 | |
| Messages - #495 Keyless Vehicle (KV) - steering malfunction 2 | DE13 | 3 | 0 (guess) | Enabled | 0=| Messages - #495 Keyless Yehicle (KY) - steering malfunction 2 | |
| Messages - #496 Keyless Vehicle (KV) - key not detected | DE13 | 3 | 1 | Enabled | 0=1|, 1=d I |
| Messages - #497 Driver Door Open | DE13 | 3 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #498 Keyless Vehicle (KV) - key outside car | DE13 | 3 | 3 | Enabled | 0==w|, 1=1| - |
| Messages - #499 Keyless Vehicle (KV) - press brake | DE13 | 3 | 4 | Enabled | 0=bled, 1=bled e |
| Messages - #500 Keyless Vehicle (KV) - steering locked | DE13 | 3 | 5 | Enabled | 0==] ——, 1=| Messages - #9300 Keyless Wehicle (k) - steering locked | |
| Messages - #502 Keyless Vehicle (KV) - press clutch | DE13 | 3 | 6 | Enabled | 0=hled, 1=a]/=ls| - |
| Messages - #512 Deflation Detection System (DDS) Warning | DE13 | 3 | 7 | Enabled | 0=» EE———————, 1=| Messages - #3512 Deflation Detection System (DDS) Warning | |
| Messages - #513 Deflation Detection System (DDS) Fault | DE14 | 0 | 0 | Enabled | 0=, 1=| Messages - #5132 Deflation Detection System (DDS) Fault | |
| Messages - #516 Driver door open - 2 | DE14 | 0 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #517 Passenger door open - 2 | DE14 | 0 | 2 (guess) | Enabled | 1=Enabled |
| Messages - #518 Driver side rear door open - 2 | DE14 | 0 | 3 | Enabled | 0=isabled, 1=nabled - |
| Messages - #519 Passenger side rear door open - 2 | DE14 | 0 | 4 | Enabled | 0=abled, 1=bled B |
| Messages - #520 Boot / Trunk open - 2 | DE14 | 0 | 5 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #521 Bonnet / Hood open - 2 | DE14 | 0 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #522 Keyless Vehicle (KV) - Change passive key battery | DE14 | 0 | 7 (guess) | Enabled | 0=lessages - #3522 Keyless Wehicle ) - Change passive key battery |
| Messages - #530 Restraints indicator | DE14 | 1 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #531 MPS6 Transmission Heat protection - 0 | DE14 | 1 | 1 | Enabled | 0=led S, 1=| Messages - #3531 MPSA Transmission Heat protection -0 | |
| Messages - #532 MPS6 Transmission Heat protection - 1 | DE14 | 1 | 2 | Enabled | 0=led, 1=o e |
| Messages - #533 MPS6 Transmission Heat protection - 2 | DE14 | 1 | 3 | Enabled | 0=led, 1=o e |
| Messages - #534 MPS6 Transmission Heat protection - 3 | DE14 | 1 | 4 | Enabled | 0=led S, 1=| Messages - #5324 MPSA Transmission Heat protection -2 | |
| Messages - #567 Immobilizer malfunction | DE14 | 2 | 0 (guess) | Enabled | 1=Enabled |
| Messages - #577 Keyless Vehicle (KV) - Engine preheating (Diesel) | DE14 | 2 | 1 (guess) | Enabled | 0=lessages - #5977 Keyless Yehicle (K% - Engine preheating (Diesel) |
| Messages - #582 Hill Start Assist (HSA) release - chime | DE14 | 2 | 2 | Enabled | 0=1|, 1=d I |
| Messages - #584 Park assistance failure | DE14 | 2 | 3 (guess) | Enabled | 1=Enabled |
| Messages - #586 Mini liftgate open | DE14 | 2 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #588 Mini liftgate open | DE14 | 2 | 5 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #589 Power operated tailgate malfunction | DE14 | 2 | 6 | Enabled | 0=hled, 1=a]/=ls| - |
| Messages - #591 Automated Transmission - limited function | DE14 | 2 | 7 | Enabled | 0=i I————————————, 1=| Messages - #5391 Automated Transmission - limited function | |
| Messages - #600 Electric Power Assist Steering (EPAS) - steering assist not… | DE14 | 3 | 0 | Enabled | 0=#6000 Electric Power Assist Steering (EPAS) - steering assist not av:, 1=... |
| Messages - #601 Electric Power Assist Steering (EPAS) - increased friction | DE14 | 3 | 1 (guess) | Enabled | 0=ages - #601 Electric Power Assist Steering (EPAS) - increased frictior |
| Messages - #602 Electric Power Assist Steering (EPAS) - malfunction | DE14 | 3 | 2 (guess) | Enabled | 0=essages - #6002 Electric Power Assist Steering (EPAS) - malfunction |
| Messages - #606 Brake Pad Wear | DE14 | 3 | 3 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #607 Low Brake Vacuum | DE14 | 3 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #608 Secondary brake not available | DE14 | 3 | 5 | Enabled | 0=Disabled, 1=“habled . |
| Messages - #609 Trailer Sway | DE14 | 3 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #610 Blind Spot Monitoring (BLIS) - right sensor blocked | DE14 | 3 | 7 (guess) | Enabled | 0=essages - #610 Blind Spot Monitoring (BLIS) - right sensor blocked |
| Messages - #611 Blind Spot Monitoring (BLIS) - left sensor blocked | DE15 | 0 | 0 (guess) | Enabled | 0=lessages - #611 Blind Spot Monitoring (BLIS) - left sensor blocked |
| Messages - #612 Blind Spot Monitoring (BLIS) - right sensor malfunction | DE15 | 0 | 1 (guess) | Enabled | 0=sages - #6512 Blind Spot Monitoring (BLIS) - right sensor malfunction |
| Messages - #613 Blind Spot Monitoring (BLIS) - left sensor malfunction | DE15 | 0 | 2 (guess) | Enabled | 0=ssages - #6513 Blind Spot Monitoring (BLIS) - left sensor malfunction |
| Messages - #614 Blind Spot Monitoring (BLIS) - trailer connected - deactivat(ed) | DE15 | 0 | 3 (guess) | Enabled | 0=les - #614 Blind Spot Monitoring (BLIS) - trailer connected - deactival |
| Messages - #625 Park brake applied - 1 | DE15 | 0 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #626 Park brake applied - 2 | DE15 | 0 | 5 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #630 Keyless Vehicle (KV) - place key in key holder | DE15 | 0 | 6 (guess) | Enabled | 0=| Messages - #630 Keyless vehicle (k) - place key in key holder | |
| Messages - #632 Keyless Vehicle (KV) - press brake and clutch | DE15 | 0 | 7 (guess) | Enabled | 0=| Messages - #6232 Keyless Yehicle (KY) - press brake and clutch | |
| Messages - #633 Keyless Vehicle (KV) - Hold Key next to symbol | DE16 | 3 | 1 (guess) | Enabled | 0=Messages - #633 Keyless Vehicle (K4 - Hold Key next to symbol |
| Messages - #640 Start / Stop - Engine starting | DE15 | 1 | 0 | Enabled | 0=isabled, 1=nabled - |
| Messages - #641 Start / Stop - press clutch 2 | DE15 | 1 | 1 | Enabled | 0=Disabled, 1=“habled . |
| Messages - #642 Start / Stop - malfunction | DE15 | 1 | 2 | Enabled | 0=Disabled, 1=Enabled I |
| Messages - #643 Start / Stop - turn ignition off | DE15 | 1 | 3 | Enabled | 0=abled, 1=abled B |
| Messages - #644 Start / Stop - select neutral | DE15 | 1 | 4 | Enabled | 0=Disabled, 1=“habled . |
| Messages - #650 Child power lock | DE15 | 1 | 5 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #651 Belt minder sensor failure | DE15 | 1 | 6 | Enabled | 0=Disabled, 1=Enabled I |
| Messages - #655 One Touch Integrated Start (OTIS) - press brake to start | DE16 | 1 | 4 (guess) | Enabled | 0=ages - #6355 One Touch Integrated Start (OTIS) - press brake to star |
| Messages - #656 One Touch Integrated Start (OTIS) - press clutch to start | DE16 | 1 | 5 (guess) | Enabled | 0=ages - #656 One Touch Integrated Start (OTIS) - press clutch to star |
| Messages - #657 One Touch Integrated Start (OTIS) - press clutch and brak(e) | DE16 | 1 | 6 | Enabled | 0=#657 One Touch Integrated Start (OTIS) - press clutch and brake &, 1=... |
| Messages - #658 One Touch Integrated Start (OTIS) - cranking time exceed(ed) | DE16 | 1 | 7 (guess) | Enabled | 0=es - #6558 One Touch Integrated Start (OTIS) - cranking time excesc |
| Messages - #660 My Key Active - Drive Safely | DE15 | 1 | 7 | Enabled | 0=Disabled, 1=Enabled . |
| Messages - #661 Greeting: Speed Limited to 80 MPH (130 km/h) | DE15 | 2 | 0 (guess) | Enabled | 0=Messages - #661 Greeting: Speed Limited to 80 MPH {130 km/h) |
| Messages - #662 Greeting: Speed Limited to 130 km/h | DE15 | 2 | 1 | Enabled | 0=hled, 1=a]/=ls| - |
| Messages - #665 Check Speed - Drive Safely | DE15 | 2 | 2 | Enabled | 0=Disabled, 1=Enabled l |
| Messages - #666 Vehicle Near Top Speed of MyKey Setting | DE15 | 2 | 3 | Enabled | 0=1|, 1=d I |
| Messages - #667 Vehicle at Top Speed of MyKey Setting | DE15 | 2 | 4 | Enabled | 0=led, 1=o e |
| Messages - #670 Buckle Up to Unmute Audio | DE15 | 2 | 5 | Enabled | 0=Disabled, 1=Enabled I |
| Messages - #680 Front camera reduced visibility | DE15 | 2 | 6 | Enabled | 0=sabled, 1=1abled - |
| Messages - #681 Lane Departure Warning System (LDWS) Camera malfuncti(on) | DE15 | 2 | 7 (guess) | Enabled | 0=jes - #6381 Lane Departure Warning System (LOWS) Camera malfunc |
| Messages - #682 Front camera not available | DE15 | 3 | 0 | Enabled | 0=Disabled, 1=Enabled I |
| Messages - #685 Lane Departure Warning System malfunction | DE15 | 3 | 1 | Enabled | 0=i R, 1=| Messages - #6585 Lane Departure \Warning System malfunction | |
| Messages - #688 Driver impairment monitor 1st warning | DE15 | 3 | 2 | Enabled | 0=led .., 1=| Messages - #6828 Driver impairment manitor 1st warning | |
| Messages - #689 Driver impairment monitor 2nd warning | DE15 | 3 | 3 | Enabled | 0=led, 1=o e |
| Messages - #695 Auto High Beam Control (AHBC) on | DE15 | 3 | 4 | Enabled | 0=abled, 1=abled B |
| Messages - #696 Auto High Beam Control (AHBC) off | DE15 | 3 | 5 | Enabled | 0=abled, 1=bled B |
| Messages - #710 City Safety auto braking | DE16 | 0 | 2 | Enabled | 0=Disabled, 1=Enabled I |
| Messages - #711 City Safety sensor blocked | DE16 | 0 | 3 | Enabled | 0=Disabled, 1=Enabled I |
| Messages - #712 City Safety malfunction | DE16 | 0 | 4 (guess) | Enabled | 1=Enabled |
| Messages - #723 Transmission State | DE16 | 0 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #724 Transmission State | DE16 | 1 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #725 Transmission Heat Protection | DE16 | 1 | 1 | Enabled | 0=Disabled, 1=Enabled . |
| Messages - #746 Brake system malfunction | DE15 | 3 | 6 | Enabled | 0=Disabled, 1=Enabled I |
| Messages - #760 Remote Start Active | DE16 | 1 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Messages - #761 Remote Start Passive Entry Passive Start | DE16 | 1 | 3 | Enabled | 0=,6B6J6J96B6B6B6B69Bn69@— @, 1=| Messages - #7651 Remaote Start Passive Entry Passive Start | |
| Messages - #790 One Touch Integrated Start (OTIS) - engine start pending, … | DE16 | 3 | 2 | Enabled | 0=#790 One Touch Integrated Start (OTIS) - engine start pending, ples, 1=... |
| Messages - #791 One Touch Integrated Start (OTIS) - engine start cancelled | DE16 | 3 | 3 (guess) | Enabled | 0=ges - #791 One Touch Integrated Start (OTIS) - engine start cancelle |
| Messages - #98 Engine On | DE14 | 1 | 5 | Enabled | 0=Disabled, 1=Enabled |
| Metric Units Type | DE02 | 3 | 0 | L/100 km | 0=L1200 ki, 1=kmfi |
| MyKey Menu - Blind Spot Monitoring | DE05 | 0 | 5 | Enabled | 0=Disabled, 1=Enabled |
| MyKey Menu - Cross Traffic Alert | DE05 | 0 | 2 | Enabled | 0=Disabled, 1=Enabled |
| MyKey Menu - Forward Collision Alert | DE05 | 0 | 3 | Disabled | 0=Disabled, 1=Enabled |
| MyKey Menu - Lane Departure Warning | DE05 | 0 | 0 | Disabled | 0=Disabled, 1=Enabled |
| Navigation Repeater | DE1B | 1 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Passenger Beltminder | DE1A | 0 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Passenger Seat | DE23 | 1 | 0 | Disabled | 0=Disabled, 1=Enabled |
| RS Feature | DE05 | 2 | 0 | Disabled | 0=Disabled, 1=Enabled |
| RS Feature - Animation | DE05 | 3 | 7 | Base | 0=Base, 1=R5+ |
| RS Feature - Exhaust Settings | DE05 | 3 | 6 | Disabled | 0=Disabled, 1=Enabled |
| RS Feature - Launch Control | DE05 | 0 | 6 | Disabled | 0=Disabled, 1=Enabled |
| RS Feature - Peformance Shift Control | DE05 | 0 | 7 | Disabled | 0=Disabled, 1=Enabled |
| RS Feature - Selectable Drive Modes | DE05 | 2 | 1 | Disabled | 0=Disabled, 1=Enabled |
| Rear Defrost | DE23 | 0 | 5 | Disabled | 0=Disabled, 1=Enabled |
| Rear beltminder | DE1A | 0 | 5 | Enabled | 0=Disabled, 1=Enabled |
| Remote Start | DE1B | 2 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Remote Start | DE23 | 0 | 6–0 | Disabled | 0=Disabled, 71=Enabled |
| Remote Start - Driver Seat | DE23 | 1 | 1 | Disabled | 0=Disabled, 1=Enabled |
| Remote Start - Passenger Seat | DE23 | 1 | 0 | Disabled | 0=Disabled, 1=Enabled |
| Remote Start - Steering Wheel | DE23 | 0 | 7 | Disabled | 0=Disabled, 1=Enabled |
| Remote Start Front Defrost HVAC | DE23 | 0 | 4 | Disabled | 0=Disabled, 1=Enabled |
| Remote Start Menu - Climate Mode | DE23 | 0 | 3 | Disabled | 0=Disabled, 1=Enabled |
| Remote Start Menu - Duration Timer | DE23 | 0 | 2 | Disabled | 0=Disabled, 1=Enabled |
| Remote Start Menu - Front windows and washer jets defroster | DE23 | 0 | 4 (guess) | Disabled | 0=| Remote Start Menu - Front windows and washer jets defroster | |
| Remote Start Menu - Quiet Mode On/Off | DE23 | 0 | 1 | Disabled | 0=Disabled, 1=Enabled |
| Remote Start Menu - Rear windows and mirrors defroster | DE23 | 0 | 5 | Disabled | 0=2 2 ===, 1=.4 |Remate Start Menu - Rear windows and mirrors defroster | |
| Remote Start Menu - Remote Start enable/disable | DE23 | 0 | 0 | Disabled | 0=sabled -, 1=1abled |
| Remote Start Menu - Reset to default | DE23 | 0 | 6 | Disabled | 0=Disabled, 1=Enabled |
| Tire Pressure Monitor | DE1B | 1 | 5 | Enabled | 0=Disabled, 1=Enabled |
| Trip Computer - All Values | DE02 | 0 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Trip Computer - Average Fuel Economy | DE02 | 0 | 4 | Enabled | 0=Disabled, 1=Enabled |
| Trip Computer - Average Speed | DE02 | 0 | 6 | Disabled | 0=Disabled, 1=Enabled |
| Trip Computer - Digital Speedometer | DE02 | 1 | 7 | Enabled | 0=Disabled, 1=Enabled |
| Trip Computer - Distance Till Empty | DE02 | 0 | 2 | Enabled | 0=Disabled, 1=Enabled |
| Trip Computer - Instant Fuel Economy | DE02 | 0 | 3 | Enabled | 0=Disabled, 1=Enabled |
| Trip Computer - Navigation Repeater | DE02 | 1 | 6 | Enabled | 0=Disabled, 1=Enabled |
| Trip Computer - Trip Timer | DE02 | 0 | 1 | Enabled | 0=Disabled, 1=Enabled |
| Trip Computer 1 - Screen A (upper left) | DE03 | 0 | 2–0 (guess) | Trip Odometer | 1=Trip Timer, 2=Distance Till Empty, 3=Instant Fuel Econarmy, 4=Average Fuel Econarmy, 5=Digital Speedometer Gauge, 7=Trip Odometer |
| Trip Computer 1 - Screen B (upper right) | DE03 | 1 | 2–0 | Average Fuel Economy | 0=Default, 1=Trip Timer, 2=Distance Till Empty, 3=Instant Fuel Econormy, 4=Average Fuel Econormy, 5=Average Speed, 6=Digital Speedometer Gauge, 7=Trip Odometer |
| Trip Computer 1 - Screen C (down left) | DE03 | 2 | 2–0 | Instant Fuel Economy | 0=Default, 1=Trip Timer, 2=Distance Till Empty, 3=Instant Fuel Econormy, 4=Average Fuel Econormy, 5=Average Speed, 6=Digital Speedometer Gauge, 7=Trip Odometer |
| Trip Computer 1 - Screen D (down right) | DE03 | 3 | 1 (guess) | Distance Till Empty | 1=Trip Timer, 2=Distance Till Empty, 3=Instant Fuel Econarmy, 4=Average Fuel Econarmy, 5=Digital Speedometer Gauge, 7=Trip Odometer |
| Trip Computer 2 - Screen A (upper left) | DE04 | 0 | 2–0 (guess) | Trip Odometer | 1=Trip Timer, 2=Distance Till Empty, 3=Instant Fuel Econarmy, 4=Average Fuel Econarmy, 5=Digital Speedometer Gauge, 7=Trip Odometer |
| Trip Computer 2 - Screen B (upper right) | DE04 | 1 | 2–0 | Average Fuel Economy | 0=Default, 1=Trip Timer, 2=Distance Till Empty, 3=Instant Fuel Econormy, 4=Average Fuel Econormy, 5=Average Speed, 6=Digital Speedometer Gauge, 7=Trip Odometer |
| Trip Computer 2 - Screen C (down left) | DE04 | 2 | 2–0 | Instant Fuel Economy | 0=Default, 1=Trip Timer, 2=Distance Till Empty, 3=Instant Fuel Econormy, 4=Average Fuel Econormy, 5=Average Speed, 6=Digital Speedometer Gauge, 7=Trip Odometer |
| Trip Computer 2 - Screen D (down right) | DE04 | 3 | 1 (guess) | Distance Till Empty | 1=Trip Timer, 2=Distance Till Empty, 3=Instant Fuel Econarmy, 4=Average Fuel Econarmy, 5=Digital Speedometer Gauge, 7=Trip Odometer |
| Trip Computer B | DE02 | 0 | 0 | Enabled | 0=Disabled, 1=Enabled |
| Trip Computer Type | DE02 | 1 | 0 | North America | 0=Europe, 1=Morth America |
| Trip Computer Units | DE02 | 3 | 1 | Imperial | 0=Metfric, 1=Imperial |
| Vehicle Graphics | DE05 | 2 | 2 | Enabled | 0=Disabled, 1=Enabled |
