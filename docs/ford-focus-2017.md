# What FORScan says to a 2017 Ford Focus

Notes from one evening (23 November 2026) of recording the traffic between
FORScan 2.3.72 and a 2017 Ford Focus 2.0 GDI through an OBDLink EX. They cover
which modules the car has, how each is addressed, what FORScan reads from them,
where the configuration ("as-built") blocks live, and the exact sequence FORScan
uses to change one.

Everything here was observed on one car. Where something is an inference
rather than an observation, it says so. cardiag itself still sends read
requests only; the write sequence is recorded here, not implemented.

The data behind these notes:

- [`data/focus-2017-requests.txt`](data/focus-2017-requests.txt): every
  distinct request FORScan sent, with one reply each (432 of them).
- [`data/focus-2017-asbuilt.txt`](data/focus-2017-asbuilt.txt): every
  configuration block, by module, with its value on this car.
- [`data/focus-2017-ccc-map.txt`](data/focus-2017-ccc-map.txt): the body
  control module's central configuration, byte by byte, with FORScan's names
  (from a second session on 24 November).
- [`focus-2017-settings.md`](focus-2017-settings.md): every setting FORScan
  names for this car, with its value (same session).
- [`focus-2017-config-map.md`](focus-2017-config-map.md): where each of those
  settings lives (block, byte, bits) and what its values mean, for the body
  control module and the cluster.
- [`../tools/parse_forscan_capture.py`](../tools/parse_forscan_capture.py):
  turns a raw capture into the first of those.

The VIN has been replaced with a placeholder in both data files. The raw
capture and FORScan's own log are not in the repository: the capture holds the
VIN, and FORScan's log holds the licence key and the owner's name.

## How the traffic was recorded

FORScan runs under Wine and talks to the adapter through a COM port. Wine maps
that COM port to a device file, so a logging relay can sit in between.

```sh
# 1. A relay between a pseudo-terminal and the adapter, logging both directions
socat -v -x PTY,link=/tmp/obd,raw,echo=0 \
      /dev/ttyUSB0,raw,echo=0,ispeed=115200,ospeed=115200 2>> capture.log

# 2. Point Wine's COM5 at the relay, then restart Wine
wine reg add 'HKLM\Software\Wine\Ports' /v COM5 /t REG_SZ /d /tmp/obd /f
wineserver -k

# 3. Start FORScan from its own folder, so it finds its certificate bundle
cd ~/.wine/drive_c/"Program Files (x86)"/FORScan && wine FORScan.exe
```

In FORScan: connection type `COM`, port `COM5`, baud rate `115200`.

What went wrong along the way, so it need not again:

- **"Auto" and "FTDI" connection types find no adapter.** They need FTDI's
  Windows driver, which Wine does not have. `COM` works.
- **Two readers on one port.** If COM5 still points at `/dev/ttyUSB0` while the
  relay is running, both read the adapter and each gets part of the replies.
  FORScan then reports "no adapter found". Check the registry value took.
- **The port left at speed 0.** Once, after the adapter was replugged, the relay
  came up with the port's output speed at 0 and the adapter heard nothing.
  `stty -F /dev/ttyUSB0 115200 raw -echo` fixed it; running that shortly after
  each start of the relay prevents it.
- **socat exits when FORScan closes the port.** Run it in a loop.
- **Wine also maps the adapter directly**, as a high-numbered COM port (COM34
  here). Keep FORScan's port fixed on COM5, not "Auto", or it may pick that one
  and bypass the relay.
- **The relay fixes the speed at 115200**, the OBDLink EX default. FORScan stayed
  at that speed throughout.

FORScan sends what you open and nothing else. The capture therefore holds the
module scan, the live values that were put on a dashboard for the engine
module, a fault-code read, every "(AS BUILT format)" entry opened once, one
engine-module reset, and two writes to the instrument cluster.

## How FORScan sets up the adapter

After identifying the adapter (`ATI`, `STI`, `STDI`), FORScan sets it up with:

```
ATE0  ATL0  ATH0  ATR1  ATS0  ATCAF1  ATAL
ATTP6            11-bit CAN at 500 kbit/s: the HS bus
STPTOT100
```

Then, for each module it talks to:

```
ATSH0007E0       send to 7E0
STCAFCP7E0,7E8   flow control for the pair: requests to 7E0, replies from 7E8
```

To reach the modules on the slower bus it switches protocol:

```
STP53            the adapter's second CAN channel (MS bus on an OBDLink EX)
STPBR125000      at 125 kbit/s
```

