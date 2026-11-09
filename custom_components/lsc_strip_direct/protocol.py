"""Pure-python protocol helpers for LSC RGBIC+CCT strips (DP61 white scheme)."""
from __future__ import annotations

import base64

DP_SWITCH = "20"
DP_MODE = "21"
DP_COLOUR = "24"
DP_WHITE = "61"

MODE_WHITE = "white"
MODE_COLOUR = "colour"

# Colour value written before switching to white (needed when coming from colour)
COLOUR_RESET = "00d200000000"

MIN_KELVIN = 2700
MAX_KELVIN = 6500


def _clamp(value: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(value))))


def encode_white(brightness_pct: float, temp_pct: float) -> str:
    """DP61 payload. brightness 1-100, temp 0 (warm) - 100 (cold)."""
    b = _clamp(brightness_pct, 1, 100)
    t = _clamp(temp_pct, 0, 100)
    return base64.b64encode(bytes([0, 0, 0, 0x14, 0, b, t])).decode()


def decode_white(payload: str) -> tuple[int, int] | None:
    """Return (brightness_pct, temp_pct) or None if payload is not valid."""
    try:
        raw = base64.b64decode(payload)
    except Exception:  # noqa: BLE001
        return None
    if len(raw) != 7:
        return None
    return raw[5], raw[6]


def encode_colour(hue: float, sat_pct: float, val_pct: float) -> str:
    """DP24 payload HHHHSSSSVVVV (hue 0-360, sat/val 0-1000)."""
    h = _clamp(hue, 0, 360)
    s = _clamp(sat_pct * 10, 0, 1000)
    v = _clamp(val_pct * 10, 10, 1000)
    return f"{h:04x}{s:04x}{v:04x}"


def decode_colour(payload: str) -> tuple[int, float, float] | None:
    """Return (hue, sat_pct, val_pct) or None."""
    try:
        if len(payload) != 12:
            return None
        return (
            int(payload[0:4], 16),
            int(payload[4:8], 16) / 10,
            int(payload[8:12], 16) / 10,
        )
    except ValueError:
        return None


def kelvin_to_temp_pct(kelvin: int) -> int:
    kelvin = max(MIN_KELVIN, min(MAX_KELVIN, kelvin))
    return _clamp((kelvin - MIN_KELVIN) * 100 / (MAX_KELVIN - MIN_KELVIN), 0, 100)


def temp_pct_to_kelvin(temp_pct: int) -> int:
    return _clamp(MIN_KELVIN + temp_pct * (MAX_KELVIN - MIN_KELVIN) / 100, MIN_KELVIN, MAX_KELVIN)


def brightness255_to_pct(brightness: int) -> int:
    return _clamp(brightness * 100 / 255, 1, 100)


def pct_to_brightness255(pct: float) -> int:
    return _clamp(pct * 255 / 100, 1, 255)
