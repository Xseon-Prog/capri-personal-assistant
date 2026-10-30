from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

MARKER = "CAPRI_TELEGRAM_CHAT_FIX_V1"
ROUTE_ANCHOR = '            (r"^(открой |зайди в |перейди в |выбери |найди )?(в )?(телеграм\\w*|telegram|телег\\w*|тг )?\\s*"'

NEW_ROUTES = '''            # CAPRI_TELEGRAM_CHAT_FIX_V1: natural phrases for finding Telegram chats/contacts
            (r"^(?:найди|поищи|открой|покажи|перейди|зайди)(?: мне)?\\s+(?:в\\s+)?(?:чат|диалог|переписк\\w*)\\s+(?:с\\s+)?(?P<name>.+?)(?:\\s+(?:в|через)\\s+(?:telegram|телеграм\\w*|телега|тг))?$", self.chat),
            (r"^(?:найди|поищи|открой|покажи|перейди|зайди)(?: мне)?\\s+(?:в\\s+)?(?:telegram|телеграм\\w*|телега|тг)\\s+(?:чат|диалог|переписк\\w*)\\s+(?:с\\s+)?(?P<name>.+)$", self.chat),
            (r"^(?:найди|поищи)(?: мне)?\\s+(?:контакт|человек\\w*|пользовател\\w*)\\s+(?P<name>.+?)\\s+(?:в|через)\\s+(?:telegram|телеграм\\w*|телега|тг)$", self.chat),
            (r"^(?:найди|поищи)(?: мне)?\\s+(?P<name>.+?)\\s+(?:в|через)\\s+(?:telegram|телеграм\\w*|телега|тг)$", self.chat),
'''

