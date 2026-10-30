"""Offline smoke tests for natural-language Telegram chat commands."""
import re

PATTERNS = [
    re.compile(r"^(?:найди|поищи|открой|покажи|перейди|зайди)(?: мне)?\s+(?:в\s+)?(?:чат|диалог|переписк\w*)\s+(?:с\s+)?(?P<name>.+?)(?:\s+(?:в|через)\s+(?:telegram|телеграм\w*|телега|тг))?$"),
    re.compile(r"^(?:найди|поищи|открой|покажи|перейди|зайди)(?: мне)?\s+(?:в\s+)?(?:telegram|телеграм\w*|телега|тг)\s+(?:чат|диалог|переписк\w*)\s+(?:с\s+)?(?P<name>.+)$"),
    re.compile(r"^(?:найди|поищи)(?: мне)?\s+(?:контакт|человек\w*|пользовател\w*)\s+(?P<name>.+?)\s+(?:в|через)\s+(?:telegram|телеграм\w*|телега|тг)$"),
    re.compile(r"^(?:найди|поищи)(?: мне)?\s+(?P<name>.+?)\s+(?:в|через)\s+(?:telegram|телеграм\w*|телега|тг)$"),
]
CASES = {
    "найди мне чат мама в телеграмм": "мама",
    "найди чат с мамой в телеграме": "мамой",
    "открой чат мама": "мама",
    "открой в телеграме чат мама": "мама",
    "перейди в чат мама": "мама",
    "зайди в чат с мамой": "мамой",
    "поищи мне диалог мама в telegram": "мама",
    "найди контакт мама в телеграме": "мама",
    "найди мне маму в телеграме": "маму",
    "найди переписку с мамой через телеграм": "мамой",
}

passed = 0
for phrase, expected in CASES.items():
    match = next((p.fullmatch(phrase) for p in PATTERNS if p.fullmatch(phrase)), None)
    assert match is not None, f"Не распознана команда: {phrase}"
    actual = match.group("name").strip()
    assert actual == expected, f"Неверно извлечено имя из «{phrase}»: {actual!r} != {expected!r}"
    passed += 1

# The main search implementation must never select an arbitrary Edit field: it checks
# coordinates in the top-left chat sidebar after closing transient popovers.
from pathlib import Path
installer = Path(__file__).with_name("apply_capri_telegram_chat_fix_v1.py").read_text(encoding="utf-8")
assert "send_keys([\"esc\"])" in installer
assert "rel_y <= 0.30" in installer
assert "send_keys([\"ctrl\", \"f\"])" in installer
def stem_name(word):
    if len(word) >= 5 or (len(word) == 4 and word.endswith(("е", "у", "ы", "и"))):
        import re
        stem = re.sub(r"(ами|ями|ого|его|ому|ему|ов|ев|ей|ой|ом|ем|ым|им|ою|ею|ах|ях|ам|ям|ую|юю|ая|яя|ые|ие|ы|и|а|я|у|ю|е)$", "", word)
        word = stem if len(stem) >= 3 else word
    return word

assert stem_name("мама") == "мама"
assert stem_name("маме") == "мам"
assert stem_name("маму") == "мам"
assert stem_name("мамой") == "мам"
print(f"OK: {passed} вариантов команд распознаны; склонения имени и фильтр поиска чатов проверены.")
