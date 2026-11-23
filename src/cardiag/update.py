"""Updates for an installed copy: find a newer release on GitHub, fetch it, switch to it.

An installed copy lives in a home directory laid out like this:

    releases/0.2.0/src/cardiag/...   one directory per installed version
    current  -> releases/0.2.0       the version that runs
    previous -> releases/0.1.0       the one before, kept for going back

Installing a release downloads its source, checks that it runs here, and points
`current` at it. The service then restarts into the new version. The file
`pending` marks an update that has not yet proved it can start: the launcher
script goes back to `previous` if the new version fails to come up, and
`confirm()` removes the mark once it has.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath

import serial

from . import __version__

REPOSITORY = "yycholla/cardiag"
_MAX_DOWNLOAD = 20 * 1024 * 1024
_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


class UpdateError(Exception):
    """An update could not be checked for or installed."""


def parse_version(text: str) -> tuple[int, int, int]:
    match = _VERSION.fullmatch(text.strip())
    if not match:
        raise UpdateError(f"{text!r} is not a version number like 1.2.3")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


class Updater:
    def __init__(
        self,
        home: str | os.PathLike,
        *,
        repository: str = REPOSITORY,
        api: str = "https://api.github.com",
        current: str = __version__,
    ) -> None:
        self.home = Path(home)
        self.current = current
        self._base = f"{api}/repos/{repository}"
        self._lock = threading.Lock()

    # ---- reading -----------------------------------------------------------

    def status(self) -> dict:
        return {"managed": True, "current": self.current, "rolled_back": self._note("rolled-back")}

    def check(self) -> dict:
        """Ask GitHub for the latest release and say whether it is newer than this copy."""
        release = json.loads(self._fetch(f"{self._base}/releases/latest"))
        latest = str(release.get("tag_name", "")).removeprefix("v")
        newer = parse_version(latest) > parse_version(self.current)
        return {
            **self.status(),
            "latest": latest,
            "available": newer,
            "notes": str(release.get("body") or "").strip()[:2000] if newer else "",
        }

    # ---- installing --------------------------------------------------------

    def install(self) -> dict:
        """Install the latest release. The caller restarts the app afterwards."""
        if not self._lock.acquire(blocking=False):
            raise UpdateError("an update is already being installed")
        try:
            if not (self.home / "current").is_symlink():
                raise UpdateError("this copy of cardiag was not installed in a way that lets it update itself")
            found = self.check()
            if not found["available"]:
                raise UpdateError(f"version {self.current} is already the latest")
            version = found["latest"]
            releases = self.home / "releases"
            with tempfile.TemporaryDirectory(dir=releases, prefix=".incoming-") as work:
                archive = Path(work) / "source.tar.gz"
                archive.write_bytes(self._fetch(f"{self._base}/tarball/v{version}"))
                staged = Path(work) / "release"
                self._unpack(archive, staged)
                self._prove(staged, version)
                final = releases / version
                if final.exists():
                    shutil.rmtree(final)
                staged.rename(final)
            self._switch_to(version)
            return {"installed": version}
        finally:
            self._lock.release()

    def confirm(self) -> None:
        """The running version started properly; an update no longer needs undoing."""
        for name in ("pending", "pending.tried"):
            (self.home / name).unlink(missing_ok=True)

    # ---- steps ---------------------------------------------------------------

    def _fetch(self, url: str) -> bytes:
        request = urllib.request.Request(
            url, headers={"User-Agent": f"cardiag/{self.current}", "Accept": "application/vnd.github+json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read(_MAX_DOWNLOAD + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise UpdateError("no release has been published yet") from None
            if exc.code in (403, 429):
                raise UpdateError("GitHub is turning requests away for now; try again in an hour") from None
            raise UpdateError(f"GitHub answered with an error ({exc.code})") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if isinstance(getattr(exc, "reason", None), ssl.SSLCertVerificationError):
                raise UpdateError(
                    "could not verify GitHub's identity; the clock here may be wrong. "
                    "Wait a minute after joining Wi-Fi and try again"
                ) from None
            raise UpdateError(
                "could not reach GitHub. Updates need internet access, so join a Wi-Fi network first"
            ) from None
        if len(body) > _MAX_DOWNLOAD:
            raise UpdateError("the download is far larger than a release should be")
        return body

    @staticmethod
    def _unpack(archive: Path, into: Path) -> None:
        """Copy out the package's own files and nothing else, wherever the archive says to put them."""
        copied = 0
        try:
            with tarfile.open(archive, "r:gz") as tar:
                for member in tar:
                    parts = PurePosixPath(member.name).parts[1:]  # drop the archive's top directory
                    if parts[:2] != ("src", "cardiag") or ".." in parts or not member.isfile():
                        continue
                    target = into.joinpath(*parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = tar.extractfile(member)
                    assert source is not None  # isfile() was checked
                    target.write_bytes(source.read())
                    copied += 1
        except (tarfile.TarError, EOFError, OSError) as exc:
            raise UpdateError(f"the download could not be unpacked ({exc})") from None
        if not copied:
            raise UpdateError("the download does not contain the app")

    @staticmethod
    def _prove(staged: Path, version: str) -> None:
        """Run the new version against the simulated car before trusting it with the real one."""
        source = staged / "src"
        stated = re.search(r'^__version__ = "([^"]+)"', (source / "cardiag" / "__init__.py").read_text(), re.M)
        if not stated or stated.group(1) != version:
            says = stated.group(1) if stated else "nothing"
            raise UpdateError(f"release {version} is mislabelled: its code says it is version {says}")
        libraries = Path(serial.__file__).resolve().parent.parent  # wherever pyserial is on this machine
        try:
            trial = subprocess.run(
                [sys.executable, "-m", "cardiag", "--sim", "focus", "info"],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=staged,
                env={**os.environ, "PYTHONPATH": f"{source}{os.pathsep}{libraries}", "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except subprocess.TimeoutExpired:
            raise UpdateError(f"version {version} did not finish its self-test, so it was not installed") from None
        if trial.returncode != 0 or "VIN" not in trial.stdout:
            raise UpdateError(f"version {version} failed its self-test here, so it was not installed")

    def _switch_to(self, version: str) -> None:
        was = os.readlink(self.home / "current")
        if Path(was).name != version:
            self._point("previous", was)
        (self.home / "pending").write_text(version + "\n")
        (self.home / "pending.tried").unlink(missing_ok=True)
        (self.home / "rolled-back").unlink(missing_ok=True)
        self._point("current", f"releases/{version}")
        keep = {version, Path(was).name}
        for old in (self.home / "releases").iterdir():
            if old.is_dir() and old.name not in keep:
                shutil.rmtree(old, ignore_errors=True)

    def _point(self, link: str, target: str) -> None:
        """Repoint a link in one step, so there is never a moment without it."""
        fresh = self.home / f".{link}.new"
        fresh.unlink(missing_ok=True)
        fresh.symlink_to(target)
        os.replace(fresh, self.home / link)

    def _note(self, name: str) -> str | None:
        try:
            return (self.home / name).read_text().strip() or None
        except OSError:
            return None
