"""Safely install the cyberpunk UI refresh for Capricorn; no cloud providers are added."""
from __future__ import annotations
import datetime
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "CAPRI_CYBERPUNK_UI_V6"

def fail(message: str) -> int:
    print(f"[Capri UI v6] ОШИБКА: {message}")
    print("Исходники не должны изменяться при ошибке проверки.")
    return 1

def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"Не удалось однозначно определить место изменения «{label}» (совпадений: {count}).")
    return source.replace(old, new, 1)

def patch_main(source: str) -> str:
    if MARKER in source:
        if "capri.report_requested.connect(report_windows.show)" in source and "CommandInputDialog.getText" in source:
            return source
        raise ValueError("Обнаружена неполная установка интерфейса v6 в main.py.")
    if "CAPRI_LONG_ANSWER_UI_V1" not in source or "capri.full_answer.connect(answer_windows.show)" not in source:
        raise ValueError("Не найдена ожидаемая интеграция окна полного ответа. Сначала восстанови/проверь этот модуль.")
    source = replace_once(source,
        '    full_answer = Signal(str)  # CAPRI_LONG_ANSWER_UI_V1\n',
        '    full_answer = Signal(str)  # CAPRI_LONG_ANSWER_UI_V1\n'
        '    choice_requested = Signal(object)  # ' + MARKER + '\n'
        '    report_requested = Signal(str, str)  # ' + MARKER + '\n',
        "сигналы диалогов")
    old_input = '''    def ask_text():
        text, ok = QInputDialog.getText(None, "Капри", "Команда или вопрос:")
        if ok and text.strip():
            capri.text_command(text.strip())
'''
    new_input = '''    def ask_text():
        from capri_ui import CommandInputDialog  # CAPRI_CYBERPUNK_UI_V6
        text, ok = CommandInputDialog.getText(None, "Капри", "Команда или вопрос:")
        if ok and text.strip():
            capri.text_command(text.strip())
'''
    source = replace_once(source, old_input, new_input, "диалог ввода команды")
    source = replace_once(source,
        '    capri.full_answer.connect(answer_windows.show)\n',
        '    capri.full_answer.connect(answer_windows.show)\n'
        '    # ' + MARKER + ': themed report and selection dialogs run in the GUI thread.\n'
        '    from capri_ui import ReportWindowManager, ChoiceWindowManager\n'
        '    report_windows = ReportWindowManager()\n'
        '    choice_windows = ChoiceWindowManager()\n'
        '    capri.report_requested.connect(report_windows.show)\n'
        '    capri.actions.report_callback = lambda path, report: capri.report_requested.emit(path, report)\n'
        '    capri.choice_requested.connect(choice_windows.show)\n'
        '    choice_windows.selected.connect(capri.text_command)\n',
        "подключение окон и сигналов")
    old_finish = '''        if self.say(reply.text):
            return  # перебили — уже слушаем новую команду

        if reply.action == "quit":
'''
    new_finish = (
        '        if self.say(reply.text):\n'
        '            return  # перебили — уже слушаем новую команду\n'
        '\n'
        '        # ask with a populated choice list means matches are ambiguous.\n'
        '        if reply.action == "ask" and self.actions.choice:\n'
        '            self.choice_requested.emit([name for name, _ in self.actions.choice])  # ' + MARKER + '\n'
        '\n'
        '        if reply.action == "quit":\n'
    )
    source = replace_once(source, old_finish, new_finish, "выбор приложения/процесса")
    return source

def patch_actions(source: str) -> str:
    if MARKER in source:
        if "self.report_callback = None" in source and "callback(path, report)" in source:
            return source
        raise ValueError("Обнаружена неполная установка интерфейса v6 в actions.py.")
    source = replace_once(source,
        '        self.save = save  # save(раздел, название, значение или None) → текст ошибки или None\n',
        '        self.save = save  # save(раздел, название, значение или None) → текст ошибки или None\n'
        '        self.report_callback = None  # ' + MARKER + ': main supplies a GUI-thread signal callback.\n',
        "callback окна отчёта")
    source = replace_once(source,
        '        os.startfile(path)\n        use_ai = self.cfg.get("enable_ai") and self.ai and self.ai.available\n',
        '        callback = getattr(self, "report_callback", None)  # ' + MARKER + '\n'
        '        if callback:\n'
        '            callback(path, report)\n'
        '        else:\n'
        '            os.startfile(path)\n'
        '        use_ai = self.cfg.get("enable_ai") and self.ai and self.ai.available\n',
        "кастомное окно диагностики")
    return source