and switches back with `ATTP6`. `STP53` and `STPBR` are STN commands; a plain
ELM327 cannot reach the MS bus at all. On this car the MS bus is on the
diagnostic connector's pins 3 and 11, which the OBDLink EX switches to by
itself; that pin detail is general knowledge about Ford, not something the
capture shows.

Most requests are sent as plain hex, with a trailing digit telling the adapter
how many replies to wait for (`22F4461` is `22 F446`, one reply). Some are
wrapped in an STN command instead: `STPX D:22DE00, R:1`. Both forms are the
same request to the car.

`ATRV` (adapter supply voltage) is polled every two seconds as a keep-alive.
`3E 80` (tester present, no reply wanted) is sent to `7DF` while a session is
open.

## The modules

Fourteen addresses answered the scan. The names are the ones FORScan uses in
its as-built file names; three modules have no as-built entry and so no name
here.

| Request | Reply | Bus | Module |
|---|---|---|---|
| `7E0` | `7E8` | HS | PCM, engine |
| `7E1` | `7E9` | HS | not named (the transmission module on other Fords) |
| `7D0` | `7D8` | HS | APIM, SYNC |
| `797` | `79F` | HS | not named |
| `765` | `76D` | HS | not named |
| `760` | `768` | HS | ABS |
| `737` | `73F` | HS | RCM, airbags |
| `730` | `738` | HS | PSCM, power steering |
| `726` | `72E` | HS | BdyCM, body control |
| `7A5` | `7AD` | MS | FCDIM, front display |
| `727` | `72F` | MS | ACM, audio |
| `720` | `728` | MS | IPC, instrument cluster |
| `701` | `709` | MS | GPSM, GPS |

`7DF` is the broadcast address on the HS bus. A module always answers from its
request address plus 8.

## What FORScan reads

| Service | Meaning | Where it was seen |
|---|---|---|
| `01`, `03`, `07`, `09` | Standard OBD-II: supported values, stored and pending codes, VIN | `7DF` |
| `22 xxxx` | Read data by identifier | every module |
| `19 02 8F` | Read fault codes by status mask | every module |
| `19 04 …` | Read the stored detail for one fault code | cluster |
| `3E 00` | Tester present | engine |

### Identifiers that came up on every module

| Identifier | What it appears to hold | Why |
|---|---|---|
| `DD00` | A running clock | Four bytes that count up between reads; nearly the same on every module |
| `DD01` | Odometer | Three bytes, identical on every module that answers |
| `DD02` | Battery voltage in quarter volts | One byte: `0x30` with the engine off, `0x38` or `0x39` with the adapter reading 14.3 to 14.7 V. ABS and steering answer `00` and `FF` |
| `D100` | Active diagnostic session | Reads `01` in the default session and `03` after `10 03` |
| `F106` | The central car configuration (CCC), 254 bytes | Same reply from body control and cluster; matches what FORScan reads through the bootloader. See "Reading the central configuration" |
| `F188`, `F113` | Software and hardware part numbers | ASCII Ford part numbers |
| `F190` | VIN | ASCII |
| `F162` | Not known | One byte, read just before unlocking |

These meanings are read off the bytes, not taken from any Ford document.

### Live values

Only the engine module's live values were captured: 167 identifiers answered
and 8 were refused. They are in the requests file, each with a sample reply.
The capture does not say which identifier is which named value, since FORScan
shows names on screen and sends only numbers; that pairing has to be made by
watching one value at a time. The other modules have only the handful of
identifiers FORScan reads during its scan.

Identifiers beginning `F4` follow the standard OBD-II numbering (`F40C` is
engine speed, standard value `0C`), so those decode the way service `01` does.
That was checked for `F40C` only, which read zero with the engine off.

## Configuration blocks

See the [configuration catalog](focus-2017-config-catalog.md) for known settings and the per-module address inventory.

Each module keeps its configuration in a run of identifiers starting at `DE00`.
FORScan calls these as-built blocks and numbers them from 1:

```
block number = identifier - DE00 + 1
```

So `DE00` is block 1 and `DE11` is block 18. FORScan shows each block in rows
of five bytes, and writes them to `.abt` files like this:

```
;Block 1
720G1G1430100006D
```

which is the module (`720`), the block (`G1`), the row (`G1`), the data
(`43 01 00 00`) and a checksum (`6D`). The checksum is the low byte of the sum
of the address digits taken as bytes (`07 20 01 01`) and the data bytes. It was
checked on two rows of the cluster's file. The car never sees it: it exists
only on screen and in the file.

