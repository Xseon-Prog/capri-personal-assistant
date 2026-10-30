"""CAPRI_VOICE_SETTINGS_COMMANDS_V1
Локальный разбор голосовых команд для настроек Капри и Радио Найт-Сити.
Не использует LLM, сеть или сторонние библиотеки.
"""
from __future__ import annotations

import re
from typing import Any

MARKER = "CAPRI_VOICE_SETTINGS_COMMANDS_V1"

_NUMBERS = {
    "ноль": 0, "нуль": 0,
    "один": 1, "одна": 1, "одно": 1, "одну": 1,
    "два": 2, "две": 2, "двух": 2,
    "три": 3, "трех": 3, "трёх": 3,
    "четыре": 4, "четырех": 4, "четырёх": 4,
    "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9,
    "десять": 10, "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13,
    "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16,
    "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19,
    "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
    "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80,
    "девяносто": 90, "сто": 100,
}


def _norm(text: str) -> str:
    value = (text or "").lower().replace("ё", "е").replace("—", " ").replace("-", " ")
    value = re.sub(r"[«»\"'`.,!?;:%()]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"^(?:эй\s+)?капри\s*[, ]*", "", value)
    value = re.sub(r"^(?:пожалуйста|ну|слушай)\s+", "", value)
    return value.strip()


def _number_after(text: str) -> int | None:
    """Read the first integer or common Russian spoken number (including 20 + 5)."""
    m = re.search(r"(?<!\d)(\d{1,3})(?!\d)", text)
    if m:
        return int(m.group(1))
    words = text.split()
    for i, word in enumerate(words):
        if word in _NUMBERS:
            value = _NUMBERS[word]
            if value >= 20 and i + 1 < len(words) and words[i + 1] in _NUMBERS:
                tail = _NUMBERS[words[i + 1]]
                if 1 <= tail <= 9:
                    value += tail
            return value
    if re.search(r"\bполминут\w*\b", text):
        return 30
    if re.search(r"\bполовин\w*\b", text):
        return 50
    if re.search(r"\bминут\w*\b", text):
        return 1
    if re.search(r"\bмаксимум\b|\bна полную\b|\bполную громкость\b", text):
        return 100
    if re.search(r"\bминимум\b|\bв ноль\b", text):
        return 0
    return None


def _intent(action: str, value: Any = None, reply: str = "Выполняю.") -> dict[str, Any]:
    return {"action": action, "value": value, "reply": reply}


def _is_down(text: str) -> bool:
    return bool(re.search(r"\b(сниз\w*|убав\w*|уменьш\w*|приглуш\w*|потише|тише|меньше|пониз\w*|убери)\b", text))


def _is_up(text: str) -> bool:
    return bool(re.search(r"\b(увелич\w*|прибав\w*|добав\w*|громче|погромче|больше|подним\w*|повыш\w*)\b", text))


def _volume_intent(text: str, target: str) -> dict[str, Any] | None:
    """target is radio or voice. A directional phrase means a relative change; otherwise set absolute."""
    if not re.search(r"громкост\w*|громче|тише|приглуш\w*|потише|погромче", text):
        return None
    amount = _number_after(text)
    if _is_down(text) and not re.search(r"\bдо\s+\d", text):
        delta = -(amount if amount is not None else 10)
        reply = "Снижаю громкость радио." if target == "radio" else "Снижаю громкость своего голоса."
        return _intent(f"{target}_volume", {"mode": "delta", "amount": delta}, reply)
    if _is_up(text) and not re.search(r"\bдо\s+\d", text):
        delta = amount if amount is not None else 10
        reply = "Повышаю громкость радио." if target == "radio" else "Повышаю громкость своего голоса."
        return _intent(f"{target}_volume", {"mode": "delta", "amount": delta}, reply)
    if amount is not None:
        reply = "Устанавливаю громкость радио." if target == "radio" else "Устанавливаю громкость своего голоса."
        return _intent(f"{target}_volume", {"mode": "set", "amount": amount}, reply)
    return None


def parse_voice_control(text: str) -> dict[str, Any] | None:
    """Return a deterministic GUI action or None when the utterance is not a settings command."""
    c = _norm(text)
    if not c:
        return None

    # Radio-specific commands must run before generic volume/settings commands.
    has_radio = bool(re.search(r"\bрадио\b|\bнайт\s+сити\b|\bnight\s+city\b", c))
    if has_radio:
        volume = _volume_intent(c, "radio")
        if volume:
            return volume
        if re.search(r"\b(следующ\w*|дальше|переключ\w*|пропуст\w*|скип\w*)\b", c) and re.search(r"трек|песн|композиц|радио|найт", c):
            return _intent("radio_next", reply="Переключаю на следующую композицию.")
        if re.search(r"\b(предыдущ\w*|прошл\w*|верни предыдущ\w*)\b", c):
            return _intent("radio_previous", reply="Возвращаю предыдущую композицию.")
        if re.search(r"\b(пауза|паузу|приостанов\w*|поставь на паузу)\b", c):
            return _intent("radio_pause", reply="Ставлю радио на паузу.")
        if re.search(r"\b(продолж\w*|возобнов\w*|сними с паузы|играй дальше)\b", c):
            return _intent("radio_resume", reply="Продолжаю воспроизведение.")
        if re.search(r"\b(закрой|закрывай|выключи|выключай|отключи|отключай)\b", c):
            return _intent("radio_close", reply="Останавливаю радио и закрываю окно.")
        if re.search(r"\b(стоп|останов\w*|прекрат\w*)\b", c):
            return _intent("radio_stop", reply="Останавливаю воспроизведение радио.")
        if re.search(r"\b(включи|запусти|открой|начни|запускай|давай послушаем)\b", c) or c in ("радио", "найт сити"):
            return _intent("radio_start", reply="Включаю Радио Найт-Сити.")

    # Automatic standby delay, distinct from the persistent manual standby toggle.
    if re.search(r"ожидан\w*|standby", c) and ("автоматическ" in c or "таймер" in c or "никогда" in c or "навсегда" in c or re.search(r"\d|секунд|сек\b|минут|минуту|полминут|двадцать|тридцать|сорок|пятьдесят|шестьдесят|одну", c)):
        if re.search(r"\bникогда\b|\bнавсегда\b|\bне включай\b|\bотключи таймер\b|\bотключ\w*\b|\bвыключ\w*\b", c):
            return _intent("standby_after", 0, "Автоматический режим ожидания отключён.")
        amount = _number_after(c)
        if amount is not None:
            seconds = 30 if re.search(r"\bполминут\w*\b", c) else (amount * 60 if re.search(r"минут", c) or re.search(r"\bодну\b", c) else amount)
            nearest = min((20, 40, 60, 0), key=lambda x: abs(x - seconds))
            return _intent("standby_after", nearest, f"Автоматическое ожидание будет включаться через {nearest} секунд." if nearest else "Автоматическое ожидание отключено.")
        if re.search(r"автоматическ", c) and re.search(r"\b(включ\w*|активир\w*|запусти)\b", c):
            return _intent("standby_after_enable", reply="Включаю автоматический режим ожидания.")

    # Persistent/manual standby on/off.
    if re.search(r"режим ожидан\w*|режим standby|анимаци\w* ожидан|выйди из ожидан\w*|выключи ожидан\w*", c):
        if re.search(r"\bне выключай\b|\bоставь включенн\w*\b", c):
            return _intent("manual_standby", True, "Оставляю постоянный режим ожидания включённым.")
        if re.search(r"\b(не включай|выключ\w*|отключ\w*|отмени\w*|сними\w*|выйди|перестань)\b", c):
            return _intent("manual_standby", False, "Выключаю постоянный режим ожидания.")
        if re.search(r"\b(включ\w*|активир\w*|запусти|перейди|оставайся)\b", c):
            return _intent("manual_standby", True, "Включаю постоянный режим ожидания.")

    # Pin avatar on desktop.
    if re.search(r"рабоч\w* стол|поверх окон|поверх всех окон|закреп\w* капри", c):
        if re.search(r"\b(не оставайся|не оставаться|не закрепляй|откреп\w*|сними закрепление|перестань оставаться|убери|сними|выключ\w*|отключ\w*)\b", c):
            return _intent("pin_desktop", False, "Больше не закрепляюсь на рабочем столе.")
        if re.search(r"\b(оставайся|оставаться|закреп\w*|включ\w*|закреплена|держись)\b", c):
            return _intent("pin_desktop", True, "Остаюсь на рабочем столе.")

    # Message HUD visibility.
    if re.search(r"сообщен\w*|панел\w* сообщений|окно сообщений|текст\w* под аватар", c):
        if re.search(r"\b(не показывай|скрой|скрывай|выключ\w*|отключ\w*|убери)\b", c):
            return _intent("message_hud", False, "Панель сообщений выключена.")
        if re.search(r"\b(показывай|покажи|включ\w*|отображай)\b", c):
            return _intent("message_hud", True, "Панель сообщений включена.")

    # Search fallback toggle.
    if re.search(r"поиск\w* в браузер\w*|искать в браузер\w*|ищи в браузер\w*|поиск\w* в интернет\w*|если не знаю", c):
        if re.search(r"\b(не ищи|не искать|не надо искать|выключ\w*|отключ\w*)\b", c):
            return _intent("search_when_unsure", False, "Поиск в браузере при неизвестном ответе выключен.")
        if re.search(r"\b(ищи|искать|включ\w*|разреш\w*)\b", c):
            return _intent("search_when_unsure", True, "Если я не знаю ответа, буду искать в браузере.")

    # Autonomous appearances / chatter.
    if re.search(r"появля\w* сама|самостоятельн\w* появлен\w*|сама появля\w*|болтать сама", c):
        if re.search(r"\b(не появляйся|не надо|выключ\w*|отключ\w*|перестань)\b", c):
            return _intent("chatter", False, "Самостоятельные появления выключены.")
        return _intent("chatter", True, "Самостоятельные появления включены.")

    # Radio volume is handled above. Generic volume refers to Capri's synthesized voice.
    voice_volume = _volume_intent(c, "voice")
    if voice_volume and "микрофон" not in c and ("капри" in c or "голос" in c or "мою громкость" in c):
        return voice_volume

    # Avatar size: explicit percentage/value or a one-step size change.
    if re.search(r"размер\w* капри|сделай капри (меньше|больше)|уменьш\w* капри|увелич\w* капри|масштаб капри", c):
        amount = _number_after(c)
        if _is_down(c):
            if amount is not None:
                return _intent("avatar_scale", {"mode": "delta", "amount": -amount / 100.0}, "Уменьшаю размер Капри.")
            return _intent("avatar_scale", {"mode": "step", "direction": -1}, "Уменьшаю размер Капри.")
        if _is_up(c):
            if amount is not None:
                return _intent("avatar_scale", {"mode": "delta", "amount": amount / 100.0}, "Увеличиваю размер Капри.")
            return _intent("avatar_scale", {"mode": "step", "direction": 1}, "Увеличиваю размер Капри.")
        if amount is not None:
            value = amount / 100.0 if amount > 1 else float(amount)
            return _intent("avatar_scale", {"mode": "set", "amount": value}, f"Устанавливаю размер Капри {round(value * 100)} процентов.")

    # Voice effects in the sound dialog.
    if re.search(r"эффект\w* голос\w*|глитч\w* голос\w*", c):
        if re.search(r"\b(выключ\w*|отключ\w*|убери|сними)\b", c) or re.search(r"чист\w* голос", c):
            return _intent("voice_fx", 0.0, "Отключаю эффекты голоса.")
        if re.search(r"\b(включ\w*|верни|добавь)\b", c) and _number_after(c) is None:
            return _intent("voice_fx", 1.8, "Возвращаю стандартные эффекты голоса.")
        amount = _number_after(c)
        if amount is not None:
            fx = max(0.0, min(2.5, amount / 100.0 if amount > 2.5 else float(amount)))
            return _intent("voice_fx", fx, f"Устанавливаю эффекты голоса на {fx:.1f}.")

    # Microphone settings: sensitivity (0-100) and input gain (0.5x-4.0x).
    if re.search(r"настройк\w* микрофон\w*|чувствительн\w* микрофон\w*|гейн микрофон\w*|усил\w* микрофон\w*|громкост\w* микрофон\w*", c):
        if re.search(r"открой|покажи|настройк", c) and not re.search(r"на\s+\d|на\s+(?:десять|двадцать|тридцать|сорок|пятьдесят|шестьдесят|семьдесят|восемьдесят|девяносто)", c):
            return _intent("open_sound", reply="Открываю настройки микрофона.")
        amount = _number_after(c)
        if amount is not None:
            if "чувствительност" in c:
                if _is_down(c) or _is_up(c):
                    delta = -amount if _is_down(c) else amount
                    return _intent("mic_sensitivity", {"mode": "delta", "amount": delta}, "Меняю чувствительность микрофона.")
                return _intent("mic_sensitivity", {"mode": "set", "amount": amount}, "Меняю чувствительность микрофона.")
            if "гейн" in c or "усил" in c or "громкост" in c:
                if _is_down(c) or _is_up(c):
                    delta = -amount if _is_down(c) else amount
                    return _intent("mic_gain", {"mode": "delta", "amount": delta}, "Меняю усиление микрофона.")
                gain = amount / 100.0 if amount > 4 else float(amount)
                return _intent("mic_gain", {"mode": "set", "amount": gain}, "Меняю усиление микрофона.")

    if re.search(r"\bмикрофон\b|\bустройство ввода\b", c):
        if re.search(r"\b(следующ\w*|друг\w*|смен\w*|переключ\w*)\b", c):
            return _intent("mic_next", reply="Переключаю микрофон.")
        m = re.search(r"(?:выбер\w*|установ\w*|используй|поставь)\s+(?:микрофон\s+)?(.+)$", c)
        if m:
            name = m.group(1).strip()
            if name in ("", "микрофон", "устройство ввода"):
                return _intent("mic_next", reply="Переключаю микрофон.")
            if name and name not in ("по умолчанию", "стандартный", "windows"):
                return _intent("mic_select", name, f"Выбираю микрофон {name}.")
            return _intent("mic_select", None, "Использую микрофон Windows по умолчанию.")

    # Other settings/dialogs from the context menu.
    if re.search(r"мои сайты|свои сайты|программ\w* и ответ\w*|настройк\w* сайтов|ответ\w* на фраз", c):
        return _intent("open_entries", reply="Открываю сайты, программы и пользовательские ответы.")
    if re.search(r"открой конфиг|открой config|открой настройки в файле|покажи config", c):
        return _intent("open_config", reply="Открываю config.json.")
    if re.search(r"гитхаб|github|репозитори\w* капри|страниц\w* капри", c):
        if re.search(r"открой|покажи|перейди|зайди|где", c):
            return _intent("open_github", reply="Открываю GitHub Капри.")
    if re.search(r"открой настройки звука|настройки голоса|настройки микрофона", c):
        return _intent("open_sound", reply="Открываю настройки звука.")
    if re.search(r"как ко мне обраща\w*|настрой обращен\w*|поменяй обращен\w*", c):
        return _intent("open_profile", reply="Открываю настройки обращения.")

    # Help for the voice settings layer.
    if re.search(r"какие настройки ты можешь менять|что можно настроить голосом|команды настроек|помощь по настройкам", c):
        return _intent("voice_settings_help", reply=(
            "Голосом я могу включать и выключать радио и режим ожидания, менять громкость радио и голоса, "
            "размер Капри, время автоматического ожидания, закрепление на рабочем столе, показ сообщений, "
            "поиск в браузере, самостоятельные появления и настройки микрофона."
        ))

    return None


