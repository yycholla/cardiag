# cardiag

Car diagnostics over OBD-II for Linux. It reads trouble codes, readiness
monitors and live data, and records sessions, from the command line or from a
web page that a phone, tablet or laptop can open. From those it works out what
the car does not say outright: which gear it is in, whether a clutch slips, how
fuel trim varies with load, and how each figure sits against a healthy band. It
sends read requests only.

Targets: a 2017 Ford Focus (CAN) and a pre-2007 Chevrolet Tahoe (J1850 VPW),
through an OBDLink EX USB adapter. Any ELM327-compatible adapter should work for
the standard data.

## Install

```sh
git clone https://github.com/yycholla/cardiag.git
cd cardiag
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## Try it without a car

Three simulated vehicles are built in:

```sh
.venv/bin/cardiag --sim focus info
.venv/bin/cardiag --sim focus codes
.venv/bin/cardiag --sim tahoe codes
.venv/bin/cardiag --sim focus live
.venv/bin/cardiag serve --sim focus_dct    # a Focus driven through its gears, with a clutch that slips in third
```

`focus_dct` repeats a 150-second lap: a gentle run up through the gears, then a
hard one. Under the hard run third gear slips and the shift from second to
third is slow. Its gear ratios are invented.

## Use it with the adapter

Plug the adapter into the car and the laptop, and turn the ignition on. The
engine can stay off.

```sh
.venv/bin/cardiag ports       # the adapter should be listed, usually /dev/ttyUSB0
.venv/bin/cardiag info        # adapter, network, VIN, modules
.venv/bin/cardiag codes       # stored, pending and permanent codes, plus the freeze frame
.venv/bin/cardiag monitors    # check-engine light and emissions readiness
.venv/bin/cardiag pids        # every standard live value the car offers
.venv/bin/cardiag live --log --note "cold start"
.venv/bin/cardiag sessions
.venv/bin/cardiag export 1 --out drive.csv
```

The port and speed are found automatically. Override them with `--port` and
`--baud` if needed.

If opening the port fails with "permission denied", add yourself to the
serial-port group and log in again:

```sh
sudo usermod -aG dialout $USER    # the group is uucp on Arch
```

## Web interface

```sh
.venv/bin/cardiag serve --sim focus          # try it with the simulated car
.venv/bin/cardiag serve                      # with the adapter, this machine only
.venv/bin/cardiag serve --host 0.0.0.0       # reachable from a phone or tablet
```

Open the address it prints. The server keeps retrying while the adapter is
unplugged or the ignition is off, so it can be started first. The tabs:

- **Live, Codes, Readiness, Recordings:** live values with trend lines, trouble
  codes with the freeze frame, emissions readiness, and recordings with CSV
  download.
- **Setup:** per car. Lists every standard value each module offers and which
  of the ones the other tabs want are missing; takes the engine size and
  transmission, which the car cannot report; keeps an idle baseline; and learns
  the gear ratios from a gentle drive.
- **Diagnosis:** for the live connection or any recording. Each figure against
  a healthy band, fuel trim by engine speed and load, measured air flow against
  what the engine should draw, warm-up, time in each speed band, a fuel
  estimate, and one recording against another.
- **Drive:** engine speed against road speed with a line per learned gear,
  every shift with how long it took and how far the engine flared, slip under
  load per gear, and pull times through each speed span. "Start a drive
  capture" records with only the values shifting needs, so each is read more
  often.

A link ending in `#drive`, `#diagnosis` and so on opens on that tab.

What the Drive tab can and cannot know: standard OBD-II reports no gear, no
clutch state and no transmission temperature. Everything there is worked out
from engine speed and road speed. The transmission module's own slip and
temperature figures need maker-specific requests, which cardiag does not send.
The healthy bands are general rules of thumb for petrol engines unless a
baseline marked as known good has been taken; none of them are the maker's
figures.

The Settings tab switches between the real car and the simulated ones, so
the page can be tried with no adapter plugged in. A simulation lasts until you
switch back or the app restarts, and the top of the page says "Simulation"
while one is showing.

There is no login. Use `--host 0.0.0.0` only on a network you trust.

## Raspberry Pi in the car

A Pi with the adapter in a USB port can replace the laptop: it runs the server,
and a phone or iPad on its Wi-Fi is the screen. These steps are for Raspberry
Pi OS Lite (Bookworm).

```sh
# Step 1: make the Pi its own Wi-Fi network, started at every boot
sudo nmcli device wifi hotspot ifname wlan0 con-name cardiag ssid cardiag password 'choose-a-password'
sudo nmcli connection modify cardiag connection.autoconnect yes

# Step 2: get the code and install it as a service
sudo apt install -y git python3-serial
git clone https://github.com/yycholla/cardiag.git ~/cardiag
sudo ~/cardiag/deploy/pi/install.sh
```

Step 3: join the `cardiag` Wi-Fi from the phone or iPad and open
`http://10.42.0.1:8000` (or `http://<the Pi's hostname>.local:8000`).

`install.sh` copies the app to `/opt/cardiag`, installs the `cardiag` command
and the service, and lets the service change the Pi's Wi-Fi. It can also
prepare an SD card from another computer, with no internet on the Pi:
`sudo deploy/pi/install.sh --root /path/to/rootfs --vendor DIR`, where `DIR`
holds an unpacked copy of pyserial.

