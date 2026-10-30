#!/usr/bin/env python3
"""Install deterministic spoken commands for Capri's settings and Night City Radio."""
from __future__ import annotations

import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
PARSER = ROOT / "voice_controls.py"
BRIDGE = ROOT / "voice_control_bridge.py"
STAGED = Path(__file__).resolve().parent.parent
MARKER = "CAPRI_VOICE_SETTINGS_COMMANDS_V1"


def fail(message: str) -> None:
    print(f"[Capri Voice Settings v1] ОШИБКА: {message}")
    print("Файлы проекта не изменены.")
    raise SystemExit(1)


def main() -> None:
    for path, label in ((MAIN, "main.py"),
                        (STAGED / "voice_controls.py", "voice_controls.py в архиве"),
                        (STAGED / "voice_control_bridge.py", "voice_control_bridge.py в архиве")):
        if not path.is_file():
            fail(f"Не найден {label}. Распакуй архив целиком в корень проекта.")

    try:
        main_src = MAIN.read_text(encoding="utf-8-sig")
        parser_src = (STAGED / "voice_controls.py").read_text(encoding="utf-8-sig")
        bridge_src = (STAGED / "voice_control_bridge.py").read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        fail(f"Не удалось прочитать исходники как UTF-8: {exc}")

    if MARKER in main_src:
        if ("voice_control_requested.emit(voice_control)" in main_src
                and PARSER.is_file() and BRIDGE.is_file()):
            print("[Capri Voice Settings v1] Голосовое управление настройками уже установлено.")
            print("Файлы не изменены.")
            return
        fail("Найден неполный след предыдущей установки. Автоматически перезаписывать его небезопасно.")

    # This update targets the locally installed radio integration; it deliberately refuses
    # to patch an unintegrated/original repository checkout.
    required_main = (
        "class Capri(QObject):",
        'report_requested = Signal(str, str)',
        "def open_radio():",
        "radio_window = None",
        "NightCityRadioWindow",
        "def open_entries():",
        "def open_sound():",
        "def open_profile():",
        "def tray_icon():",
        'reply = self.actions.handle(cmd)\n        decision = None',
    )
    missing = [token for token in required_main if token not in main_src]
    if missing:
        fail("Текущий main.py отличается от ожидаемой версии с радио. Не найдены фрагменты: " + ", ".join(missing))

    if "input_devices" not in main_src or "CAPRI_URL" not in main_src or "CONFIG_PATH" not in main_src:
        fail("В main.py не найдены функции/пути для управления микрофоном, GitHub и config.json.")

    signal_anchor = '    report_requested = Signal(str, str)  # CAPRI_CYBERPUNK_UI_V6\n'
    if main_src.count(signal_anchor) != 1:
        fail("Не удалось однозначно добавить сигнал голосового управления рядом с сигналами Capri.")
    main_src = main_src.replace(
        signal_anchor,
        signal_anchor + f'    voice_control_requested = Signal(object)  # {MARKER}\n',
        1,
    )

    process_anchor = '        reply = self.actions.handle(cmd)\n        decision = None\n'
    process_replacement = '''        # CAPRI_VOICE_SETTINGS_COMMANDS_V1: settings and radio controls are local rules, not LLM prompts.
        from voice_controls import parse_voice_control
        voice_control = parse_voice_control(cmd)
        if voice_control is not None:
            self.voice_control_requested.emit(voice_control)
            reply = Reply(voice_control["reply"], "voice_control")
        else:
            reply = self.actions.handle(cmd)
        decision = None
'''
    if main_src.count(process_anchor) != 1:
        fail("Не удалось однозначно найти место перед Actions.handle() в Capri._process().")
    main_src = main_src.replace(process_anchor, process_replacement, 1)

    menu_anchor = "    menu = QMenu()\n"
    if main_src.count(menu_anchor) != 1:
        fail("Не удалось однозначно найти точку подключения обработчика в main().")
    if "capri.voice_control_requested.connect" in main_src:
        fail("Сигнал голосовых настроек уже подключён, но маркер установки отсутствует. Файлы не изменены.")

    bridge_setup = f'''    # {MARKER}: QObject slot ensures UI/settings actions run on the Qt main thread.
    from voice_control_bridge import VoiceControlBridge
    voice_control_bridge = VoiceControlBridge(
        capri=capri,
        avatar=avatar,
        save_setting=save_setting,
        open_radio=open_radio,
        get_radio=lambda: radio_window,
        open_entries=open_entries,
        open_sound=open_sound,
        open_profile=open_profile,
        open_config=lambda: os.startfile(CONFIG_PATH),
        open_github=lambda: capri.actions.web(CAPRI_URL),
        mic_devices=input_devices,
    )
    capri.voice_control_requested.connect(voice_control_bridge.execute)

'''
    main_src = main_src.replace(menu_anchor, bridge_setup + menu_anchor, 1)

    # Validate source and staged modules before touching any user file.
    for name, source in (("main.py", main_src),
                         ("voice_controls.py", parser_src),
                         ("voice_control_bridge.py", bridge_src)):
        try:
            ast.parse(source, filename=name)
        except SyntaxError as exc:
            fail(f"Синтаксическая проверка {name} не пройдена: {exc}")

    # Write into temporary files first so an interrupted write cannot leave a partial source file.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "backups" / f"capri_voice_settings_v1_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MAIN, backup / "main.py")
    if PARSER.exists():
        shutil.copy2(PARSER, backup / "voice_controls.py")
    if BRIDGE.exists():
        shutil.copy2(BRIDGE, backup / "voice_control_bridge.py")

    staged_files = {
        MAIN: main_src,
        PARSER: parser_src,
        BRIDGE: bridge_src,
    }
    temps: list[tuple[Path, Path]] = []
    try:
        for target, content in staged_files.items():
            temp = target.with_suffix(target.suffix + ".voice_tmp")
            temp.write_text(content, encoding="utf-8", newline="\n")
            temps.append((temp, target))
        for temp, target in temps:
            temp.replace(target)
    except Exception as exc:
        for temp, _ in temps:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        # Restore main.py if the atomic replacements had started.
        shutil.copy2(backup / "main.py", MAIN)
        fail(f"Не удалось записать обновление: {exc}")

    print("[Capri Voice Settings v1] Установка завершена.")
    print("[Capri Voice Settings v1] Настройки и Радио Найт-Сити управляются локально, без обращения к ИИ.")
    print("[Capri Voice Settings v1] Подключены: ожидание, таймер, HUD, закрепление, поиск, появления, громкость, размер, микрофон, радио, config и GitHub.")
    print(f"[Capri Voice Settings v1] Резервная копия: {backup}")
    print("[Capri Voice Settings v1] Полностью закрой Капри и перезапусти run.bat.")


if __name__ == "__main__":
    main()
