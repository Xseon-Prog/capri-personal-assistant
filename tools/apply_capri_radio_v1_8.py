#!/usr/bin/env python3
"""Use Capri's existing tray_icon() for the Night City Radio window."""
from __future__ import annotations

import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CURRENT = ROOT / "radio_player.py"
STAGED = ROOT / "radio_player_v1_8.py"


def fail(message: str) -> None:
    print(f"[Capri Radio v1.8] ОШИБКА: {message}")
    raise SystemExit(1)


def main() -> None:
    for path, label in ((MAIN, "main.py"), (CURRENT, "radio_player.py"), (STAGED, "radio_player_v1_8.py")):
        if not path.is_file():
            fail(f"Не найден {label}. Распакуй архив целиком в корень проекта.")

    try:
        main_src = MAIN.read_text(encoding="utf-8-sig")
        current_src = CURRENT.read_text(encoding="utf-8-sig")
        staged_src = STAGED.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        fail(f"Не удалось прочитать исходники как UTF-8: {exc}")

    if "NightCityRadioWindow" not in main_src or "CAPRI_NIGHT_CITY_RADIO_V1_1" not in main_src:
        fail("Интеграция радио не найдена в main.py. Файлы не изменены.")
    if "def tray_icon():" not in main_src:
        fail("Не найдена функция tray_icon() из основного приложения. Файлы не изменены.")

    accepted = (
        "CAPRI_NIGHT_CITY_RADIO_V1_5",
        "CAPRI_NIGHT_CITY_RADIO_V1_6",
        "CAPRI_NIGHT_CITY_RADIO_V1_7",
        "CAPRI_NIGHT_CITY_RADIO_V1_8",
    )
    found = next((marker for marker in accepted if marker in current_src), None)
    if not found:
        fail("radio_player.py не похож на поддерживаемую версию v1.5–v1.8. Файлы не изменены.")

    required = (
        "CAPRI_NIGHT_CITY_RADIO_V1_8",
        "window_icon: Optional[QIcon] = None",
        "if window_icon is not None:",
        "self.setWindowIcon(window_icon)",
    )
    missing = [token for token in required if token not in staged_src]
    if missing:
        fail("Новая версия radio_player.py не прошла проверку: " + ", ".join(missing))

    # The integration installer v1.1 creates this exact constructor argument.
    # Add the existing app icon as a parameter; do not create a second icon.
    import re
    call_pattern = re.compile(
        r'(?m)^(?P<indent>[ \t]*)video_path=os\.path\.join\(BASE, "media", "night_city_radio\.mp4"\),[ \t]*$'
    )
    already_connected = "window_icon=tray_icon()" in main_src
    if not already_connected:
        matches = list(call_pattern.finditer(main_src))
        if len(matches) != 1:
            fail(f"Не удалось однозначно найти аргумент video_path в вызове NightCityRadioWindow (совпадений: {len(matches)}). Файлы не изменены.")
        match = matches[0]
        indent = match.group("indent")
        replacement = match.group(0) + "\n" + indent + 'window_icon=tray_icon(),  # CAPRI_RADIO_REUSE_APP_ICON_V1_8'
        main_src = main_src[:match.start()] + replacement + main_src[match.end():]

    try:
        ast.parse(main_src, filename="main.py")
        ast.parse(staged_src, filename="radio_player.py")
    except SyntaxError as exc:
        fail(f"Синтаксическая проверка не пройдена: {exc}")

    if "window_icon=tray_icon()" not in main_src:
        fail("Не удалось передать существующую иконку Капри окну радио. Файлы не изменены.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "backups" / f"capri_radio_v1_8_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MAIN, backup / "main.py")
    shutil.copy2(CURRENT, backup / "radio_player.py")

    # Remove only the old separately generated radio app icon, if present.
    # Keep previous/next/play/pause button assets in media/radio_icons.
    for folder in (ROOT / "media" / "radio_icons", ROOT / "tools" / "capri_radio_icons"):
        for filename in ("capri_radio.ico", "capri_radio.png"):
            item = folder / filename
            if item.is_file():
                dest = backup / "old_custom_icon" / folder.name
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest / filename)
                item.unlink()
        try:
            folder.rmdir()
        except OSError:
            pass

    for target, content in ((MAIN, main_src), (CURRENT, staged_src)):
        temp = target.with_suffix(target.suffix + ".radio_tmp")
        temp.write_text(content, encoding="utf-8", newline="\n")
        temp.replace(target)

    print("[Capri Radio v1.8] Установка завершена.")
    print("[Capri Radio v1.8] Используется та же tray_icon(), что и у основного приложения Капри.")
    print("[Capri Radio v1.8] Отдельная сгенерированная иконка радио не используется.")
    print(f"[Capri Radio v1.8] Резервная копия: {backup}")
    print("[Capri Radio v1.8] Закрой все окна Капри и запусти run.bat заново.")


if __name__ == "__main__":
    main()