### Joining your Wi-Fi

The Pi has one Wi-Fi radio, so it is either its own hotspot or on another
network, never both. The hotspot is the resting state: it starts at every
boot, and it comes back by itself if joining a network fails or that network
goes away.

To work on the Pi at home, save your Wi-Fi under Settings, then press Join.
The hotspot switches off, the Pi joins your network, and the page moves to
`http://<the Pi's hostname>.local:8000`. Press "Switch back to the hotspot"
when done, or just power the Pi off: the next boot is a hotspot again.

### A phone or tablet as the way out

Save your phone's or tablet's hotspot under Settings → "Travelling hotspot".
The Pi joins it by itself whenever it comes into range and keeps looking for it
while it is away; its own hotspot comes back whenever the other one is gone.
Other devices on that hotspot reach the page at
`http://<the Pi's hostname>.local:8000`. "Switch back to the hotspot" makes the
Pi stay on its own network until you press "Join it now" or it restarts.

Phones often stop advertising their hotspot until its settings screen is open,
so the first join after a while can need that screen opened once.

### A central server

A second copy of cardiag, on a machine that is always on, can collect every
recording so that drives can be compared over months:

```sh
cardiag serve --host 0.0.0.0 --accept-uploads
```

On the Pi, enter that machine's address under Settings → "Central server". The
Pi still records to its own disk first; whenever it can reach the central
server it sends what has not arrived yet, and keeps trying until it has.
Recordings that arrive this way are listed with the box they came from, and the
Diagnosis and Drive tabs work on them there.

Neither end has a login. Put both on a private network such as a
[Tailscale](https://tailscale.com) tailnet, and use the central server's
address on it. Live values are not relayed: for those, open the Pi itself.

### Updates

With the Pi on a network that reaches the internet, Settings → "Check for
updates" looks for a newer release of this repository on GitHub. Installing
one downloads it, runs it against the simulated Focus on the Pi, and only then
switches to it and restarts the app. The previous version is kept: if the new
one does not stay up after the restart, the Pi goes back to it by itself and
the page says so.

To publish a release, change `__version__` in `src/cardiag/__init__.py`, merge
that to `main`, and tag it with the same number:

```sh
gh release create v0.4.0 --generate-notes
```

A release whose tag and `__version__` disagree is refused by the Pi. So is one
where `cardiag --sim focus info` fails; that command is the self-test.

Things to know:

- **Who can use the page:** anyone on the same network, with no login. On the
  Pi that includes changing its Wi-Fi and installing updates.
- **Power:** a Pi 4 needs a 5 V, 3 A USB-C supply. Use a car adapter rated for it.
- **Shutdown:** cutting power without shutting down can corrupt the SD card.
- **Clock:** with no internet the Pi's clock can be wrong, so recording dates
  may be off. Elapsed times are unaffected. Checking for updates also needs
  the right time; it is set within a minute of joining Wi-Fi.

## Tests

```sh
.venv/bin/python -m pytest
```

The tests run against the simulator, including the real serial code path
through a pseudo-terminal and the web server over real HTTP. Wi-Fi switching
is tested against a stand-in for NetworkManager, and updates against a stand-in
for GitHub. The gear, shift and slip figures are tested against the simulated
geared Focus, whose faults are known. Nothing here has been run against a real
adapter or vehicle yet, and Wi-Fi switching, the travelling hotspot, uploads
and updates have not been run on a Pi yet.

One test runs the web page's script outside a browser. It needs Node.js or
QuickJS (`qjs`) and is skipped without one. It checks behaviour, not layout.

## Layout

| File | Purpose |
|---|---|
| `src/cardiag/transport.py` | Serial link to the adapter, with speed detection |
| `src/cardiag/elm.py` | ELM327 / OBDLink command driver |
| `src/cardiag/frames.py` | Reply parsing: CAN multi-frame reassembly and older networks |
| `src/cardiag/pids.py` | Standard live-data definitions and scaling |
| `src/cardiag/obd.py` | Codes, readiness, VIN, freeze frame, live values |
| `src/cardiag/store.py` | Recordings, per-car setup and settings in SQLite; CSV export |
| `src/cardiag/analysis.py` | The arithmetic: gears, shifts, slip, fuel trim map, air flow, healthy bands |
| `src/cardiag/garage.py` | Per-car setup, and reports for the live car or a recording |
| `src/cardiag/sync.py` | Sending recordings to a central server |
| `src/cardiag/service.py` | Background worker that owns the adapter and retries the connection |
| `src/cardiag/web.py` | Web server: JSON endpoints and a live event stream |
| `src/cardiag/web/index.html` | The web page |
| `src/cardiag/network.py` | The Pi's hotspot, home Wi-Fi and travelling hotspot, through NetworkManager |
| `src/cardiag/update.py` | Finding and installing releases from GitHub |
| `src/cardiag/sim.py` | Simulated adapter and vehicles |
| `src/cardiag/cli.py` | Command-line tool |
| `deploy/pi/` | Installer, service and launcher for the Pi |
