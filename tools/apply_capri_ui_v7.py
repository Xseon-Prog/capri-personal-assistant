"""Improve Capri's multiline command input and normalize formatted local-model answers.

Copy into the existing Capricorn tools/ folder, then run from the project root:
    py -3.13 tools\\apply_capri_ui_v7.py
Only capri_ui.py and local_ai.py are patched. No cloud API is added.
"""
from __future__ import annotations

import datetime
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "CAPRI_CYBERPUNK_UI_V7"

LAYOUT_HELPER = r'''def normalize_answer_layout(text):
    """Turn model-generated inline Markdown/list separators into readable plain text."""  # CAPRI_CYBERPUNK_UI_V7
    parts = re.split(r"(```[\s\S]*?```)", text or "")
    for i, part in enumerate(parts):
        if part.startswith("```"):
            continue
        # Remove horizontal rules the model sometimes inserts between numbered steps.
        part = re.sub(r"\s*[-*_]{3,}\s*", "\n\n", part)
        # Turn inline Markdown headings into their own paragraphs before removing markers.
        part = re.sub(r"\s+#{1,6}\s*(?=[^\s#])", "\n\n", part)
        part = re.sub(r"(?m)^[ \t]*#{1,6}[ \t]*", "", part)
        # Split inline numbered steps only when there are multiple list items; IP addresses
        # like 8.8.8.8 do not match because a digit follows the dot rather than whitespace.
        item_re = r"(?<!\d)\b\d{1,2}[.)]\s+[A-Za-zА-ЯЁа-яё]"
        if len(re.findall(item_re, part)) >= 2:
            part = re.sub(r":\s+(?=\d{1,2}[.)]\s+[A-Za-zА-ЯЁа-яё])", ":\n", part)
            part = re.sub(r"[ \t]+(?=\d{1,2}[.)]\s+[A-Za-zА-ЯЁа-яё])", "\n", part)
        # Promote common inline section labels and inline bullets to separate lines.
        part = re.sub(r"[ \t]+(?=(?:пример|важные нюансы|важно|вывод|итог|заключение)\s*:)",
                      "\n\n", part, flags=re.IGNORECASE)
        part = re.sub(r"(?<=[.:])\s+[-•]\s+(?=[A-Za-zА-ЯЁа-яё])", "\n• ", part)
        part = re.sub(r"[ \t]+\n", "\n", part)
        part = re.sub(r"\n[ \t]+", "\n", part)
        part = re.sub(r"\n{3,}", "\n\n", part)
        parts[i] = part.strip()
    return "\n\n".join(part for part in parts if part.strip()).strip()


'''


def fail(message: str) -> int:
    print(f"[Capri UI v7] ОШИБКА: {message}", file=sys.stderr)
    print("Проверка не пройдена; исходные файлы не должны изменяться.", file=sys.stderr)
    return 1


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"Не удалось однозначно найти место «{label}» (совпадений: {count}).")
    return source.replace(old, new, 1)


def patch_ui(source: str) -> str:
    if MARKER in source:
        if "self.editor = QPlainTextEdit(self)" in source and "dialog.editor.toPlainText()" in source:
            return source
        raise ValueError("Найдена неполная установка v7 в capri_ui.py; восстанови резервную копию.")
    if "class CommandInputDialog(QDialog):" not in source or "self.editor = QLineEdit(self)" not in source:
        raise ValueError("Не найдено ожидаемое однострочное поле ввода из UI v6. Проверь capri_ui.py.")

    source = replace_once(source,
        '        self.setMinimumWidth(520)\n        self.setStyleSheet(CAPRI_STYLE)\n',
        '        self.setMinimumWidth(540)\n        self.resize(620, 300)  # ' + MARKER + ': wider multiline question input\n'
        '        self.setStyleSheet(CAPRI_STYLE)\n',
        "размер окна ввода")
    source = replace_once(source,
        '        hint = QLabel(prompt or "Введи текст для Капри.")\n'
        '        hint.setObjectName("hint")\n'
        '        hint.setWordWrap(True)\n'
        '        root.addWidget(hint)\n'
        '        self.editor = QLineEdit(self)\n'
        '        self.editor.setPlaceholderText("Например: объясни, как работает DNS…")\n'
        '        self.editor.setText(default)\n'
        '        self.editor.returnPressed.connect(self.accept)\n'
        '        root.addWidget(self.editor)\n',
        '        hint = QLabel((prompt or "Введи текст для Капри.") + "\\nEnter — новая строка; Ctrl+Enter — отправить.")\n'
        '        hint.setObjectName("hint")\n'
        '        hint.setWordWrap(True)\n'
        '        root.addWidget(hint)\n'
        '        self.editor = QPlainTextEdit(self)  # ' + MARKER + '\n'
        '        self.editor.setPlaceholderText("Например: объясни, как работает DNS…")\n'
        '        self.editor.setPlainText(default)\n'
        '        self.editor.setMinimumHeight(100)\n'
        '        self.editor.setMaximumHeight(150)\n'
        '        root.addWidget(self.editor)\n'
        '        self._submit_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.editor)\n'
        '        self._submit_shortcut.activated.connect(self.accept)\n'
        '        self._submit_shortcut_enter = QShortcut(QKeySequence("Ctrl+Enter"), self.editor)\n'
        '        self._submit_shortcut_enter.activated.connect(self.accept)\n',
        "многострочное поле ввода")
    source = replace_once(source,
        '        return dialog.editor.text(), accepted\n',
        '        return dialog.editor.toPlainText(), accepted  # ' + MARKER + '\n',
        "чтение многострочного текста")
    return source


