"""Wi-Fi switching, against a stand-in for NetworkManager's `nmcli`."""

import pytest

from cardiag.network import NetworkError, Wifi, _split_terse

from conftest import wait_for


class FakeNetworkManager:
    """Answers the nmcli commands the app uses, keeping just enough state to be believable."""

    def __init__(self) -> None:
        self.connections = {"cardiag": {"ssid": "cardiag", "psk": "hotspot-pass"}}
        self.active = "cardiag"
        self.in_range = {"Home": ("82", "WPA2", "correct horse"), "Cafe: Free": ("40", "", ""), "Vault": ("55", "WPA3", "sae-secret")}
        self.commands: list[list[str]] = []
        self.broken = False
        self.cannot_rescan = False

    def __call__(self, args: list[str], timeout: float) -> str:
        self.commands.append(args)
        if self.broken:
            raise NetworkError("Error: NetworkManager is not running.")
        if args[:2] == ["-t", "-f"] and args[3:5] == ["device", "show"]:
            address = {"cardiag": "10.42.0.1/24", None: None}.get(self.active, "192.168.0.23/24")
            lines = [f"GENERAL.CONNECTION:{self.active or ''}"]
            if address:
                lines.append(f"IP4.ADDRESS[1]:{address}")
            return "\n".join(lines) + "\n"
        if args[:2] == ["-t", "-f"] and args[3:6] == ["device", "wifi", "list"]:
            if self.cannot_rescan and args[-1] == "yes":
                raise NetworkError("Error: Scanning not allowed while unavailable or activating.")
            rows = [f"{signal}:{security}:{ssid.replace(':', chr(92) + ':')}" for ssid, (signal, security, _) in self.in_range.items()]
            return "\n".join(rows + ["90:WPA2:cardiag", "30:WPA2:", "20:WPA2:Home"]) + "\n"
        if args[0] == "-g" and args[2:4] == ["connection", "show"]:
            if args[4] not in self.connections:
                raise NetworkError(f"Error: {args[4]} - no such connection profile.")
            return self.connections[args[4]]["ssid"] + "\n"
        if args[:2] == ["connection", "delete"]:
            if args[2] not in self.connections:
                raise NetworkError(f"Error: unknown connection '{args[2]}'.")
            del self.connections[args[2]]
            if self.active == args[2]:
                self.active = None
            return ""
        if args[:2] == ["connection", "add"]:
            options = dict(zip(args[2::2], args[3::2]))
            self.connections[options["con-name"]] = {
                "ssid": options["ssid"],
                "psk": options.get("wifi-sec.psk", ""),
                "key-mgmt": options.get("wifi-sec.key-mgmt"),
                "autoconnect": options["connection.autoconnect"],
            }
            return ""
        if args[0] == "--wait" and args[2:4] == ["connection", "up"]:
            name = args[4]
            wanted = self.connections[name]
            if name != "cardiag":
                if wanted["ssid"] not in self.in_range:
                    self.active = None
                    raise NetworkError(f"Error: Connection activation failed: No network with SSID '{wanted['ssid']}' found.")
                if self.in_range[wanted["ssid"]][2] != wanted["psk"]:
                    self.active = None
                    raise NetworkError("Error: Connection activation failed: Secrets were required, but not provided.")
            self.active = name
            return ""
        raise AssertionError(f"unexpected nmcli command: {args}")


@pytest.fixture
def wifi(nm):
    wifi = Wifi(run=nm, settle=0.01, watch_interval=0.02, retry_after=60)
    yield wifi
    wifi.stop()


def settled(wifi: Wifi) -> dict:
    wait_for(lambda: wifi.status()["switching"] is None)
    return wifi.status()


def test_starts_out_as_the_hotspot_with_nothing_saved(wifi):
    status = wifi.status()
    assert status["mode"] == "hotspot" and status["hotspot"] == "cardiag" and status["address"] == "10.42.0.1"
    assert status["saved"] is None and status["switching"] is None and status["problem"] is None
    with pytest.raises(ValueError, match="save a network first"):
        wifi.join()


