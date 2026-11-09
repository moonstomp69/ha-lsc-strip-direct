"""Light entity talking directly to the strip through tinytuya."""
from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from . import protocol as p
from .client import StripClient
from .const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_LOCAL_KEY,
    CONF_SCENE_DP,
    CONF_VERSION,
    DEFAULT_SCENE_DP,
    DOMAIN,
)
from .scenes import SCENES

_LOGGER = logging.getLogger(__name__)

EFFECT_COLOUR = "Mode Color"
EFFECT_SCENE = "Mode Scene"
EFFECT_MUSIC = "Musik"
SCENE_BY_DATA = {v: k for k, v in SCENES.items()}

GRACE = 4.0  # seconds after our own command in which device reports are ignored


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    async_add_entities([LscStripDirectLight(entry)])


class LscStripDirectLight(RestoreEntity, LightEntity):
    _attr_should_poll = False
    _attr_supported_color_modes = {ColorMode.HS, ColorMode.COLOR_TEMP}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = [EFFECT_COLOUR, EFFECT_SCENE, *SCENES, EFFECT_MUSIC]
    _attr_min_color_temp_kelvin = p.MIN_KELVIN
    _attr_max_color_temp_kelvin = p.MAX_KELVIN

    def __init__(self, entry: ConfigEntry) -> None:
        d = entry.data
        self._entry = entry
        self._scene_dp = int(entry.options.get(CONF_SCENE_DP, d.get(CONF_SCENE_DP, DEFAULT_SCENE_DP)))
        self._attr_name = None  # entity takes the device name
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, d[CONF_DEVICE_ID])},
            name=entry.title,
            manufacturer="LSC Smart Connect",
            model="Smart LED Strip RGBIC+CCT 5 m",
            configuration_url=None,
        )
        self._attr_unique_id = f"{DOMAIN}_{d[CONF_DEVICE_ID]}"
        self._attr_is_on = False
        self._attr_available = False
        self._attr_color_mode = ColorMode.COLOR_TEMP
        self._attr_brightness = 255
        self._attr_color_temp_kelvin = 4000
        self._attr_hs_color = (0.0, 100.0)
        self._attr_effect = None
        self._dps: dict[str, Any] = {}
        self._last_cmd = 0.0
        self._client: StripClient | None = None

    # ---- lifecycle --------------------------------------------------------
    async def async_added_to_hass(self) -> None:
        if (last := await self.async_get_last_state()) is not None:
            a = last.attributes
            if a.get(ATTR_BRIGHTNESS):
                self._attr_brightness = a[ATTR_BRIGHTNESS]
            if a.get(ATTR_COLOR_TEMP_KELVIN):
                self._attr_color_temp_kelvin = a[ATTR_COLOR_TEMP_KELVIN]
            if a.get(ATTR_HS_COLOR) and a.get("color_mode") == ColorMode.HS:
                self._attr_hs_color = tuple(a[ATTR_HS_COLOR])
        d = self._entry.data
        self._client = StripClient(
            d[CONF_HOST],
            d[CONF_DEVICE_ID],
            d[CONF_LOCAL_KEY],
            d.get(CONF_VERSION, "3.5"),
            on_state=lambda dps: self._post(self._handle_dps, dps),
            on_available=lambda ok: self._post(self._handle_available, ok),
        )
        await self.hass.async_add_executor_job(self._client.start)

        async def _stop(_: Event) -> None:
            await self.hass.async_add_executor_job(self._client.stop)

        self.async_on_remove(
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)
        )

    def _post(self, func, *args) -> None:
        try:
            self.hass.loop.call_soon_threadsafe(func, *args)
        except RuntimeError:
            pass  # event loop already closed (shutdown)

    async def async_will_remove_from_hass(self) -> None:
        if self._client:
            await self.hass.async_add_executor_job(self._client.stop)

    # ---- device -> HA -----------------------------------------------------
    @callback
    def _handle_available(self, ok: bool) -> None:
        self._attr_available = ok
        self.async_write_ha_state()

    @callback
    def _handle_dps(self, dps: dict[str, Any]) -> None:
        first = not self._dps
        changed = set(dps) if first else {k for k, v in dps.items() if self._dps.get(k) != v}
        self._dps = {**self._dps, **dps}
        if not changed:
            return
        if time.monotonic() - self._last_cmd < GRACE and not first:
            return  # our own command is still settling
        if "20" in changed:
            self._attr_is_on = bool(dps["20"])
        mode = self._dps.get("21")
        if first or changed & {"21", "61", "24", str(self._scene_dp)}:
            white = p.decode_white(self._dps["61"]) if isinstance(self._dps.get("61"), str) else None
            colour = p.decode_colour(self._dps["24"]) if isinstance(self._dps.get("24"), str) else None
            self._attr_effect = None
            if mode == "music":
                self._attr_effect = EFFECT_MUSIC
            elif isinstance(mode, str) and mode.startswith("scene"):
                data = self._dps.get(str(self._scene_dp))
                self._attr_effect = SCENE_BY_DATA.get(data, EFFECT_SCENE)
            if self._attr_effect is not None:
                pass
            elif mode == p.MODE_WHITE or (mode != p.MODE_COLOUR and "61" in changed and white):
                self._attr_color_mode = ColorMode.COLOR_TEMP
                if white:
                    self._attr_brightness = p.pct_to_brightness255(white[0])
                    self._attr_color_temp_kelvin = p.temp_pct_to_kelvin(white[1])
            elif mode == p.MODE_COLOUR and colour:
                self._attr_color_mode = ColorMode.HS
                self._attr_hs_color = (float(colour[0]), float(colour[1]))
                self._attr_brightness = p.pct_to_brightness255(max(colour[2], 1))
        self.async_write_ha_state()

    # ---- HA -> device -----------------------------------------------------
    def _send(self, writes: list[tuple[int, Any]]) -> None:
        self._last_cmd = time.monotonic()
        if self._client:
            self._client.send(writes)

    async def async_turn_on(self, **kwargs: Any) -> None:
        effect = kwargs.get(ATTR_EFFECT)
        if effect in SCENES or effect in (EFFECT_SCENE, EFFECT_MUSIC):
            writes: list[tuple[int, Any]] = [(20, True)]
            if effect in SCENES:
                writes += [(self._scene_dp, SCENES[effect]), (21, "scene")]
            elif effect == EFFECT_SCENE:
                writes += [(21, "scene")]
            else:
                writes += [(21, "music")]
            self._attr_effect = effect
            self._send(writes)
            self._attr_is_on = True
            self.async_write_ha_state()
            return
        if effect == EFFECT_COLOUR and ATTR_HS_COLOR not in kwargs:
            kwargs = {**kwargs, ATTR_HS_COLOR: self._attr_hs_color}
        mode = self._attr_color_mode
        if ATTR_HS_COLOR in kwargs:
            hs = tuple(kwargs[ATTR_HS_COLOR])
            if mode == ColorMode.COLOR_TEMP and self._is_derived_white(hs):
                pass  # card sent the colour derived from the white temperature
            else:
                self._attr_hs_color = hs
            mode = ColorMode.HS
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            mode = ColorMode.COLOR_TEMP
            self._attr_color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        self._attr_color_mode = mode
        self._attr_effect = None

        pct = p.brightness255_to_pct(self._attr_brightness)
        writes: list[tuple[int, Any]] = [(20, True)]
        if mode == ColorMode.HS:
            h, s = self._attr_hs_color
            writes += [(24, p.encode_colour(h, s, pct)), (21, p.MODE_COLOUR)]
        else:
            t = p.kelvin_to_temp_pct(self._attr_color_temp_kelvin)
            writes += [(61, p.encode_white(pct, t))]  # DP61 alone switches to white
        self._send(writes)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._send([(20, False)])
        self._attr_is_on = False
        self.async_write_ha_state()

    def _is_derived_white(self, hs) -> bool:
        try:
            from homeassistant.util.color import color_temperature_to_hs

            dh, ds = color_temperature_to_hs(self._attr_color_temp_kelvin)
        except Exception:  # noqa: BLE001
            return False
        return abs(hs[0] - dh) < 2 and abs(hs[1] - ds) < 2
