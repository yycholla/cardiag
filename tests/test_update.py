"""Finding, installing and undoing updates, against a stand-in for GitHub."""

import io
import json
import os
import subprocess
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import cardiag
from cardiag.update import UpdateError, Updater, parse_version

PACKAGE = Path(cardiag.__file__).parent
LAUNCHER = Path(__file__).parent.parent / "deploy" / "pi" / "cardiag"


def release_archive(version: str, *, change=None, extra=()) -> bytes:
    """A source archive shaped like the ones GitHub serves: one top directory, then the checkout."""
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        def add(name: str, data: bytes) -> None:
            info = tarfile.TarInfo(f"yycholla-cardiag-abc1234/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        add("README.md", b"not part of the app\n")
        for path in sorted(PACKAGE.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(PACKAGE).as_posix()
            data = path.read_bytes()
            if relative == "__init__.py":
                data = data.replace(cardiag.__version__.encode(), version.encode())
            if change and relative in change:
                data = change[relative]
            add(f"src/cardiag/{relative}", data)
        for member in extra:
            tar.addfile(member, io.BytesIO(b"x" * member.size))
    return out.getvalue()


class FakeGitHub:
    def __init__(self) -> None:
        self.latest: dict | None = None
        self.archives: dict[str, bytes] = {}
        hub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def do_GET(self) -> None:
                body = None
                if self.path == "/repos/yycholla/cardiag/releases/latest" and hub.latest:
                    body = json.dumps(hub.latest).encode()
                elif self.path.startswith("/repos/yycholla/cardiag/tarball/"):
                    body = hub.archives.get(self.path.rsplit("/", 1)[1])
                self.send_response(200 if body is not None else 404)
                self.send_header("Content-Length", str(len(body or b"")))
                self.end_headers()
                self.wfile.write(body or b"")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def publish(self, version: str, notes: str = "", **archive_options) -> None:
        self.latest = {"tag_name": f"v{version}", "body": notes}
        self.archives[f"v{version}"] = release_archive(version, **archive_options)


def installed_versions(home: Path) -> list[str]:
    return sorted(path.name for path in (home / "releases").iterdir())


def test_version_numbers_compare_by_value():
    assert parse_version("v0.10.0") > parse_version("0.9.9")
    for bad in ("", "1.2", "v1.2.3-rc1", "latest"):
        with pytest.raises(UpdateError):
            parse_version(bad)


def test_check_finds_a_newer_release(github, home):
    updater = Updater(home, api=github.url)
    github.publish("9.0.0", notes="Fixes the thing.\n")
    assert updater.check() == {
        "managed": True, "current": cardiag.__version__, "rolled_back": None,
        "latest": "9.0.0", "available": True, "notes": "Fixes the thing.",
    }
    github.publish(cardiag.__version__, notes="what is already here")
    found = updater.check()
    assert found["available"] is False and found["notes"] == ""


def test_install_switches_to_the_new_release_and_keeps_the_old_one(github, home):
    github.publish("9.0.0")
    updater = Updater(home, api=github.url)
    assert updater.install() == {"installed": "9.0.0"}

    assert os.readlink(home / "current") == "releases/9.0.0"
    assert os.readlink(home / "previous") == f"releases/{cardiag.__version__}"
    assert '__version__ = "9.0.0"' in (home / "current" / "src" / "cardiag" / "__init__.py").read_text()
    assert (home / "current" / "src" / "cardiag" / "web" / "index.html").is_file()
    assert not (home / "current" / "README.md").exists()  # only the app itself is copied
    assert (home / "pending").read_text() == "9.0.0\n"
    assert installed_versions(home) == sorted([cardiag.__version__, "9.0.0"])

    updater.confirm()  # still the old version running: the new one has proved nothing yet
    assert (home / "pending").read_text() == "9.0.0\n"
    Updater(home, api=github.url, current="9.0.0").confirm()  # the new version, after its restart
    assert not (home / "pending").exists()

    # The next update drops the oldest copy and keeps one to go back to.
    github.publish("9.1.0")
    Updater(home, api=github.url, current="9.0.0").install()
    assert installed_versions(home) == ["9.0.0", "9.1.0"]
    assert os.readlink(home / "previous") == "releases/9.0.0"


def test_nothing_to_install_when_already_up_to_date(github, home):
    github.publish(cardiag.__version__)
    with pytest.raises(UpdateError, match="already the latest"):
        Updater(home, api=github.url).install()


def test_a_release_that_does_not_run_is_not_installed(github, home):
    github.publish("9.0.0", change={"obd.py": b"def broken(:\n"})
    with pytest.raises(UpdateError, match="failed its self-test"):
        Updater(home, api=github.url).install()
    assert os.readlink(home / "current") == f"releases/{cardiag.__version__}"
    assert installed_versions(home) == [cardiag.__version__]  # nothing left lying around
    assert not (home / "pending").exists() and not (home / "previous").exists()


def test_a_mislabelled_release_is_not_installed(github, home):
    github.publish("9.0.0")
    github.archives["v9.0.0"] = release_archive("8.0.0")
    with pytest.raises(UpdateError, match="mislabelled: its code says it is version 8.0.0"):
        Updater(home, api=github.url).install()
    assert installed_versions(home) == [cardiag.__version__]


def test_an_archive_cannot_write_outside_its_release(github, home, tmp_path):
    def member(name: str, kind: bytes = tarfile.REGTYPE, link: str = "") -> tarfile.TarInfo:
        info = tarfile.TarInfo(name)
        info.type, info.linkname, info.size = kind, link, 0 if link else 4
        return info

    github.publish("9.0.0", extra=[
        member("top/src/cardiag/../../../../escaped.txt"),
        member("/tmp/absolute.txt"),
        member("top/src/cardiag/link.py", tarfile.SYMTYPE, "/etc/passwd"),
        member("top/elsewhere/not-the-app.py"),
    ])
    Updater(home, api=github.url).install()
    release = home / "releases" / "9.0.0"
    assert not list(tmp_path.rglob("escaped.txt")) and not (release / "src" / "cardiag" / "link.py").exists()
    assert sorted(path.name for path in release.iterdir()) == ["src"]
    assert sorted(path.name for path in (release / "src").iterdir()) == ["cardiag"]


def test_problems_reaching_github_are_explained(github, home, tmp_path):
    with pytest.raises(UpdateError, match="no release has been published yet"):
        Updater(home, api=github.url).check()
    github.server.shutdown()
    github.server.server_close()
    with pytest.raises(UpdateError, match="join a Wi-Fi network first"):
        Updater(home, api=github.url).check()


def test_a_copy_that_was_not_installed_for_updates_says_so(github, tmp_path):
    github.publish("9.0.0")
    with pytest.raises(UpdateError, match="not installed in a way that lets it update itself"):
        Updater(tmp_path, api=github.url).install()


# ---- the launcher script: going back when an update does not start ---------

def launch(home: Path, *, service: bool) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ["PATH"], "CARDIAG_HOME": str(home)}
    if service:
        env["CARDIAG_SERVICE"] = "1"
    return subprocess.run([str(LAUNCHER), "--version"], capture_output=True, text=True, timeout=60, env=env)


needs_system_python = pytest.mark.skipif(
    subprocess.run(
        ["/usr/bin/python3", "-c", "import sys; sys.exit(sys.version_info < (3, 10))"], capture_output=True
    ).returncode != 0 if Path("/usr/bin/python3").exists() else True,
    reason="the launcher runs /usr/bin/python3, which must be Python 3.10 or newer",
)


@needs_system_python
def test_launcher_runs_the_current_release(home):
    result = launch(home, service=True)
    assert result.stdout == f"cardiag {cardiag.__version__}\n", result.stderr


@needs_system_python
def test_an_update_that_never_confirms_is_undone_on_the_second_start(github, home):
    github.publish("9.0.0")
    updater = Updater(home, api=github.url)
    updater.install()

    assert launch(home, service=False).stdout == "cardiag 9.0.0\n"  # running it by hand does not count
    assert not (home / "pending.tried").exists()
    assert launch(home, service=True).stdout == "cardiag 9.0.0\n"  # first start: given its chance
    assert (home / "pending.tried").exists()

    second = launch(home, service=True)  # still unconfirmed: it did not stay up
    assert second.stdout == f"cardiag {cardiag.__version__}\n"
    assert "version 9.0.0 did not start" in second.stderr
    assert os.readlink(home / "current") == f"releases/{cardiag.__version__}"
    assert not (home / "pending").exists() and not (home / "pending.tried").exists()
    assert updater.status()["rolled_back"] == "9.0.0"


@needs_system_python
def test_the_old_version_confirming_late_does_not_spoil_the_undo(github, home):
    github.publish("9.0.0")
    updater = Updater(home, api=github.url)
    updater.install()
    updater.confirm()  # the old version's start-up timer firing just after the install
    assert launch(home, service=True).stdout == "cardiag 9.0.0\n"
    assert launch(home, service=True).stdout == f"cardiag {cardiag.__version__}\n"  # still undone
    assert updater.status()["rolled_back"] == "9.0.0"


@needs_system_python
def test_a_confirmed_update_stays(github, home):
    github.publish("9.0.0")
    updater = Updater(home, api=github.url)
    updater.install()
    assert launch(home, service=True).stdout == "cardiag 9.0.0\n"
    Updater(home, api=github.url, current="9.0.0").confirm()
    assert not (home / "pending.tried").exists()
    assert launch(home, service=True).stdout == "cardiag 9.0.0\n"
    assert launch(home, service=True).stdout == "cardiag 9.0.0\n"
    assert updater.status()["rolled_back"] is None
