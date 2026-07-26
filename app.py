#!/usr/bin/env python3
"""Authenticated-loopback web API for EqualizerCast."""

from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import threading
import time
import urllib.request
import zlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("EQUALIZERCAST_STATE_DIR", "/var/lib/equalizercast"))
STATE_FILE = STATE_DIR / "settings.json"
KEY_FILE = Path(os.environ.get("LIQUIDSOAP_API_KEY_FILE", "/etc/equalizercast/liquidsoap-api-key"))
CONTROLS = json.loads((BASE / "controls.json").read_text())
PRESETS = json.loads((BASE / "presets.json").read_text())
EQ = CONTROLS["equalizer"]
LOCK = threading.RLock()
TONE_TIMER: threading.Timer | None = None


def control_spec() -> dict[str, dict]:
    specs = {CONTROLS["output"]["name"]: CONTROLS["output"]}
    specs[CONTROLS["tone"]["frequency"]["name"]] = CONTROLS["tone"]["frequency"]
    specs[CONTROLS["tone"]["amplitude"]["name"]] = CONTROLS["tone"]["amplitude"]
    return specs


SPECS = control_spec()
DEFAULTS = {name: spec["value"] for name, spec in SPECS.items()}
DEFAULTS[CONTROLS["tone"]["enabled"]["name"]] = False
DEFAULT_BANDS = [band.copy() for band in CONTROLS["bands"]]


def validate_bands(value) -> list[dict[str, float]]:
    if not isinstance(value, list):
        raise ValueError("Bands must be a list")
    if not EQ["min_bands"] <= len(value) <= EQ["max_bands"]:
        raise ValueError(f"Band count must be between {EQ['min_bands']} and {EQ['max_bands']}")
    bands = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"Band {index + 1} must be an object")
        band = {}
        for field, minimum, maximum in (
            ("frequency", EQ["frequency_min"], EQ["frequency_max"]),
            ("gain", EQ["gain_min"], EQ["gain_max"]),
            ("q", EQ["q_min"], EQ["q_max"]),
        ):
            number = float(raw.get(field))
            if not math.isfinite(number) or not minimum <= number <= maximum:
                raise ValueError(f"Band {index + 1} {field} must be between {minimum} and {maximum}")
            band[field] = number
        bands.append(band)
    frequencies = [band["frequency"] for band in bands]
    if any(left >= right for left, right in zip(frequencies, frequencies[1:])):
        raise ValueError("Band frequencies must be unique and in increasing order")
    return bands


def load_state() -> tuple[dict, list[dict[str, float]]]:
    try:
        saved = json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    saved_values = saved.get("values", {}) if saved.get("version") == 2 else saved
    if not isinstance(saved_values, dict):
        saved_values = {}
    state = DEFAULTS.copy()
    for name, value in saved_values.items():
        if name in state and name != "eq.tone.enabled":
            state[name] = value
    state["eq.tone.enabled"] = False
    try:
        bands = validate_bands(saved["bands"]) if saved.get("version") == 2 else [
            {
                **band,
                "gain": float(saved.get(f"eq.gain.{band['frequency']}", band["gain"])),
            }
            for band in DEFAULT_BANDS
        ]
    except (KeyError, TypeError, ValueError):
        bands = [band.copy() for band in DEFAULT_BANDS]
    return state, bands


STATE, BANDS = load_state()