def patch_local_ai(source: str) -> str:
    if MARKER in source:
        if "def normalize_answer_layout(text):" in source and "answer = normalize_answer_layout(answer)" in source:
            return source
        raise ValueError("Найдена неполная установка v7 в local_ai.py; восстанови резервную копию.")
    for marker in ("CAPRI_LOCAL_DIALOGUE_V4", "CAPRI_LOCAL_DIALOGUE_V5", "CAPRI_LOCAL_DIALOGUE_V6_FORMAT"):
        if marker not in source:
            raise ValueError(f"Не найден маркер {marker}; проверь, что установлены обновления диалога v4–v6.")
    source = replace_once(source, "class LocalAI:", LAYOUT_HELPER + "class LocalAI:", "нормализатор разметки")

    lines = source.splitlines(keepends=True)
    matched = [i for i, line in enumerate(lines) if "answer = strip_markdown(answer)" in line]
    if len(matched) != 1:
        raise ValueError(f"Не удалось найти единственное место вызова strip_markdown (найдено: {len(matched)}).")
    i = matched[0]
    indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
    if i + 1 < len(lines) and "normalize_answer_layout(answer)" in lines[i + 1]:
        raise ValueError("Вызов нормализатора найден, но маркер v7 отсутствует; проверь local_ai.py вручную.")
    lines.insert(i + 1, indent + "answer = normalize_answer_layout(answer)  # " + MARKER + "\n")
    updated = "".join(lines)
    return updated


def main() -> int:
    paths = {name: ROOT / name for name in ("capri_ui.py", "local_ai.py")}
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        return fail("Не найдены файлы: " + ", ".join(missing) + ". Сначала скопируй capri_ui.py из архива v6 в корень проекта.")
    original = {name: path.read_text(encoding="utf-8-sig") for name, path in paths.items()}
    try:
        patched = {
            "capri_ui.py": patch_ui(original["capri_ui.py"]),
            "local_ai.py": patch_local_ai(original["local_ai.py"]),
        }
        for name, content in patched.items():
            compile(content, name, "exec")
        # Ensure the expected shortcut and multiline API are actually present.
        assert 'QShortcut(QKeySequence("Ctrl+Return"), self.editor)' in patched["capri_ui.py"]
        assert "dialog.editor.toPlainText()" in patched["capri_ui.py"]
        assert "answer = normalize_answer_layout(answer)" in patched["local_ai.py"]
    except Exception as exc:
        return fail(str(exc))

    changes = {name: content for name, content in patched.items() if content != original[name]}
    if not changes:
        print("[Capri UI v7] Обновление уже установлено; изменений не требуется.")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "backups" / f"capri_ui_v7_{stamp}"
    try:
        backup.mkdir(parents=True, exist_ok=False)
        for name in changes:
            shutil.copy2(paths[name], backup / name)
        written: list[str] = []
        try:
            for name, content in changes.items():
                paths[name].write_text(content, encoding="utf-8")
                written.append(name)
        except OSError:
            for name in written:
                shutil.copy2(backup / name, paths[name])
            raise
    except Exception as exc:
        return fail(f"Не удалось записать обновление; проверь резервную копию {backup}: {exc}")

    print("[Capri UI v7] Обновление установлено.")
    print("Изменены: " + ", ".join(changes))
    print("Поле команды теперь многострочное: Enter добавляет строку, Ctrl+Enter отправляет.")
    print("Ответы локальной модели: Markdown-разделители и встроенная нумерация форматируются для чтения.")
    print("Анимации, команды Windows, память SQLite, провайдеры и оформление остальных окон не менялись.")
    print(f"Резервные копии: {backup}")
    print("Полностью выйди из Капри через системный трей и запусти run.bat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
