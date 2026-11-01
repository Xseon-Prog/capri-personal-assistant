"""CAPRI_VOICE_SETTINGS_COMMANDS_V1 GUI-thread executor."""
from __future__ import annotations

from typing import Any
import time

from PySide6.QtCore import QObject, Slot


class VoiceControlBridge(QObject):
    """Executes parsed controls in the Qt GUI thread; safe for commands from Capri's worker thread."""

    def __init__(self, capri, avatar, save_setting, open_radio, get_radio,
                 open_entries, open_sound, open_profile, open_config, open_github, mic_devices):
        super().__init__()
        self.capri = capri
        self.avatar = avatar
        self.save_setting = save_setting
        self.open_radio = open_radio
        self.get_radio = get_radio
        self.open_entries = open_entries
        self.open_sound = open_sound
        self.open_profile = open_profile
        self.open_config = open_config
        self.open_github = open_github
        self.mic_devices = mic_devices

    @Slot(object)
    def execute(self, intent: dict[str, Any]) -> None:
        try:
            action = intent.get("action")
            value = intent.get("value")
            if action == "radio_start":
                self.open_radio()
                radio = self.get_radio()
                if radio is not None and radio.audio_player.playbackState().name != "PlayingState":
                    radio.toggle_play_pause()
            elif action == "radio_close":
                radio = self.get_radio()
                if radio is not None:
                    radio.close()  # closeEvent stops audio and video
            elif action == "radio_stop":
                radio = self.get_radio()
                if radio is not None:
                    radio.stop_radio()
            elif action == "radio_pause":
                radio = self.get_radio()
                if radio is not None and radio.audio_player.playbackState().name == "PlayingState":
                    radio.toggle_play_pause()
            elif action == "radio_resume":
                radio = self.get_radio()
                if radio is None:
                    self.open_radio()
                    radio = self.get_radio()
                if radio is not None and radio.audio_player.playbackState().name != "PlayingState":
                    radio.toggle_play_pause()
            elif action in ("radio_next", "radio_previous"):
                radio = self.get_radio()
                if radio is None or not radio.isVisible():
                    self.open_radio()
                    radio = self.get_radio()
                if radio is not None:
                    (radio.next_track if action == "radio_next" else radio.previous_track)()
            elif action == "radio_volume":
                radio = self.get_radio()
                current = int(radio.volume_slider.value()) if radio is not None else int(self.capri.cfg.get("radio_volume", 70))
                if value.get("mode") == "delta":
                    target = current + int(value.get("amount", 0))
                else:
                    target = int(value.get("amount", current))
                target = max(0, min(100, target))
                if radio is not None:
                    radio._set_volume(target, notify=True)
                else:
                    self.capri.cfg["radio_volume"] = target
                    self.save_setting("radio_volume", target)
            elif action == "manual_standby":
                enabled = bool(value)
                self.capri.cfg["manual_standby_enabled"] = enabled
                self.save_setting("manual_standby_enabled", enabled)
                self.avatar.set_manual_standby(enabled)
            elif action == "standby_after":
                seconds = int(value)
                self.capri.cfg["standby_after_seconds"] = seconds
                self.save_setting("standby_after_seconds", seconds)
                self.avatar.set_standby_after(seconds)
            elif action == "standby_after_enable":
                seconds = int(self.capri.cfg.get("standby_after_seconds", 20))
                if seconds <= 0:
                    seconds = 20
                self.capri.cfg["standby_after_seconds"] = seconds
                self.save_setting("standby_after_seconds", seconds)
                self.avatar.set_standby_after(seconds)
            elif action == "pin_desktop":
                enabled = bool(value)
                self.capri.cfg["pin_on_desktop"] = enabled
                self.save_setting("pin_on_desktop", enabled)
                self.avatar.stay_visible = enabled
                if enabled:
                    self.avatar.hide_at = 0
                    self.avatar.summon()
                elif self.avatar.state == "visible" and self.avatar.mode == "idle":
                    self.avatar.hide_at = time.time() + self.avatar.hide_after
            elif action == "message_hud":
                enabled = bool(value)
                self.capri.cfg["show_message_hud"] = enabled
                self.save_setting("show_message_hud", enabled)
                self.avatar.show_message_hud = enabled
                if not enabled:
                    self.avatar.message_hud_until = 0.0
                elif self.avatar.subtitle:
                    self.avatar.message_hud_until = time.time() + max(8.0, self.avatar.subtitle_duration)
                self.avatar.render()
                self.avatar.update()
            elif action == "search_when_unsure":
                self.capri.set_search_when_unsure(bool(value))
            elif action == "chatter":
                self.capri.set_chatter(bool(value))
            elif action == "voice_volume":
                current = int(self.capri.cfg.get("voice_volume", 100))
                if value.get("mode") == "delta":
                    target = current + int(value.get("amount", 0))
                else:
                    target = int(value.get("amount", current))
                self.capri.set_voice_volume(max(0, min(100, target)))
            elif action == "avatar_scale":
                current = float(self.capri.cfg.get("avatar_scale", 1.0))
                mode = value.get("mode")
                if mode == "delta":
                    target = current + float(value.get("amount", 0))
                elif mode == "step":
                    options = (0.55, 0.70, 0.85, 1.0)
                    if value.get("direction", 0) < 0:
                        target = max((x for x in options if x < current - 0.001), default=options[0])
                    else:
                        target = min((x for x in options if x > current + 0.001), default=options[-1])
                else:
                    target = float(value.get("amount", current))
                target = max(0.50, min(1.0, target))
                self.avatar.set_scale(target)
                self.capri.cfg["avatar_scale"] = target
                self.save_setting("avatar_scale", target)
            elif action == "mic_next":
                self.capri.mic_command("mic_next")
            elif action == "mic_select":
                requested = (value or "").strip().lower().replace("ё", "е")
                if not requested:
                    self.capri.set_mic(None)
                else:
                    devices = self.mic_devices()
                    match = next((name for name, _ in devices if requested in name.lower().replace("ё", "е")), None)
                    if match is None:
                        match = next((name for name, _ in devices if name.lower().replace("ё", "е") in requested), None)
                    if match is None:
                        self.capri.subtitle.emit("Не нашла микрофон с таким названием. Скажи «следующий микрофон» или открой настройки звука.")
                    else:
                        self.capri.set_mic(match)
            elif action == "mic_sensitivity":
                current = int(self.capri.cfg.get("mic_sensitivity", 100))
                if isinstance(value, dict):
                    target = current + int(value.get("amount", 0)) if value.get("mode") == "delta" else int(value.get("amount", current))
                else:
                    target = int(value)
                self.capri.set_mic_tuning(sensitivity=max(0, min(100, target)))
            elif action == "mic_gain":
                current = float(self.capri.cfg.get("mic_gain", 1.0))
                if isinstance(value, dict):
                    current_percent = round(current * 100)
                    target_percent = current_percent + int(value.get("amount", 0)) if value.get("mode") == "delta" else round(float(value.get("amount", current)) * 100)
                    target = target_percent / 100.0
                else:
                    target = float(value)
                self.capri.set_mic_tuning(gain=max(0.5, min(4.0, target)))
            elif action == "voice_fx":
                self.capri.set_voice_fx(float(value))
            elif action == "open_entries":
                self.open_entries()
            elif action == "open_sound":
                self.open_sound()
            elif action == "open_profile":
                self.open_profile()
            elif action == "open_config":
                self.open_config()
            elif action == "open_github":
                self.open_github()
            elif action == "voice_settings_help":
                pass  # reply is spoken by Capri's worker
            else:
                return
        except Exception:
            import logging
            logging.getLogger("capri").exception("Ошибка выполнения голосовой настройки: %s", action)
