"""Byte-level links between the app and an ELM327-style adapter."""

from __future__ import annotations

import time
from typing import Protocol

import serial


class LinkError(Exception):
    """The link to the adapter could not be set up."""


class Transport(Protocol):
    """Anything that can carry command text to an adapter and bring replies back."""

    def write(self, data: bytes) -> None: ...

    def read(self) -> bytes:
        """Return whatever has arrived, or b"" after a short wait."""
        ...

    def flush_input(self) -> None: ...

    def close(self) -> None: ...


class SerialTransport:
    """A USB or Bluetooth serial port, such as /dev/ttyUSB0 for the OBDLink EX."""

    # Tried in this order when no speed is given. OBDLink adapters ship at 115200.
    BAUD_RATES = (115200, 38400, 9600, 230400, 57600, 19200, 500000, 1000000, 2000000)

    def __init__(self, port: str, baud: int | None = None) -> None:
        self.port = port
        self._serial = serial.Serial(
            port, baud or self.BAUD_RATES[0], timeout=0.05, write_timeout=2
        )
        if baud is None:
            try:
                self._find_baud()
            except BaseException:
                self._serial.close()
                raise

    def _find_baud(self) -> None:
        for baud in self.BAUD_RATES:
            self._serial.baudrate = baud
            self._serial.reset_input_buffer()
            # Not a real command: any ELM327 answers "?" followed by its ">" prompt,
            # which only arrives intact when the speed matches.
            self._serial.write(b"\x7f\x7f\r")
            deadline = time.monotonic() + 0.4
            seen = b""
            while time.monotonic() < deadline:
                seen += self.read()
                if seen.endswith(b">"):
                    return
        raise LinkError(
            f"nothing on {self.port} answered like an OBD adapter at any common speed; "
            "check the cable, or pass --baud if the adapter uses an unusual rate"
        )

    def write(self, data: bytes) -> None:
        self._serial.write(data)

    def read(self) -> bytes:
        waiting = self._serial.in_waiting
        return self._serial.read(waiting or 1)

    def flush_input(self) -> None:
        self._serial.reset_input_buffer()

    def close(self) -> None:
        self._serial.close()
