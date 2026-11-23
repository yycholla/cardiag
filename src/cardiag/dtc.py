"""Trouble-code encoding shared by all OBD-II vehicles."""

from __future__ import annotations

_SYSTEMS = "PCBU"  # powertrain, chassis, body, network


def decode_dtc(high: int, low: int) -> str:
    """Two raw bytes to a code such as P0171."""
    return f"{_SYSTEMS[high >> 6]}{(high >> 4) & 0x3:X}{high & 0xF:X}{low >> 4:X}{low & 0xF:X}"


def encode_dtc(code: str) -> bytes:
    """A code such as P0171 back to its two raw bytes."""
    system = _SYSTEMS.index(code[0].upper())
    digits = [int(ch, 16) for ch in code[1:5]]
    return bytes([(system << 6) | (digits[0] << 4) | digits[1], (digits[2] << 4) | digits[3]])


def parse_dtcs(data: bytes) -> list[str]:
    """A run of two-byte codes. All-zero pairs are padding and are skipped."""
    codes = []
    for i in range(0, len(data) - 1, 2):
        if data[i] or data[i + 1]:
            codes.append(decode_dtc(data[i], data[i + 1]))
    return codes
