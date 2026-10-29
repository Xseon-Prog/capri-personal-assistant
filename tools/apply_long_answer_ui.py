"""Safely patch Capricorn to show long LLM answers in a separate readable window."""
from __future__ import annotations

import datetime
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MAIN = BASE / "main.py"
DIALOG = BASE / "answer_dialog.py"
MARKER = "CAPRI_LONG_ANSWER_UI_V1"


def fail(message: str) -> int:
    print(f"[Capri UI] Ошибка: {message}")
    return 1


def main() -> int:
    if not MAIN.is_file():
        return fail(f"Не найден {MAIN}. Запусти скрипт из папки проекта Capricorn.")
    if not DIALOG.is_file():
        return fail("Не найден answer_dialog.py. Скопируй его в корень проекта Capricorn.")

    source = MAIN.read_text(encoding="utf-8-sig")
    if MARKER in source:
        required = ("self.full_answer.emit(reply.text)", "capri.full_answer.connect(answer_windows.show)")
        if all(fragment in source for fragment in required):
            print("[Capri UI] Окно длинных ответов уже подключено; повторное изменение не требуется.")
            return 0
        return fail("Обнаружен неполный фрагмент предыдущей установки. main.py не изменён; пришли его для проверки.")

    anchors = {
        "signal": "    move_to = Signal(str)\n",
        "emit": '        if reply.action == "answer" and self.cfg.get("teleport_on_answer"):\n',
        "connect": "    capri = Capri(cfg)\n",
    }
    for name, anchor in anchors.items():
        count = source.count(anchor)
        if count != 1:
            return fail(f"Не удалось безопасно определить место для изменения '{name}' (совпадений: {count}). Файлы не изменены.")

    # Prepare all edits in memory before creating backup or writing anything.
    patched = source.replace(
        anchors["signal"],
        anchors["signal"] + f"    full_answer = Signal(str)  # {MARKER}\n",
        1,
    )
    patched = patched.replace(
        anchors["emit"],
        f"        # {MARKER}: keep long responses readable instead of relying only on the small avatar HUD.\n"
        "        if reply.action == \"answer\" and len(reply.text or \"\") > 240:\n"
        "            self.full_answer.emit(reply.text)\n"
        + anchors["emit"],
        1,
    )
    patched = patched.replace(
        anchors["connect"],
        anchors["connect"]
        + "    # CAPRI_LONG_ANSWER_UI_V1: display full text in a scrollable window.\n"
        "    from answer_dialog import AnswerWindowManager\n"
        "    answer_windows = AnswerWindowManager()\n"
        "    capri.full_answer.connect(answer_windows.show)\n",
        1,
    )

    # Validate that the source remains syntactically valid before touching main.py.
    try:
        compile(patched, str(MAIN), "exec")
    except SyntaxError as exc:
        return fail(f"Проверка синтаксиса не пройдена: {exc}. Файлы не изменены.")

    backup_dir = BASE / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"main_before_long_answer_ui_{stamp}.py"
    shutil.copy2(MAIN, backup)
    MAIN.write_text(patched, encoding="utf-8")

    print("[Capri UI] Улучшение отображения длинных ответов установлено.")
    print("[Capri UI] Длинные ответы (более 240 символов) будут открываться в отдельном окне с прокруткой.")
    print("[Capri UI] В окне есть кнопка копирования полного текста.")
    print(f"[Capri UI] Резервная копия: {backup}")
    print("[Capri UI] Полностью выйди из Капри через системный трей и запусти run.bat заново.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