def test_scan_lists_each_network_once_strongest_first(wifi):
    assert wifi.scan() == [
        {"ssid": "Home", "signal": 82, "security": "WPA2"},
        {"ssid": "Vault", "signal": 55, "security": "WPA3"},
        {"ssid": "Cafe: Free", "signal": 40, "security": ""},
    ]


def test_scan_makes_do_with_what_was_last_seen_when_the_radio_cannot_look(wifi, nm):
    nm.cannot_rescan = True
    assert [network["ssid"] for network in wifi.scan()] == ["Home", "Vault", "Cafe: Free"]


def test_saving_never_joins_by_itself(wifi, nm):
    wifi.save("Home", "correct horse")
    assert nm.connections["cardiag-wifi"] == {
        "ssid": "Home", "psk": "correct horse", "key-mgmt": "wpa-psk", "autoconnect": "no",
    }
    status = wifi.status()
    assert status["saved"] == "Home" and status["mode"] == "hotspot"

    wifi.save("Vault", "sae-secret")  # replaces the saved network; WPA3-only needs a different setting
    assert nm.connections["cardiag-wifi"]["key-mgmt"] == "sae"
    wifi.save("Cafe: Free", "")
    assert nm.connections["cardiag-wifi"]["key-mgmt"] is None


@pytest.mark.parametrize("ssid, password", [("", "longenough"), ("x" * 33, "longenough"), ("Home", "short"), (None, None), ("Home", 12345678)])
def test_rejects_names_and_passwords_that_cannot_work(wifi, nm, ssid, password):
    with pytest.raises(ValueError):
        wifi.save(ssid, password)
    assert "cardiag-wifi" not in nm.connections


def test_joining_and_going_back_to_the_hotspot(wifi, nm):
    wifi.save("Home", "correct horse")
    wifi.join()
    assert wifi.status()["switching"] == "Home"
    with pytest.raises(ValueError, match="already switching"):
        wifi.use_hotspot()
    status = settled(wifi)
    assert status["mode"] == "wifi" and status["address"] == "192.168.0.23" and status["problem"] is None
    with pytest.raises(ValueError, match="switch back to the hotspot"):
        wifi.save("Other", "whatever-it-is")

    wifi.use_hotspot()
    assert settled(wifi)["mode"] == "hotspot"


def test_a_wrong_password_brings_the_hotspot_back(wifi, nm):
    wifi.save("Home", "wrong password")
    wifi.join()
    status = settled(wifi)
    assert status["mode"] == "hotspot"
    assert status["problem"] == "Could not join Home: the password was not accepted. The hotspot is back on."

    wifi.save("Home", "correct horse")  # trying again clears the old complaint
    assert wifi.status()["problem"] is None


def test_a_network_out_of_range_brings_the_hotspot_back(wifi, nm):
    wifi.save("Garage", "whatever-it-is")
    wifi.join()
    status = settled(wifi)
    assert status["mode"] == "hotspot" and "that network is not in range" in status["problem"]


def test_forgetting_the_joined_network_returns_to_the_hotspot(wifi, nm):
    wifi.save("Home", "correct horse")
    wifi.join()
    settled(wifi)
    wifi.forget()
    status = settled(wifi)
    assert status["mode"] == "hotspot" and status["saved"] is None
    wifi.forget()  # nothing saved: harmless


def test_the_hotspot_is_restored_when_the_radio_is_left_with_nothing(wifi, nm):
    wifi.save("Home", "correct horse")
    wifi.join()
    settled(wifi)
    wifi.start()
    nm.active = None  # the home network went away
    wait_for(lambda: nm.active == "cardiag")


def test_failures_are_reported_not_hidden(wifi, nm):
    nm.broken = True
    with pytest.raises(NetworkError, match="not running"):
        wifi.status()
    with pytest.raises(NetworkError):
        wifi.scan()