SEARCH_AND_CHAT_IMPL = r'''# CAPRI_TELEGRAM_CHAT_FIX_V1
def _telegram_search_field(hwnd):
    """Найти именно поиск списка чатов Telegram, а не поле поиска стикеров.

    В Telegram несколько Edit-полей могут называться «Поиск». Выбираем только
    видимое поле в верхней левой части главного окна: поле стикеров обычно
    находится в плавающей панели у области ввода сообщения и отбрасывается.
    """
    try:
        from ctypes import wintypes
        import comtypes.client
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA

        rect = wintypes.RECT()
        if not u.GetWindowRect(hwnd, __import__("ctypes").byref(rect)):
            return None
        win_w = max(1, rect.right - rect.left)
        win_h = max(1, rect.bottom - rect.top)

        uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
        root = uia.ElementFromHandle(hwnd)
        edits = root.FindAll(
            UIA.TreeScope_Descendants,
            uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, UIA.UIA_EditControlTypeId),
        )
        candidates = []
        for i in range(edits.Length):
            element = edits.GetElement(i)
            if not element.CurrentIsKeyboardFocusable:
                continue
            label = (element.CurrentName or "").strip().lower()
            if label not in ("поиск", "search"):
                continue
            if getattr(element, "CurrentIsOffscreen", False):
                continue
            bounds = element.CurrentBoundingRectangle
            left, top = float(bounds.left), float(bounds.top)
            width, height = float(bounds.right - bounds.left), float(bounds.bottom - bounds.top)
            if width < 80 or height < 12 or height > 90:
                continue
            rel_x = (left - rect.left) / win_w
            rel_y = (top - rect.top) / win_h
            center_x = rel_x + width / win_w / 2
            center_y = rel_y + height / win_h / 2
            # Search in the chat sidebar: upper-left region of the Telegram window.
            # This intentionally excludes the sticker/emoji popover search input.
            if not (0.0 <= rel_x <= 0.45 and 0.0 <= rel_y <= 0.30 and center_x <= 0.62):
                continue
            score = center_y * 4.0 + center_x
            candidates.append((score, element))
        if candidates:
            candidates.sort(key=lambda item: item[0])
            return candidates[0][1]
    except Exception:
        log.exception("Не удалось найти поле поиска чатов Telegram через UI Automation")
    return None


def telegram_open_chat(index=None, name=None):
    """Открыть чат Telegram, не вводя запрос в поиск стикеров или эмодзи.

    Перед поиском закрываем плавающие панели клавишей Esc, возвращаемся к списку
    чатов и используем верхнее поле боковой панели. Если UI Automation не нашла
    его, Ctrl+F вызывает штатную команду Search Telegram.
    """
    from actions import send_keys

    hwnd = wait_and_focus(("telegram",), timeout=8)
    if not hwnd:
        log.info("Telegram не найден или не удалось активировать его окно")
        return False

    before = window_title(hwnd).replace("\u200e", "").lower()

    # Закрыть, в частности, открытый picker эмодзи/стикеров. Это важно делать
    # ДО поиска Edit-поля: иначе UIA может вернуть поле поиска стикеров.
    send_keys(["esc"])
    time.sleep(0.18)
    send_keys(["esc"])
    time.sleep(0.25)
    if not is_foreground(hwnd):
        if not focus(hwnd):
            return False

    field = _telegram_search_field(hwnd)
    if field is not None:
        try:
            field.SetFocus()
            time.sleep(0.25)
        except Exception:
            log.exception("Не удалось сфокусировать поиск чатов Telegram")
            field = None

    if field is None:
        # Штатная команда Search Telegram Desktop. Esc выше уже закрыл стикерную панель.
        send_keys(["ctrl", "f"])
        time.sleep(0.35)
        field = _telegram_search_field(hwnd)
        if field is not None:
            try:
                field.SetFocus()
                time.sleep(0.2)
            except Exception:
                log.exception("Не удалось сфокусировать поле после Ctrl+F")

    if not is_foreground(hwnd):
        log.info("Telegram потерял фокус перед вводом запроса чата")
        return False

    send_keys(["ctrl", "a"])
    time.sleep(0.08)
    if name:
        query = " ".join(str(name).strip().split())
        if not query:
            return False
        paste_text(query)
        # Даём Telegram на слабом ПК время построить результаты поиска.
        time.sleep(2.0)
        if not is_foreground(hwnd):
            log.info("Telegram потерял фокус во время поиска чата «%s»", query)
            return False
        send_keys(["enter"])
    else:
        send_keys(["backspace"])
        time.sleep(0.3)
        for _ in range(max(1, index or 1)):
            send_keys(["down"])
            time.sleep(0.1)
        send_keys(["enter"])

    query_words = [w.lower().replace("ё", "е") for w in str(name or "").split() if len(w) >= 3]
    for _ in range(18):
        time.sleep(0.25)
        title = window_title(hwnd).replace("\u200e", "").lower().replace("ё", "е")
        if name:
            # Confirm the opened window title relates to the requested contact.
            if query_words and all(token in title for token in query_words):
                return True
        elif title != before:
            return True

    log.info("Telegram не подтвердил открытие нужного чата «%s». Текущий заголовок: «%s»",
             name or f"номер {index or 1}", window_title(hwnd))
    # Не оставляем Капри в случайно открытом результате, если проверка не прошла.
    send_keys(["esc"])
    return False
'''


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: ожидалось одно совпадение, найдено {count}")
    return source.replace(old, new, 1)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    actions_path = root / "actions.py"
    automation_path = root / "automation.py"
    if not actions_path.is_file() or not automation_path.is_file():
        print("[Capri Telegram Fix v1] ОШИБКА: запускай установщик из папки tools внутри корня проекта.")
        return 2

    actions = actions_path.read_text(encoding="utf-8-sig")
    automation = automation_path.read_text(encoding="utf-8-sig")

    if MARKER in actions and MARKER in automation:
        print("[Capri Telegram Fix v1] Исправление уже установлено. Файлы не изменены.")
        return 0

    if MARKER in actions or MARKER in automation:
        print("[Capri Telegram Fix v1] ОШИБКА: обнаружена частичная установка. Файлы не изменены.")
        return 3

    route_anchor = '            (r"^(открой |зайди в |перейди в |выбери |найди )?(в )?(телеграм\\w*|telegram|телег\\w*|тг )?\\s*'
    if actions.count(route_anchor) != 1:
        print("[Capri Telegram Fix v1] ОШИБКА: не найден ожидаемый блок Telegram-команд в actions.py. Файлы не изменены.")
        return 4

    search_start = automation.find("def _telegram_search_field(hwnd):")
    chat_start = automation.find("def telegram_open_chat(index=None, name=None):", search_start + 1)
    if search_start < 0 or chat_start < 0:
        print("[Capri Telegram Fix v1] ОШИБКА: не найдены функции Telegram в automation.py. Файлы не изменены.")
        return 5
    # In the current project these two Telegram helpers are the final definitions in automation.py.
    trailing = automation[chat_start:]
    if "\ndef " in trailing:
        print("[Capri Telegram Fix v1] ОШИБКА: структура automation.py отличается от ожидаемой. Файлы не изменены.")
        return 6

    actions_new = actions.replace(route_anchor, NEW_ROUTES + route_anchor, 1)
    # Improve inflection handling for short Russian contact names («маме», «маму», «мама»).
    stem_start = actions_new.find("def stem_name(name):")
    stem_end = actions_new.find("\ndef youtube_search_in_tab", stem_start + 1)
    if stem_start < 0 or stem_end < 0:
        print("[Capri Telegram Fix v1] ОШИБКА: функция stem_name не найдена. Файлы не изменены.")
        return 9
    stem_func = actions_new[stem_start:stem_end]
    stem_func_new = replace_once(stem_func, "        if len(w) >= 5:\n", "        if len(w) >= 5 or (len(w) == 4 and w.endswith((\"е\", \"у\", \"ы\", \"и\"))):\n", "stem_name")
    actions_new = actions_new[:stem_start] + stem_func_new + actions_new[stem_end:]

    automation_new = automation[:search_start] + SEARCH_AND_CHAT_IMPL + "\n"

    # Ensure all expected markers and the four core command patterns are present before touching files.
    if MARKER not in actions_new or "Ctrl+F" not in automation_new:
        print("[Capri Telegram Fix v1] ОШИБКА: внутренняя проверка патча не пройдена. Файлы не изменены.")
        return 7

    backup_dir = root / "backups" / f"capri_telegram_chat_fix_{datetime.now():%Y%m%d_%H%M%S}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(actions_path, backup_dir / "actions.py")
    shutil.copy2(automation_path, backup_dir / "automation.py")

    actions_path.write_text(actions_new, encoding="utf-8", newline="\n")
    automation_path.write_text(automation_new, encoding="utf-8", newline="\n")

    try:
        import ast
        ast.parse(actions_new)
        ast.parse(automation_new)
    except SyntaxError as exc:
        shutil.copy2(backup_dir / "actions.py", actions_path)
        shutil.copy2(backup_dir / "automation.py", automation_path)
        print(f"[Capri Telegram Fix v1] ОШИБКА синтаксиса; файлы восстановлены из резервной копии: {exc}")
        return 8

    print("[Capri Telegram Fix v1] Установка завершена.")
    print(f"Резервная копия: {backup_dir}")
    print("Изменены: actions.py, automation.py")
    print("Проверка: синтаксис обоих файлов корректен.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
