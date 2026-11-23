# cardiag

Car diagnostics over OBD-II for Linux. It reads trouble codes, readiness
monitors and live data, and records sessions, from the command line or from a
web page that a phone, tablet or laptop can open. It sends read requests only.

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

Two simulated vehicles are built in:

```sh
.venv/bin/cardiag --sim focus info
.venv/bin/cardiag --sim focus codes
.venv/bin/cardiag --sim tahoe codes
.venv/bin/cardiag --sim focus live
```

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

Open the address it prints. The page shows live values with trend lines, codes,
readiness, and recordings with CSV download. The server keeps retrying while
the adapter is unplugged or the ignition is off, so it can be started first.

There is no login. Use `--host 0.0.0.0` only on a network you trust.

## Raspberry Pi in the car

A Pi with the adapter in a USB port can replace the laptop: it runs the server,
and a phone or iPad on its Wi-Fi is the screen. These steps are for Raspberry
Pi OS (Bookworm) and have not been run on a Pi yet.

```sh
# Step 1: get the code and install it. The repository is private, so sign in
# to GitHub first; `gh auth login` gives a code to enter on your phone.
sudo apt install -y git gh python3-venv
gh auth login
gh repo clone yycholla/cardiag ~/cardiag
python3 -m venv ~/cardiag/.venv
~/cardiag/.venv/bin/pip install -e ~/cardiag
sudo usermod -aG dialout $USER

# Step 2: make the Pi its own Wi-Fi network, started at every boot
sudo nmcli device wifi hotspot ifname wlan0 ssid cardiag password 'choose-a-password'
sudo nmcli connection modify Hotspot connection.autoconnect yes
```

Step 3: start the server at boot. Save this as `/etc/systemd/system/cardiag.service`,
replacing `pi` with your username, then run
`sudo systemctl enable --now cardiag`:

```ini
[Unit]
Description=cardiag web interface
After=network.target

[Service]
User=pi
ExecStart=/home/pi/cardiag/.venv/bin/cardiag serve --host 0.0.0.0
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Step 4: join the `cardiag` Wi-Fi from the phone or iPad and open
`http://10.42.0.1:8000`.

Things to know:

- **Power:** a Pi 4 needs a 5 V, 3 A USB-C supply. Use a car adapter rated for it.
- **Shutdown:** cutting power without shutting down can corrupt the SD card.
- **Clock:** with no internet the Pi's clock can be wrong, so recording dates
  may be off. Elapsed times are unaffected.

## Tests

```sh
.venv/bin/python -m pytest
```

The tests run against the simulator, including the real serial code path
through a pseudo-terminal and the web server over real HTTP. Nothing here has
been run against a real adapter or vehicle yet.

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
| `src/cardiag/store.py` | Session recording in SQLite, CSV export |
| `src/cardiag/service.py` | Background worker that owns the adapter and retries the connection |
| `src/cardiag/web.py` | Web server: JSON endpoints and a live event stream |
| `src/cardiag/web/index.html` | The web page |
| `src/cardiag/sim.py` | Simulated adapter and vehicles |
| `src/cardiag/cli.py` | Command-line tool |