def save_state() -> None:
    STATE_DIR.mkdir(mode=0o750, parents=True, exist_ok=True)
    persistent = {key: value for key, value in STATE.items() if key != "eq.tone.enabled"}
    with tempfile.NamedTemporaryFile("w", dir=STATE_DIR, delete=False) as stream:
        json.dump({"version": 2, "values": persistent, "bands": BANDS}, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temp_name = stream.name
    os.chmod(temp_name, 0o640)
    os.replace(temp_name, STATE_FILE)


def api_key() -> str:
    key = os.environ.get("LIQUIDSOAP_API_KEY", "").strip()
    if not key:
        try:
            key = KEY_FILE.read_text().strip()
        except FileNotFoundError as exc:
            raise RuntimeError(f"Liquidsoap API key file not found: {KEY_FILE}") from exc
    if not key:
        raise RuntimeError("Liquidsoap API key is empty")
    return key


def liquidsoap_url() -> str:
    override = os.environ.get("LIQUIDSOAP_API_URL", "").strip()
    if override:
        return override
    container = os.environ.get("AZURACAST_CONTAINER", "azuracast")
    address = subprocess.check_output(
        ["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", container],
        text=True,
        timeout=3,
    ).strip()
    port = int(os.environ.get("LIQUIDSOAP_API_PORT", "8004"))
    return f"http://{address}:{port}/telnet"


def liquidsoap(command: str) -> str:
    request = urllib.request.Request(
        liquidsoap_url(),
        data=command.encode(),
        method="POST",
        headers={"x-liquidsoap-api-key": api_key(), "Content-Type": "text/plain"},
    )
    with urllib.request.urlopen(request, timeout=4) as response:
        return response.read().decode().strip()


def runtime_set(name: str, value) -> str:
    encoded = "true" if value is True else "false" if value is False else f"{float(value):.6f}"
    result = liquidsoap(f"var.set {name} = {encoded}")
    if "not found" in result.lower() or "syntax error" in result.lower():
        raise RuntimeError(result)
    return result


def band_revision(bands: list[dict[str, float]]) -> int:
    encoded = json.dumps(bands, sort_keys=True, separators=(",", ":")).encode()
    return zlib.crc32(encoded)


def stop_tone() -> None:
    global TONE_TIMER
    with LOCK:
        STATE["eq.tone.enabled"] = False
        try:
            runtime_set("eq.tone.enabled", False)
        except Exception:
            pass
        TONE_TIMER = None


def start_tone_timer() -> None:
    global TONE_TIMER
    if TONE_TIMER:
        TONE_TIMER.cancel()
    TONE_TIMER = threading.Timer(30.0, stop_tone)
    TONE_TIMER.daemon = True
    TONE_TIMER.start()


def apply_bands(bands: list[dict[str, float]]) -> None:
    """Replace the live EQ curve without exposing an in-between filter sweep."""
    runtime_set("eq.band.count", 0)
    for index, band in enumerate(bands):
        runtime_set(f"eq.band.{index}.frequency", band["frequency"])
        runtime_set(f"eq.band.{index}.q", band["q"])
        runtime_set(f"eq.band.{index}.gain", band["gain"])
    runtime_set("eq.band.count", len(bands))
    runtime_set("eq.band.revision", band_revision(bands))


def apply_all() -> None:
    with LOCK:
        runtime_set("eq.tone.enabled", False)
        STATE["eq.tone.enabled"] = False
        for name, value in STATE.items():
            if name != "eq.tone.enabled":
                runtime_set(name, value)
        apply_bands(BANDS)


def monitor_runtime() -> None:
    while True:
        try:
            with LOCK:
                current = liquidsoap("var.get eq.output.gain")
                expected = float(STATE["eq.output.gain"])
                band_count = liquidsoap("var.get eq.band.count")
                revision = liquidsoap("var.get eq.band.revision")
                if (
                    abs(float(current) - expected) > 0.0005
                    or int(float(band_count)) != len(BANDS)
                    or int(float(revision)) != band_revision(BANDS)
                ):
                    apply_all()
        except Exception:
            pass
        time.sleep(5)


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".css": "text/css"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE / "static"), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'")
        super().end_headers()

    def json_response(self, status: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/state":
            with LOCK:
                payload = {
                    "controls": CONTROLS,
                    "values": STATE.copy(),
                    "bands": [band.copy() for band in BANDS],
                    "presets": PRESETS,
                    "tone_seconds": 30,
                }
            return self.json_response(200, payload)
        if self.path == "/health":
            return self.json_response(200, {"ok": True})
        return super().do_GET()

    def do_POST(self):
        if self.headers.get("X-Equalizer-Request") != "1":
            return self.json_response(403, {"error": "Missing request guard"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 32768:
                raise ValueError("Request too large")
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("Request body must be a JSON object")
            if self.path == "/api/set":
                return self.handle_set(data)
            if self.path == "/api/reset":
                return self.handle_reset()
            if self.path == "/api/bands":
                return self.handle_bands(data)
            if self.path == "/api/tone":
                return self.handle_tone(data)
            return self.json_response(404, {"error": "Not found"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self.json_response(400, {"error": str(exc)})
        except Exception as exc:
            return self.json_response(503, {"error": str(exc)})

    def handle_set(self, data: dict):
        name = str(data.get("name", ""))
        if name.startswith("eq.band.") and name.endswith(".gain"):
            try:
                index = int(name.split(".")[2])
            except (IndexError, ValueError) as exc:
                raise ValueError("Unknown control") from exc
            value = float(data.get("value"))
            if not math.isfinite(value) or not EQ["gain_min"] <= value <= EQ["gain_max"]:
                raise ValueError(f"Value must be between {EQ['gain_min']} and {EQ['gain_max']}")
            with LOCK:
                if not 0 <= index < len(BANDS):
                    raise ValueError("Unknown control")
                previous = BANDS[index]["gain"]
                candidate = [band.copy() for band in BANDS]
                candidate[index]["gain"] = value
                try:
                    runtime_set(name, value)
                    runtime_set("eq.band.revision", band_revision(candidate))
                except Exception:
                    try:
                        runtime_set(name, previous)
                        runtime_set("eq.band.revision", band_revision(BANDS))
                    except Exception:
                        pass
                    raise
                BANDS[index] = candidate[index]
                save_state()
            return self.json_response(200, {"ok": True, "name": name, "value": value})
        if name not in SPECS:
            raise ValueError("Unknown control")
        value = float(data.get("value"))
        if not math.isfinite(value):
            raise ValueError("Value must be finite")
        spec = SPECS[name]
        if not float(spec["min"]) <= value <= float(spec["max"]):
            raise ValueError(f"Value must be between {spec['min']} and {spec['max']}")
        with LOCK:
            runtime_set(name, value)
            STATE[name] = value
            save_state()
        return self.json_response(200, {"ok": True, "name": name, "value": value})

    def handle_bands(self, data: dict):
        global BANDS
        bands = validate_bands(data.get("bands"))
        with LOCK:
            previous = BANDS
            try:
                apply_bands(bands)
            except Exception:
                try:
                    apply_bands(previous)
                except Exception:
                    pass
                raise
            BANDS = bands
            save_state()
        return self.json_response(200, {"ok": True, "bands": [band.copy() for band in BANDS]})

    def handle_tone(self, data: dict):
        enabled = data.get("enabled") is True
        with LOCK:
            runtime_set("eq.tone.enabled", enabled)
            STATE["eq.tone.enabled"] = enabled
            if enabled:
                start_tone_timer()
            else:
                stop_tone()
        return self.json_response(200, {"ok": True, "enabled": enabled, "auto_stop_seconds": 30})

    def handle_reset(self):
        global BANDS
        with LOCK:
            STATE.update(DEFAULTS)
            BANDS = [band.copy() for band in DEFAULT_BANDS]
            STATE["eq.tone.enabled"] = False
            apply_all()
            save_state()
        return self.json_response(200, {"ok": True, "values": STATE.copy()})

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}", flush=True)


if __name__ == "__main__":
    STATE_DIR.mkdir(mode=0o750, parents=True, exist_ok=True)
    stop_tone()
    threading.Thread(target=monitor_runtime, daemon=True).start()
    host = os.environ.get("EQUALIZERCAST_HOST", "127.0.0.1")
    port = int(os.environ.get("EQUALIZERCAST_PORT", "8767"))
    ThreadingHTTPServer((host, port), Handler).serve_forever()
