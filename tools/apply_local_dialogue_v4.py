"""Remove visible Markdown formatting from local Qwen answers without changing code blocks.

Copy this file into Capricorn's tools/ directory, then run from the project root:
    py -3.13 tools\\apply_local_dialogue_v4.py
"""
from __future__ import annotations

import datetime
import re
import shutil
import sys
from pathlib import Path

MARKER = "CAPRI_LOCAL_DIALOGUE_V4"
ROOT = Path(__file__).resolve().parents[1]

FORMATTER = '''def strip_markdown(text):
    """Remove visible Markdown syntax from prose while preserving fenced code contents."""
    parts = re.split(r"(```[\\s\\S]*?```)", text)
    for i, part in enumerate(parts):
        if part.startswith("```"):
            # Keep the source between fences, discard only the fence and optional language tag.
            match = re.match(r"```[^\\n`]*\\n?(.*?)```$", part, flags=re.S)
            parts[i] = match.group(1).strip("\\n") if match else part.strip("`")
            continue
        part = re.sub(r"\\[([^\\]]+)\\]\\((?:https?://|mailto:)[^)]+\\)", r"\\1", part)
        part = re.sub(r"`([^`\\n]+)`", r"\\1", part)
        part = re.sub(r"\\*\\*(.+?)\\*\\*", r"\\1", part)
        part = re.sub(r"__(.+?)__", r"\\1", part)
        part = re.sub(r"(?<!\\*)\\*([^*\\n]+)\\*(?!\\*)", r"\\1", part)
        part = re.sub(r"(?<!_)_([^_\\n]+)_(?!_)", r"\\1", part)
        part = re.sub(r"(?m)^\\s{0,3}#{1,6}\\s+", "", part)
        part = re.sub(r"(?m)^\\s{0,3}[-+]\\s+", "• ", part)
        parts[i] = part
    return re.sub(r"[ \\t]+\\n", "\\n", "".join(parts)).strip()


'''


def fail(message: str) -> None:
    raise ValueError(message)


def replace_once(pattern: str, replacement: str, source: str, label: str) -> str:
    updated, count = re.subn(pattern, lambda _m: replacement, source, count=1, flags=re.M)
    if count != 1:
        fail(f"Не удалось безопасно найти место для обновления «{label}» (совпадений: {count}). Файл не изменён.")
    return updated


def patch(source: str) -> str:
    if MARKER in source:
        if "def strip_markdown(text):" in source and "answer = strip_markdown(answer)" in source:
            return source
        fail("Обнаружена неполная установка v4. Восстанови local_ai.py из резервной копии.")
    if "CAPRI_LOCAL_MEMORY_V1" not in source or "CAPRI_LOCAL_DIALOGUE_V3" not in source:
        fail("Не найдена ожидаемая версия локальной памяти и диалога v3. Файл не изменён.")
    source = replace_once(r"^class LocalAI:\s*$", FORMATTER + "class LocalAI:", source, "функция очистки Markdown")
    source = replace_once(
        r"^        answer = naturalize\(drop_repeats\(drop_third_person\(answer\), self\.history\), question, recent\)\s*$",
        "        answer = naturalize(drop_repeats(drop_third_person(answer), self.history), question, recent)\n"
        "        answer = strip_markdown(answer)  # " + MARKER,
        source,
        "очистка форматирования ответа",
    )
    try:
        compile(source, "local_ai.py", "exec")
    except SyntaxError as exc:
        fail(f"Проверка синтаксиса не пройдена: {exc}")
    return source


def main() -> int:
    path = ROOT / "local_ai.py"
    if not path.is_file():
        print("ОШИБКА: local_ai.py не найден в корне проекта.", file=sys.stderr)
        return 1
    original = path.read_text(encoding="utf-8-sig")
    try:
        updated = patch(original)
    except Exception as exc:
        print("ОШИБКА: " + str(exc), file=sys.stderr)
        return 1
    if updated == original:
        print("Очистка Markdown v4 уже установлена; изменений не требуется.")
        return 0
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / f"backup_local_dialogue_v4_{stamp}"
    backup.mkdir()
    shutil.copy2(path, backup / "local_ai.py")
    path.write_text(updated, encoding="utf-8")
    print("Очистка Markdown v4 установлена.")
    print("Изменён только local_ai.py; облачные провайдеры и память не затронуты.")
    print(f"Резервная копия: {backup.name}")
    print("Полностью выйди из Капри через системный трей и снова запусти run.bat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
