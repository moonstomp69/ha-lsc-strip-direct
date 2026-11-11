# LSC Strip (direct) – Home Assistant

Home Assistant custom integration that controls **LSC Smart LED strips (RGBIC+CCT, 5 m, Tuya `h4xcs3aemqldhnr9`)** *directly* over the local network, using [tinytuya](https://github.com/jasonacox/tinytuya). No cloud and no LocalTuya needed.

Made for strips whose white light is controlled via **DP 61** (`paint_colour_data`) instead of the usual DP 22/23 – on those, switching between white and colour fails with the standard integrations.

> Deutsche Anleitung weiter unten.

## Features
- One light entity per strip (and a device): on/off, brightness, colour (HS), white colour temperature (2700–6500 K)
- Smooth switch from colour to white (no flicker)
- Effects: *Mode Color, Mode Scene, Music*, the 19 preset scenes (Night, Read, Meeting, Rainbow, Christmas, …) plus **your own scenes** learned from the Tuya app (see below)
- Changes made in the Tuya app show up instantly (push updates over one persistent local connection)
- Config flow with connection test

## Requirements
- Home Assistant 2025.1 or newer
- Per strip: **IP address** (give it a fixed IP/DHCP reservation), **device ID** and **local key**
- A strip accepts **only one local connection** – remove it from LocalTuya (or any other local integration) first.

You can get device ID and local key from the [Tuya IoT platform](https://iot.tuya.com) or e.g. with `tinytuya wizard`. **Never post your local key publicly.**

## Installation
### HACS (custom repository)
HACS → ⋮ → *Custom repositories* → add this repository, category *Integration* → install → restart Home Assistant.

### Manual
Copy `custom_components/lsc_strip_direct` to `/config/custom_components/` and restart.

## Setup
Settings → Devices & services → *Add integration* → **LSC Strip (direct, tinytuya)**. Enter name, IP, device ID, local key, protocol version (default `3.5`). Repeat for each strip.

## Scenes
The preset scenes are written to DP 25 together with the mode in one packet. App scenes live in DP 51 (`dreamlight_scene_mode`, raw/base64) and cannot be generated, so the integration can *learn* them:
1. Pick a scene in the Tuya app.
2. In Home Assistant → Developer tools → Actions call `lsc_strip_direct.save_scene` for the light with a `name`.
3. The name appears in the light's effect list. Remove it with `lsc_strip_direct.delete_scene`.

Scenes are stored per strip (`.storage/lsc_strip_direct.scenes.<device id>`).

## How the white mode works
Datapoint 61 holds 7 bytes, base64 encoded: `00 00 00 14 00 BB TT` – `BB` = brightness 1–100, `TT` = colour temperature 0 (warm) – 100 (cold). Writing it also switches the strip to white mode. Colour uses DP 24 (`HHHHSSSSVVVV`, hue 0–360, saturation/value 0–1000) plus DP 21 = `colour`.

## Limitations
- Only tested with the LSC strips mentioned above. Other Tuya lights may work for colour/scenes, but their white mode will not.
- Scenes must be saved once from the Tuya app (see above); they are not shared between strips.

## Credits
Preset scene data (`scenes.py`) taken from the LocalTuya light platform – fork [xZetsubou/hass-localtuya](https://github.com/xZetsubou/hass-localtuya), based on [rospogrigio/localtuya](https://github.com/rospogrigio/localtuya) (GPL-3.0). Protocol library: [tinytuya](https://github.com/jasonacox/tinytuya). Not affiliated with Tuya or LSC.

---

# Deutsch

Direkte lokale Steuerung der **LSC Smart LED-Strips RGBIC+CCT 5 m** in Home Assistant, ohne Cloud und ohne LocalTuya. Gedacht für Strips, bei denen Weiß über **DP 61** läuft und der Wechsel zwischen Weiß und Farbe mit den Standard-Integrationen nicht klappt.

**Einrichten:** Ordner `custom_components/lsc_strip_direct` nach `/config/custom_components/` kopieren (oder über HACS als benutzerdefiniertes Repository), Home Assistant neu starten, dann *Integration hinzufügen → LSC Strip (direkt)*. Pro Strip: Name, IP-Adresse, Geräte-ID, Zugangscode (`local_key`), Protokollversion (`3.5`).

**Wichtig:** Ein Strip erlaubt nur eine lokale Verbindung. Vorher aus LocalTuya entfernen. Den `local_key` niemals öffentlich posten.

## License
GPL-3.0 – see [LICENSE](LICENSE).
