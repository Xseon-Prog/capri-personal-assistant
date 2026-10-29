"""Improve factual precision and detailed explanations in local Capricorn dialogue.

Copy this file into Capricorn's tools/ directory, then run from the project root:
    py -3.13 tools\\apply_local_dialogue_v5.py

Only local_ai.py is changed. No cloud API is added.
"""
from __future__ import annotations

import datetime
import re
import shutil
import sys
from pathlib import Path

MARKER = "CAPRI_LOCAL_DIALOGUE_V5"
ROOT = Path(__file__).resolve().parents[1]

GUIDANCE = '''FACTUAL_GUIDANCE = """Правила фактической точности:
- Не придумывай точные числа, даты, IP-адреса, версии и названия ради наглядности. Если значение может меняться, скажи об этом или используй явно условный пример.
- Для технических тем объясняй реальный механизм; упрощённую аналогию не выдавай за точное описание протокола.
- Не утверждай, что проверила свежие сведения, запустила код или выполнила действие, если у тебя нет результата соответствующего инструмента.
- Если не уверена в конкретной детали, честно обозначь неопределённость и отдели её от известных фактов."""  # CAPRI_LOCAL_DIALOGUE_V5

DETAIL_GUIDANCE = """Для запроса с просьбой подробно объяснить, разобрать или решить:
- Дай содержательный ответ, а не только краткое резюме. Обычно нужно примерно 180–350 слов; сложность темы может требовать больше или меньше.
- Начни с простого определения, затем объясни процесс последовательно в 5–8 понятных шагов или связанных абзацах, когда это подходит теме.
- Расшифруй важные термины при первом использовании и покажи один практический пример.
- Укажи важный нюанс, ограничение или типичную ошибку, если это помогает понять тему.
- Не повторяй одно и то же разными словами, не добавляй пустое вступление и не заканчивай автоматическим предложением «могу рассказать ещё».
- Пиши по-русски обычным текстом. Не используй Markdown-звёздочки, заголовки с решётками или таблицы; простая нумерация допустима.
- Для динамических значений (например, IP-адреса сайта) поясни, что пример не является постоянным значением."""  # CAPRI_LOCAL_DIALOGUE_V5
'''


def fail(message: str) -> None:
    raise ValueError(message)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        fail(f"Не удалось безопасно найти место для обновления «{label}» (совпадений: {count}). Файл не изменён.")
    return source.replace(old, new, 1)


def patch(source: str) -> str:
    if MARKER in source:
        if "FACTUAL_GUIDANCE" in source and "DETAIL_GUIDANCE" in source and "max_tokens = 1200 if DETAIL_REQUEST_RE.search(question) else 420" in source:
            return source
        fail("Найдена неполная установка v5. Восстанови local_ai.py из резервной копии.")

    for required in ("CAPRI_LOCAL_MEMORY_V1", "CAPRI_LOCAL_DIALOGUE_V3", "CAPRI_LOCAL_DIALOGUE_V4"):
        if required not in source:
            fail(f"Не найден маркер {required}. Сначала проверь предыдущие обновления.")
    if "DETAIL_REQUEST_RE" not in source:
        fail("Не найден классификатор подробных запросов DETAIL_REQUEST_RE. Сначала установи локальный диалог v3.")

    source = replace_once(source, "class LocalAI:", GUIDANCE + "\nclass LocalAI:", "правила точности и подробных объяснений")

    old_context = '        messages = [{"role": "system", "content": system_context}] + self.history'
    new_context = r'''        system_context += "\n\nПРАВИЛА ТОЧНОСТИ:\n" + FACTUAL_GUIDANCE
        if DETAIL_REQUEST_RE.search(question):
            system_context += "\n\nПРАВИЛА ПОДРОБНОГО ОТВЕТА:\n" + DETAIL_GUIDANCE
        messages = [{"role": "system", "content": system_context}] + self.history'''
    source = replace_once(source, old_context, new_context, "динамические правила системного контекста")

    old_limit = "max_tokens = 900 if DETAIL_REQUEST_RE.search(question) else 420"
    new_limit = "max_tokens = 1200 if DETAIL_REQUEST_RE.search(question) else 420  # " + MARKER
    source = replace_once(source, old_limit, new_limit, "лимит токенов подробного ответа")

    try:
        compile(source, "local_ai.py", "exec")
    except SyntaxError as exc:
        fail(f"Проверка синтаксиса не пройдена: {exc}")
    return source


def apply(root: Path) -> int:
    target = root / "local_ai.py"
    if not target.is_file():
        print("ОШИБКА: local_ai.py не найден в корне проекта.", file=sys.stderr)
        return 1
    original = target.read_text(encoding="utf-8-sig")
    try:
        updated = patch(original)
    except Exception as exc:
        print("ОШИБКА: " + str(exc), file=sys.stderr)
        print("Файл не должен изменяться, если проверка совместимости не прошла.", file=sys.stderr)
        return 1
    if updated == original:
        print("Улучшение точности и подробных ответов v5 уже установлено; изменений не требуется.")
        return 0
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / f"backup_local_dialogue_v5_{stamp}"
    backup.mkdir()
    shutil.copy2(target, backup / "local_ai.py")
    target.write_text(updated, encoding="utf-8")
    print("Улучшение точности и подробных ответов v5 установлено.")
    print("Изменён только local_ai.py; память, аватар, управление Windows и облачные API не затронуты.")
    print("Для подробных запросов: расширенные инструкции и до 1200 выходных токенов; обычные ответы — без изменений.")
    print(f"Резервная копия: {backup.name}")
    print("Полностью выйди из Капри через системный трей и снова запусти run.bat.")
    return 0


def main() -> int:
    try:
        return apply(ROOT)
    except Exception as exc:
        print("ОШИБКА: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