Blocks on this car:

| Module | Blocks that read | Bytes in all |
|---|---|---|
| Body control `726` | `DE00`–`DE05` | 60 |
| Engine `7E0` | `DE00`, `DE01` | 104 |
| SYNC `7D0` | `DE00`–`DE02` | 19 |
| ABS `760` | `DE00` (the VIN) | 17 |
| Airbags `737` | `DE00`–`DE03`, `DE05` (`DE00` is the VIN) | 30 |
| Power steering `730` | `DE00` | 1 |
| Front display `7A5` | `DE00`–`DE03` | 19 |
| Audio `727` | `DE00`–`DE07` | 93 |
| Cluster `720` | 30 blocks between `DE00` and `DE23` | 176 |
| GPS `701` | `DE00`, `DE01` | 8 |

FORScan asks past the end of each run and the module refuses with `7F 22 31`
(request out of range). The refused identifiers are listed per module in the
as-built data file.

Two things that did not work:

- The body control module refused `DE06`–`DE0A`. On 23 November FORScan's
  named view of that module then asked for a file, `GV6T-14C097-AA.VBF`, which
  its log calls a secondary bootloader, and its download was refused (HTTP 401).
  On 24 November the same named view opened without asking, reading only
  `DE00`–`DE05` after unlocking.
