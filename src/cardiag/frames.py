"""Turn the adapter's raw reply lines into per-module messages.

The adapter is always configured with headers on and spaces off, so a CAN line
looks like ``7E8064100BE3FA813`` (identifier, then up to eight data bytes) and a
line from an older network looks like ``486B104100BE3FA811C4`` (three header
bytes, data, one checksum byte).
"""

from __future__ import annotations

from dataclasses import dataclass


class FrameError(Exception):
    """A reply from the vehicle was malformed or incomplete."""


@dataclass(frozen=True)
class Message:
    ecu: int  # CAN identifier of the responder, or its source address on older networks
    data: bytes  # diagnostic payload, starting with the response service byte


def parse_can(lines: list[str], id_bits: int = 11) -> list[Message]:
    """Reassemble ISO-TP frames into one message per reply, ordered by module."""
    id_chars = 3 if id_bits == 11 else 8
    messages: list[Message] = []
    partial: dict[int, tuple[int, bytearray]] = {}  # ecu -> (declared length, bytes so far)

    for line in lines:
        text = line.replace(" ", "")
        try:
            ecu = int(text[:id_chars], 16)
            body = bytes.fromhex(text[id_chars:])
        except ValueError as exc:
            raise FrameError(f"unreadable CAN line {line!r}") from exc
        if not body:
            continue
        kind = body[0] >> 4
        if kind == 0:  # single frame
            length = body[0] & 0x0F
            if length == 0 or length > len(body) - 1:
                raise FrameError(f"bad single-frame length in {line!r}")
            messages.append(Message(ecu, body[1 : 1 + length]))
        elif kind == 1:  # first frame of a long reply
            if len(body) < 2:
                raise FrameError(f"truncated first frame {line!r}")
            partial[ecu] = (((body[0] & 0x0F) << 8) | body[1], bytearray(body[2:]))
        elif kind == 2:  # consecutive frame; the adapter delivers these in order
            if ecu in partial:
                partial[ecu][1].extend(body[1:])
        # kind 3 is flow control, which carries no data

    for ecu, (length, collected) in partial.items():
        if len(collected) < length:
            raise FrameError(
                f"incomplete reply from module {ecu:X}: got {len(collected)} of {length} bytes"
            )
        messages.append(Message(ecu, bytes(collected[:length])))

    return sorted(messages, key=lambda message: message.ecu)


def parse_legacy(lines: list[str]) -> list[Message]:
    """Parse J1850, ISO 9141 and KWP lines: one message per line, in arrival order."""
    messages: list[Message] = []
    for line in lines:
        try:
            raw = bytes.fromhex(line.replace(" ", ""))
        except ValueError as exc:
            raise FrameError(f"unreadable line {line!r}") from exc
        if len(raw) < 5:  # three header bytes, at least one data byte, checksum
            raise FrameError(f"line too short to be a reply: {line!r}")
        messages.append(Message(ecu=raw[2], data=raw[3:-1]))
    return messages