def test_colons_in_names_survive_nmcli_escaping():
    assert _split_terse(r"40::Cafe\: Free", 3) == ["40", "", "Cafe: Free"]
    assert _split_terse(r"GENERAL.CONNECTION:back\\slash", 2) == ["GENERAL.CONNECTION", "back\\slash"]
    assert _split_terse("IP4.ADDRESS[1]:10.42.0.1/24", 2) == ["IP4.ADDRESS[1]", "10.42.0.1/24"]


# ---- the travelling hotspot: a phone or tablet that gives the box a way out ----


def ups(nm) -> int:
    return sum(1 for command in nm.commands if command[2:] == ["connection", "up", "cardiag-uplink"])


def test_the_travelling_hotspot_is_joined_when_it_comes_into_range(wifi, nm):
    wifi.save("iPad", "tablet-pass", "uplink")
    assert nm.connections["cardiag-uplink"]["autoconnect"] == "no"  # NetworkManager must not fight the app over it
    status = wifi.status()
    assert status["uplink"] == "iPad" and status["saved"] is None and status["mode"] == "hotspot" and status["uplink_auto"]

    wifi.start()
    for _ in range(10):
        wifi._stop.wait(0.02)
    assert nm.active == "cardiag" and ups(nm) == 0  # not in range: nothing is tried

    nm.in_range["iPad"] = ("70", "WPA2", "tablet-pass")
    wait_for(lambda: nm.active == "cardiag-uplink")
    assert settled(wifi)["mode"] == "uplink"

    nm.active = None  # the tablet drove off, or its hotspot went to sleep
    del nm.in_range["iPad"]
    wait_for(lambda: nm.active == "cardiag")
    nm.in_range["iPad"] = ("70", "WPA2", "tablet-pass")
    wait_for(lambda: nm.active == "cardiag-uplink")  # and it is found again when it comes back


def test_asking_for_the_own_hotspot_stops_the_wandering_until_asked_back(wifi, nm):
    nm.in_range["iPad"] = ("70", "WPA2", "tablet-pass")
    wifi.save("iPad", "tablet-pass", "uplink")
    wifi.start()
    wait_for(lambda: nm.active == "cardiag-uplink")

    wifi.use_hotspot()
    assert settled(wifi)["mode"] == "hotspot" and not wifi.status()["uplink_auto"]
    tried = ups(nm)
    for _ in range(10):
        wifi._stop.wait(0.02)
    assert nm.active == "cardiag" and ups(nm) == tried

    wifi.join("uplink")
    assert settled(wifi)["mode"] == "uplink" and wifi.status()["uplink_auto"]


def test_a_refused_travelling_hotspot_is_left_alone_for_a_while(wifi, nm):
    nm.in_range["iPad"] = ("70", "WPA2", "tablet-pass")
    wifi.save("iPad", "wrong password", "uplink")
    wifi.start()
    wait_for(lambda: wifi.status()["problem"] is not None)
    assert "Could not join iPad: the password was not accepted" in wifi.status()["problem"]
    wait_for(lambda: nm.active == "cardiag")
    for _ in range(10):
        wifi._stop.wait(0.02)
    assert ups(nm) == 1  # one refusal is not followed by a stream of them

    wifi.save("iPad", "tablet-pass", "uplink")  # correcting the password clears the wait
    wait_for(lambda: nm.active == "cardiag-uplink")


def test_home_and_travelling_networks_are_kept_apart(wifi, nm):
    wifi.save("Home", "correct horse")
    wifi.save("iPad", "tablet-pass", "uplink")
    status = wifi.status()
    assert (status["saved"], status["uplink"]) == ("Home", "iPad")
    wifi.forget("uplink")
    status = wifi.status()
    assert (status["saved"], status["uplink"]) == ("Home", None)
    with pytest.raises(ValueError, match="'home' or 'uplink'"):
        wifi.save("Other", "whatever-it-is", "office")