- The capture contains no setting labels. The operator identified the cluster
  option changed during this session: see [Changing a block](#changing-a-block).
  [`focus-2017-config-map.md`](focus-2017-config-map.md) now places every named
  setting.

## Reading the central configuration

Besides its as-built blocks, the body control module holds the car's central
configuration (CCC): one byte per equipment option (engine, gearbox, tyre size,
airbags, radio, and so on), about 250 in all. The cluster keeps a copy.
FORScan calls them "Central configuration (Main)" and "(Backup)".

**FORScan's way** (24 November, engine running for the bootloader step):

| Step | Request to `726` | Reply |
|---|---|---|
| 1 | `10 02` (programming session) | `50 02 …` |
| 2 | `27 01`, `27 02` and a key | `67 01` seed, `67 02` |
| 3 | `34 …`, `36 …` ×5, `37` | Download of the secondary bootloader into RAM |
| 4 | `34`/`36`/`37` ×5 more | Small further downloads |
| 5 | `31 01 03 01 40 00 20 00` | Start the routine at `0x40002000`: run the bootloader |
| 6 | `35 00 44 00 00 80 xx xx 00 00 00 20` ×18, each followed by `36 01` | Upload 32 bytes at a time from `0x00008000` on |

Afterwards FORScan sent `11 81` to every module. While the body control module
was running the bootloader it was silent on the bus, and the other modules
logged it: the engine, SYNC, ABS, cluster and GPS stored lost-communication
codes (`U0140` and others), and the engine stored `P025A` (fuel pump module
circuit) and `P193E` (A/C clutch request), with a freeze frame one second after
step 1. All the modules answered normally afterwards.

**The other way, with no bootloader:** `22 F106` to `726` or `720` returns
`62 F1 06`, then `FC 45`, then 252 bytes. They are the same bytes FORScan
uploaded, less its last two (both `00`, which FORScan names "EUCD padding").
A program that only reads can use this. The upload also returned a header
(configuration document number, VIN) and two blocks that are all zero on this
car; those are not in `F106`.

[`data/focus-2017-ccc-map.txt`](data/focus-2017-ccc-map.txt) gives each byte's
offset, its value on this car, FORScan's name for it, and what FORScan showed
for that value. The names come from the order FORScan listed them in its
"Engineering 2 (+ hidden)" view. That view has two rows fewer than there are
bytes. The anchors are a spare byte that reads `00`, the battery type (`19`)
and the two RCM bytes (`65 81`, the same as the airbag module's `DE02`, byte
for byte reversed). From these, the two missing rows fall between "Traffic
information system" and "Occupant weight sensor", and between "Touchscreen"
and "Rear Entertainment System". Those three bytes are marked `?`. Only this
car's value of each option is known, not what the other values would mean.

## Sessions and unlocking

Before reading most modules' blocks, and before every write, FORScan does this:

| Request | Reply | Meaning |
|---|---|---|
| `10 03` | `50 03 00 32 01 F4` | Extended session. The reply gives the module's reply times: 50 ms, and 5 s when it asks for more time |
| `27 03` | `67 03 ss ss ss` | A three-byte seed, different every time |
| `27 04 kk kk kk` | `67 04` | The three-byte key worked out from that seed |
| … | | The reads or the write |
| `10 01` | `50 01 …` | Back to the default session |

The audio and GPS modules refuse the seed request (`7F 27 7F`) and are read
without unlocking.

The key is computed from the seed. Because the seed changes every time, a
recorded key cannot be sent again; a program that wants to unlock a module has
to implement the calculation. The capture does not reveal it. What it does give
is pairs to test an implementation against:

| Module | Seed | Key |
|---|---|---|
| Engine `7E0` | `4F2C9F` | `63A9E4` |
| Engine `7E0` | `8FA3A5` | `A42E3C` |
| Body control `726` | `13C8E3` | `7EB971` |
| Body control `726` | `295A5E` | `D61032` |
| Body control `726` | `726A8A` | `09900A` |
| Body control `726` | `2F2C18` | `4597B6` |
| Body control `726` | `87987F` | `0FDC23` |
| SYNC `7D0` | `4F94C9` | `7F9217` |
| ABS `760` | `2E8EA2` | `466968` |
| Airbags `737` | `A0EEF4` | `095DC5` |
| Power steering `730` | `34CFFB` | `C19C0F` |
| Front display `7A5` | `95CB4B` | `3BF590` |
| Cluster `720` | `BEF060` | `1F04A6` |
| Cluster `720` | `C250EF` | `7E8A19` |
| Cluster `720` | `C2B14D` | `C9F5E9` |
| Cluster `720` | `002AE8` | `44FC3B` |

Whether every module uses the same calculation with a different secret, or
different calculations, is not known from this.

## Changing a block

One setting in the instrument cluster was changed in FORScan's named view and
then changed back. Both writes went to block 18, `DE11`:

| | Bytes | Result |
|---|---|---|
| Before | `FF FF FF 3E` | |
| First write | `FF FF 7F 3E` | accepted |
| Second write | `FF FF FF 3E` | accepted |

The operator identified the toggled option as the **key-in-ignition beep**. The sweep in [`focus-2017-config-map.md`](focus-2017-config-map.md) agrees:
"Chimes - Key In Ignition" is `DE11` byte 2 bit 7, with 1 = enabled, so the
first write turned the chime off and the second turned it back on.
On this Focus, the capture maps that option to the top bit of the third byte
(mask `80` hex). The bit was cleared and then restored. The log does not say
which state was labelled enabled in FORScan; do not infer that from bit order.

The sequence, as sent:

| Step | Request | Reply |
|---|---|---|
| 1 | `10 03` | `50 03 00 32 01 F4` |
| 2 | `27 03` | `67 03` and the seed |
| 3 | `27 04` and the key | `67 04` |
| 4 | `2E DE 11 FF FF 7F 3E` | `7F 2E 78`, then `6E DE 11` |
| 5 | `10 01` | `50 01 …` |
| 6 | `11 01` | `51 01` |

What it shows:

- **The whole block is written.** The request is the identifier and all of the
  block's bytes. To change one bit: read the block, change it, write it all back.
- **No checksum is sent.**
- **Session and unlock are both required.** FORScan first tried the write in
  the default session and got `7F 2E 7F`; then in the extended session without
  unlocking and got `7F 2E 33`.
- **The module asks for time.** `7F 2E 78` means "still working"; the real
  answer follows.
- **The module is restarted afterwards** with `11 01`, a hard reset addressed
  to that module. Presumably that is when the new setting takes effect.
- **FORScan does not send a block that has not changed.** It says there is
  nothing to do.

This is one module, on the MS bus. That the others take the same sequence is
likely but was not tried.

## Placing named settings without writing

[`../tools/forscan_dryrun_relay.py`](../tools/forscan_dryrun_relay.py) takes the
logging relay's place between FORScan and the adapter. Reads go to the car.
Anything that would change it (`2E`, `3B`, `11`, `14`, `04`, `31`, `28`, `85`,
the programming session `10 02`, downloads and uploads) is answered by the
relay and never sent. Block writes get a made-up "accepted" reply, so FORScan
carries on as if the write worked, and the relay logs which bytes and bits
FORScan wanted to change. It compares them with the last value of that block
read from the car in the same session.

```sh
# instead of step 1 of the recording recipe (COM5 still points at /tmp/obd)
python3 tools/forscan_dryrun_relay.py --log-dir ~/forscan-dryrun
```

Then, in FORScan, for each setting:

1. Open the module's named view ("Module configuration"). It reads the blocks
   from the car, which gives the relay its "before" values.
2. Change one setting with "Edit selected", then press Write.
3. The relay prints, for example, `BLOCKED write 720 DE11: byte 2: FF->7F bits [7]`
   and adds the same to `writes.jsonl`. Note down which setting it was.
4. Reopen the named view before the next one. The car was not changed, so it
   reads the real values again.

Run against yesterday's cluster write, it gives the same answer the real write
did: `DE11`, byte 2, bit 7. Changing a setting to each of its values in turn
gives each value's bit pattern.

With `--replay capture.log transcript.log` the relay needs no adapter: it
answers FORScan from recordings of earlier sessions (its own transcripts or a
socat capture), keyed by protocol, header and request. FORScan connected, found
every module and opened the named views this way, so the mapping in
[`focus-2017-config-map.md`](focus-2017-config-map.md) ran with the car parked
elsewhere. [`../tools/forscan_sweep/`](../tools/forscan_sweep/) drives FORScan
through each setting in turn.

Two limits:

- FORScan's reply to the made-up acceptance is its own business. If it re-reads
  the block to check, it will see the old value and may report a failure. The
  log entry is made either way.
- Only requests FORScan sends through the relay are seen. Settings that FORScan
  writes some other way, such as the central configuration through the
  bootloader, are refused (`7F 34 22`) rather than logged.

## Other things FORScan did

- **An engine-module routine.** One entry in Configuration and Programming,
  run on the engine module, sent `10 03`, unlocked, then `31 01 0E 06` (start
  routine `0E06`), which answered `71 01 0E 06 10`. It then returned to the
  default session and cleared the module's fault codes with `14 FF FF FF`.
  Before starting it read engine speed (`22 F40C`) and got zero. Which named
  FORScan entry this was, and what the `10` means, were not recorded.
- **A restart of everything.** `11 81` was sent to `7DF` three times: a hard
  reset to every module on the bus, with no reply wanted. Each time was while a
  body control configuration entry was being run.

## Refusals seen

A reply of `7F <service> <reason>` is a refusal.

| Reason | Meaning | When |
|---|---|---|
| `31` | Request out of range | Reading an identifier the module does not have |
| `33` | Security access denied | Writing before unlocking |
| `78` | Response pending | A write or a clear that takes time; the answer follows |
| `7F` | Not supported in the active session | Writing in the default session; asking the audio or GPS module for a seed |

## What this means for cardiag

cardiag today reads maker-specific values with service `22` from modules that
answer between `7E8` and `7EF`, on the HS bus. Against what is recorded here:

- **Most modules are outside that range.** Body control, ABS, airbags, steering
  and SYNC answer from `72E`, `768`, `73F`, `738` and `7D8`. Reading them needs
  the header and flow-control pair set per module, as FORScan does with `ATSH`
  and `STCAFCP`.
- **Four modules are on the MS bus**, which needs the STN protocol switch
  above and an adapter that has it.
- **Configuration can be read with what cardiag already sends.** The blocks are
  ordinary `22 DExx` reads. FORScan usually enters the extended session and
  unlocks first, but several blocks answered before it had done either: the
  engine's `DE00` and `DE01`, SYNC's `DE00`–`DE02`, steering's `DE00`, the
  audio module's `DE04`–`DE07`, the cluster's `DE0B`–`DE0D` and GPS's `DE01`.
  The body control, ABS, airbag and front display blocks were only ever read
  unlocked, so whether they need it is not known.
- **Changing a setting needs three things cardiag does not have:** the key
  calculation, a write request (`2E`), and the decision to stop being
  read-only. A write also wants care that a read does not: a steady supply
  voltage, a saved copy of the block beforehand, and a re-read afterwards.
- **Names for the bits have to come from elsewhere:** FORScan's named views,
  one setting at a time as with `DE11` above, or owners' as-built tables.
- **The central configuration is a plain read:** `22 F106` to `726`, decoded
  with the byte map. No session, unlocking or bootloader is needed.

## Not known

- The seed-to-key calculation.
- Where the few settings whose FORScan editor is a number box live (see
  [`focus-2017-config-map.md`](focus-2017-config-map.md)).
- Which two central configuration bytes FORScan does not show as rows.
- Which engine-module identifier is which named value.
- The names of the modules at `7E1`, `765` and `797`.
- Whether the write sequence is the same on the HS-bus modules.
- What `F162` and the routine `0E06` are.
