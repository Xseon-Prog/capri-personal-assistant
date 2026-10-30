"""Quick self-test for Capri's deterministic voice settings parser."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voice_controls import parse_voice_control

CASES = {
    "Капри, включи радио Найт-Сити": ("radio_start", None),
    "Капри, снизь громкость радио на 30": ("radio_volume", {"mode": "delta", "amount": -30}),
    "Капри, установи громкость радио на 30": ("radio_volume", {"mode": "set", "amount": 30}),
    "Капри, выключи режим ожидания": ("manual_standby", False),
    "Капри, включи режим ожидания": ("manual_standby", True),
    "Капри, поставь режим ожидания через 40 секунд": ("standby_after", 40),
    "Капри, включи автоматический режим ожидания": ("standby_after_enable", None),
    "Капри, отключи автоматическое ожидание навсегда": ("standby_after", 0),
    "Капри, не оставайся на рабочем столе": ("pin_desktop", False),
    "Капри, оставайся на рабочем столе": ("pin_desktop", True),
    "Капри, не показывай сообщения": ("message_hud", False),
    "Капри, включи поиск в браузере если не знаешь": ("search_when_unsure", True),
    "Капри, выключи самостоятельные появления": ("chatter", False),
    "Капри, снизь громкость голоса на 20": ("voice_volume", {"mode": "delta", "amount": -20}),
    "Капри, снизь громкость Капри на 30": ("voice_volume", {"mode": "delta", "amount": -30}),
    "Капри, сделай Капри меньше": ("avatar_scale", {"mode": "step", "direction": -1}),
    "Капри, открой мои сайты программы и ответы": ("open_entries", None),
    "Капри, открой конфиг": ("open_config", None),
    "Капри, поставь радио на паузу": ("radio_pause", None),
    "Капри, следующую композицию радио": ("radio_next", None),
    "Капри, закрой радио": ("radio_close", None),
    "Капри, снизь громкость на 30": None,
    "Капри, переключи микрофон": ("mic_next", None),
    "Капри, установи чувствительность микрофона на 60": ("mic_sensitivity", {"mode": "set", "amount": 60}),
    "Капри, поставь громкость микрофона на 150": ("mic_gain", {"mode": "set", "amount": 1.5}),
    "Капри, отключи эффекты голоса": ("voice_fx", 0.0),
    "Капри, открой настройки микрофона": ("open_sound", None),
    "Капри, открой гитхаб капри": ("open_github", None),
    "Капри, открой профиль, как ко мне обращаться": ("open_profile", None),
}


def main() -> None:
    failures = []
    for utterance, expected in CASES.items():
        result = parse_voice_control(utterance)
        actual = None if result is None else (result["action"], result.get("value"))
        if expected is None:
            if actual is not None:
                failures.append((utterance, expected, actual))
            continue
        if actual != expected:
            failures.append((utterance, expected, actual))
    if failures:
        for utterance, expected, actual in failures:
            print(f"FAIL: {utterance!r}\n  expected: {expected!r}\n  actual:   {actual!r}")
        raise SystemExit(1)
    print(f"OK: {len(CASES)} голосовых команд распознаны корректно.")


if __name__ == "__main__":
    main()