def patch_local_ai(source: str) -> str:
    if "CAPRI_LOCAL_DIALOGUE_V6_FORMAT" in source:
        return source
    if "CAPRI_LOCAL_DIALOGUE_V4" not in source or "CAPRI_LOCAL_DIALOGUE_V5" not in source or "def strip_markdown(text):" not in source:
        raise ValueError("Не найдена ожидаемая версия очистки Markdown v4 и точности v5 в local_ai.py.")
    old = '    return re.sub(r"[ \\t]+\\n", "\\n", "".join(parts)).strip()'
    new = '''    text = "".join(parts)
    # Normalize horizontal rules that small models often insert between numbered steps.
    text = re.sub(r"(?m)^\\s*[-*_]{3,}\\s*$", "", text)
    text = re.sub(r"\\s+[-*_]{3,}\\s+(?=\\d{1,2}[.)]\\s)", "\\n", text)
    text = re.sub(r"\\s+[-*_]{3,}\\s+(?=(?:пример|важно|примечание|вывод)\\b)", "\\n\\n", text, flags=re.IGNORECASE)
    text = re.sub(r"[ \\t]+\\n", "\\n", text)
    text = re.sub(r"\\n{3,}", "\\n\\n", text)
    return text.strip()  # CAPRI_LOCAL_DIALOGUE_V6_FORMAT'''
    return replace_once(source, old, new, "нормализация разделителей Markdown")

def main() -> int:
    files = {name: ROOT / name for name in ("main.py", "actions.py", "local_ai.py", "capri_ui.py", "answer_dialog.py")}
    missing = [str(path.name) for path in files.values() if not path.is_file()]
    if missing:
        return fail("Не найдены файлы в корне проекта: " + ", ".join(missing) + ". Скопируй capri_ui.py и answer_dialog.py туда из архива.")
    originals = {name: path.read_text(encoding="utf-8-sig") for name, path in files.items() if name in ("main.py", "actions.py", "local_ai.py")}
    try:
        patched = {
            "main.py": patch_main(originals["main.py"]),
            "actions.py": patch_actions(originals["actions.py"]),
            "local_ai.py": patch_local_ai(originals["local_ai.py"]),
        }
        for name, content in patched.items():
            compile(content, name, "exec")
        compile(files["capri_ui.py"].read_text(encoding="utf-8-sig"), "capri_ui.py", "exec")
        compile(files["answer_dialog.py"].read_text(encoding="utf-8-sig"), "answer_dialog.py", "exec")
    except Exception as exc:
        return fail(str(exc))
    changes = {name: content for name, content in patched.items() if content != originals[name]}
    if not changes:
        print("[Capri UI v6] Интерфейс v6 уже установлен; повторное изменение не требуется.")
        return 0
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "backups" / f"capri_ui_v6_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    for name in changes:
        shutil.copy2(files[name], backup / name)
    written = []
    try:
        for name, content in changes.items():
            files[name].write_text(content, encoding="utf-8")
            written.append(name)
    except OSError as exc:
        for name in written:
            shutil.copy2(backup / name, files[name])
        return fail(f"Ошибка записи; исходники восстановлены из резервной копии: {exc}")
    print("[Capri UI v6] Киберпанк-интерфейс установлен.")
    print("Изменены: " + ", ".join(changes))
    print("Добавлено: окно ввода команд, окно выбора приложения/процесса, окно отчёта вместо Блокнота.")
    print("Полный ответ получил тёмную тему; очистка Markdown убирает разделители между шагами.")
    print(f"Резервные копии: {backup}")
    print("Полностью выйди из Капри через системный трей и снова запусти run.bat.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
