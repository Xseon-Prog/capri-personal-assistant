#!/usr/bin/env python3
"""CAPRI taskbar identity fix: use Capri's existing icon, not pythonw.exe's icon."""
from __future__ import annotations

import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
MARKER = "CAPRI_WINDOWS_TASKBAR_ID_V1_9"
APP_ID = "XseonProg.Capri.PersonalAssistant"


def fail(message: str) -> None:
    print(f"[Capri Taskbar v1.9] ОШИБКА: {message}")
    raise SystemExit(1)


def main() -> None:
    if not MAIN.is_file():
        fail("Не найден main.py. Распакуй архив в корень проекта.")
    try:
        source = MAIN.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        fail(f"Не удалось прочитать main.py как UTF-8: {exc}")

    if "def tray_icon():" not in source:
        fail("Не найдена существующая функция tray_icon() в main.py. Файлы не изменены.")
    if "window_icon=tray_icon()" not in source:
        fail("Радио ещё не использует существующую иконку Капри (window_icon=tray_icon()). Сначала проверь установку Radio v1.8.")
    if MARKER in source:
        print("[Capri Taskbar v1.9] Исправление уже установлено. Файлы не изменены.")
        return

    expected = "def main():\n    app = QApplication(sys.argv)\n"
    if source.count(expected) != 1:
        fail("Не удалось однозначно найти начало main(). Файлы не изменены.")

    helper = f'''def _set_windows_app_user_model_id():
    """Задаёт отдельную идентичность Капри для группировки значка на панели задач Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        set_app_id = shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [ctypes.c_wchar_p]
        set_app_id.restype = ctypes.c_long
        result = set_app_id("{APP_ID}")
        if result != 0:
            log.warning("SetCurrentProcessExplicitAppUserModelID завершилась с HRESULT 0x%08X", result & 0xFFFFFFFF)
    except Exception:
        log.exception("Не удалось задать Windows AppUserModelID для Капри")


'''
    source = source.replace("def main():\n", helper + "def main():\n", 1)
    startup_old = "def main():\n    app = QApplication(sys.argv)\n"
    startup_new = (
        "def main():\n"
        f"    _set_windows_app_user_model_id()  # {MARKER}: before QApplication\n"
        "    app = QApplication(sys.argv)\n"
        "    app.setApplicationName(\"Capri\")\n"
        "    app.setApplicationDisplayName(\"Capri\")\n"
        "    app.setWindowIcon(tray_icon())  # same icon as Capri's system tray\n"
    )
    if source.count(startup_old) != 1:
        fail("Не удалось безопасно обновить запуск QApplication. Файлы не изменены.")
    source = source.replace(startup_old, startup_new, 1)

    try:
        ast.parse(source, filename="main.py")
    except SyntaxError as exc:
        fail(f"Синтаксическая проверка не пройдена: {exc}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "backups" / f"capri_taskbar_icon_v1_9_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MAIN, backup / "main.py")

    temp = MAIN.with_suffix(".py.taskbar_tmp")
    temp.write_text(source, encoding="utf-8", newline="\n")
    temp.replace(MAIN)

    print("[Capri Taskbar v1.9] Установка завершена.")
    print("[Capri Taskbar v1.9] Windows теперь получает отдельный AppUserModelID для Капри.")
    print("[Capri Taskbar v1.9] QApplication использует существующий tray_icon() приложения.")
    print(f"[Capri Taskbar v1.9] Резервная копия: {backup}")
    print("[Capri Taskbar v1.9] Полностью закрой Капри и запусти run.bat заново.")


if __name__ == "__main__":
    main()
