# EqualizerCast

EqualizerCast is a small, dependency-free web control panel for a Liquidsoap
equalizer running in AzuraCast. Band count, frequency, Q, gain, and output
changes reach the stream immediately and are persisted locally. It includes
more than 40 built-in presets and a sweepable sine tone
that overlays the music and automatically stops after 30 seconds.

## Safety and privacy

- The server binds to `127.0.0.1` by default. Put authentication in front of it
  before exposing it through a reverse proxy.
- The request header used by the browser is a CSRF guard, not authentication.
- Keep the Liquidsoap API key in a root-readable file or environment variable.
- Runtime settings, snapshots, `.env`, logs, database data, and keys are ignored
  by Git. No station-specific credentials or data are included in this repo.
- The tone is transmitted on air. It is capped by Liquidsoap and automatically
  disabled after 30 seconds and after every service restart.

## Requirements

- AzuraCast with Liquidsoap's HTTP/telnet bridge enabled
- Liquidsoap 2.4 or newer
- Python 3.11 or newer
- Docker access for the service account, if using automatic container discovery

## Install

1. Add the generated Liquidsoap block after your station's combined `radio`
   source exists and before its encoders:

   ```bash
   python3 generate_liquidsoap.py > equalizercast.liq
   ```

   Copy the contents into AzuraCast's custom Liquidsoap configuration. The
   generated block creates the interactive variables expected by the web app.

2. Store the Liquidsoap API key without a trailing newline:

   ```bash
   sudo install -d -m 750 /etc/equalizercast
   sudo install -m 600 /dev/null /etc/equalizercast/liquidsoap-api-key
   sudoedit /etc/equalizercast/liquidsoap-api-key
   ```

   Paste only the key into the editor. This keeps it out of shell history.

3. Install and adapt the example service:

   ```bash
   sudo cp examples/equalizercast.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now equalizercast
   ```

4. Reverse proxy `http://127.0.0.1:8767` behind your existing authenticated
   admin site. Do not expose the loopback service directly to the public.

## Configuration

`controls.json` defines the installed band curve and safe customization ranges.
The web panel can use 1–32 bands, edit every center frequency and Q, and apply a
preset either to the current layout or to the standard 10-band layout.
`presets.json` contains the built-in preset curves and their research
provenance. The curves were newly authored within the app's conservative ±6 dB
range; the referenced Audacious/Winamp collection and AWA guide were used for
established names and intended tonal profiles, not copied gain data.
Presets may also contain a complete `bands` layout and an optional `output_gain`;
these exact-layout presets restore band count, frequencies, Q, gains, and output
instead of interpolating onto the current layout.

Changing from an earlier EqualizerCast release requires regenerating and
replacing the Liquidsoap block once. The new block creates a 32-slot filter pool
whose active count, frequency, gain, and Q are runtime controls. After that,
layout changes do not require another regeneration or a Liquidsoap restart.

The app accepts these environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LIQUIDSOAP_API_KEY_FILE` | `/etc/equalizercast/liquidsoap-api-key` | Root-readable key file |
| `LIQUIDSOAP_API_KEY` | unset | Direct key; useful for containers, less ideal on a host |
| `LIQUIDSOAP_API_URL` | auto-discovered | Complete `/telnet` endpoint override |
| `AZURACAST_CONTAINER` | `azuracast` | Container used for IP discovery |
| `LIQUIDSOAP_API_PORT` | `8004` | Liquidsoap bridge port |
| `EQUALIZERCAST_STATE_DIR` | `/var/lib/equalizercast` | Persistent settings directory |
| `EQUALIZERCAST_HOST` | `127.0.0.1` | Web bind address |
| `EQUALIZERCAST_PORT` | `8767` | Web port |

## Test

```bash
python3 -m unittest discover -s tests
python3 -m py_compile app.py generate_liquidsoap.py
```
